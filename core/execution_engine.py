"""Edge Labs — Position & Order Execution Engine
Handles 3-pass speed simulation, dynamic market-driven targets & stops, multi-account parallel live execution,
sub-millisecond in-memory Breakeven & Profit Ratchet position modifications, and post-trade broker reconciliation.
"""
from __future__ import annotations
import math, time, logging, os, json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import pandas as pd

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from core.api_client import EdgeLabsClient
from core.analysis_engine import AnalysisSnapshot
from core.multi_account_manager import MultiAccountManager
from core.virtual_broker import VirtualBrokerAccount

logger = logging.getLogger("trade")


class ExecutionEngine:
    """Manages dynamic R:R sizing, multi-account live execution, and in-memory position management."""

    def __init__(self, client: EdgeLabsClient, account_manager: Optional[MultiAccountManager] = None):
        self.client = client
        self.account_manager = account_manager
        self.virtual_broker = VirtualBrokerAccount(starting_balance=4775.66, loss_floor=4755.66, leverage=10.0)
        self.daily_executions: int = 0
        self.active_simulations: List[Dict[str, Any]] = []
        self.live_positions: Dict[str, Dict[str, Any]] = {}  # In-memory RAM cache: {order_id: pos_data}
        self.last_candle_traded: Dict[str, int] = {'A': 0, 'B': 0, 'C': 0}
        self.failed_candle_ts: int = 0
        self.cooldown_candle_ts: int = 0
        self.cooldown_until: float = 0.0

    def can_trade_track(self, track_id: str, candle_ts: int, is_high_conviction: bool = False) -> bool:
        """Enforces strictly ONE trade per individual track per M5 candle, protects against failed candle re-entry,
        and manages post-loss cooldown with high-conviction bypass."""
        # 1. Failed Candle Re-entry Guard: If a trade failed on this specific candle, block re-entering (unless Track C hedge)
        if candle_ts and candle_ts == self.failed_candle_ts and track_id != 'C' and not is_high_conviction:
            return False

        # 2. Post-Loss Cooldown Guard: Holds until next candle boundary unless high-conviction bypass occurs
        if candle_ts and candle_ts == self.cooldown_candle_ts:
            if not is_high_conviction:
                return False
            logger.info(f"[{track_id}] ⚡ HIGH-CONVICTION BYPASS: Breaking cooldown on confirmed 5-D breakout setup")

        # 3. Standard time-based cooldown
        if time.time() < self.cooldown_until and not is_high_conviction:
            return False

        # 4. Prevent duplicate same-track firing on same candle
        if candle_ts and candle_ts == self.last_candle_traded.get(track_id, 0):
            return False

        return True

    def run_three_pass_simulation(
        self,
        snapshot: AnalysisSnapshot,
        entry_price: float,
        tp_dist: float,
        sl_dist: float,
        side: str
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        """Runs an upgraded 3-pass Monte-Carlo trajectory simulation before execution.
        Evaluates real-time Spread Friction, Tick Noise Variance, and Maximum Adverse Excursion:
        Pass 1: Base Momentum Drift (1.0x) + Live Spread Friction
        Pass 2: High Surge Acceleration (1.25x)
        Pass 3: Stagnation & Pullback Stress-Test (0.75x) + 1.5x Noise Jitter
        """
        passes = []
        variants = [
            ("Pass 1 (Base 1.0x)", 1.00, 1.00),
            ("Pass 2 (High 1.25x)", config.SIMULATION_SPEED_VARIANT_HIGH, 0.80),
            ("Pass 3 (Stagnation 0.75x)", config.SIMULATION_SPEED_VARIANT_LOW, 1.50),
        ]

        p_vel = max(0.08, snapshot.speed.price_velocity)  # $/min
        t_vel = max(10.0, snapshot.speed.tick_velocity)   # ticks/min
        spread_friction = max(0.02, min(0.30, snapshot.spread / 100.0 if snapshot.spread > 5 else snapshot.spread))
        adverse_dist = getattr(snapshot, 'adverse_noise_dist', 0.05)
        adverse_vel = getattr(snapshot, 'adverse_noise_vel', 0.02)

        # Opposing wick friction drag (0.00 to 0.20)
        wick_opp = snapshot.rejection.upper_ratio if side == 'buy' else snapshot.rejection.lower_ratio

        success_count = 0
        for name, speed_mult, noise_mult in variants:
            eff_pvel = p_vel * speed_mult
            eff_tvel = t_vel * speed_mult

            # 1. Estimated time to reach TP distance in seconds
            time_to_tp = (tp_dist / eff_pvel) * 60.0 if eff_pvel > 0 else 999.0

            # 2. Real Opposing Counter-Trend Noise Model
            # Evaluates true opposing counter-pullback depth and adverse counter-velocity
            opposing_counter_noise = max(adverse_dist * 0.85, (adverse_vel * 0.4) + (spread_friction * 1.2)) * noise_mult
            adverse_excursion = round((wick_opp * sl_dist * 0.80) + opposing_counter_noise, 3)

            is_pass_ok = (time_to_tp <= 300.0) and (adverse_excursion < sl_dist)
            if is_pass_ok:
                success_count += 1

            passes.append({
                'name': name,
                'speed_multiplier': speed_mult,
                'est_fill_seconds': round(time_to_tp, 1),
                'pullback_risk': adverse_excursion,
                'passed': is_pass_ok
            })

        all_passed = (success_count >= 2)
        return all_passed, passes

    def _slice_lots(self, lots: float, chunk_cap: float, lot_step: float, min_lot: float) -> list[float]:
        """Slices total position into chunks of <= chunk_cap lots."""
        chunks = []
        rem = lots
        while rem > 0:
            c = min(chunk_cap, rem)
            c = math.floor(c / lot_step) * lot_step
            c = round(max(min_lot, c), 2)
            chunks.append(c)
            rem = round(rem - c, 2)
        return chunks

    def calculate_trade_setup(
        self,
        snapshot: AnalysisSnapshot,
        entry_price: float,
        candle_time: int = 0
    ) -> Optional[Dict[str, Any]]:
        """Calculates dynamic market-driven targets, micro-stops, and compliant lot sizes per track."""
        contract_size = self.client.contract_size
        lot_step      = self.client.lot_step
        min_lot       = self.client.min_lot
        max_lot       = self.client.max_lot

        # Dynamic Micro-Pulse Displacement
        p_sec = max(0.05, snapshot.speed.price_velocity / 60.0)
        t_sec = max(1.0, snapshot.speed.tick_velocity / 60.0)
        pulse_dist = p_sec / t_sec
        spread_val = snapshot.spread if snapshot.spread < 5 else snapshot.spread / 100.0
        side = getattr(snapshot, 'impulse_side', 'buy' if snapshot.direction.bias == 'green' else 'sell')

        # Dynamic Stop Distance: Spread Friction + Pulse Displacement (0.04 to 0.12 USD)
        dyn_stop_distance = round(max(0.04, min(0.12, (spread_val * 1.5) + (pulse_dist * 0.8))), 2)

        # Spread-Anchored Price References
        bid_ref = round(entry_price, 2)
        ask_ref = round(entry_price + spread_val, 2)

        # ── TRACK A: Scalper (Strict 0.10 Lots, Max $2.00 Target, Max 12¢ Stop) ──
        risk_a = config.DEFAULT_TRACK_A_RISK_LIMIT
        target_a = config.DEFAULT_TRACK_A_PROFIT_TARGET
        sl_dist_a = min(0.12, dyn_stop_distance)
        final_lots_a = float(config.DEFAULT_TRACK_A_LOTS)  # Strict 0.10 Lots
        tp_dist_a = round(target_a / (final_lots_a * contract_size), 2)  # Strictly <= $2.00
        tp_price_a = round(ask_ref + tp_dist_a if side == 'buy' else bid_ref - tp_dist_a, 2)
        sl_price_a = round(ask_ref - sl_dist_a if side == 'buy' else bid_ref + sl_dist_a, 2)
        stop_acceptable_a = (dyn_stop_distance <= 0.12)

        # ── TRACK B: Dynamic Sniper (Strict 0.03 Lots, Max $3.33 Target, Max 12¢ Stop — 1.20x Multiplier Removed) ──
        risk_b = config.DEFAULT_TRACK_B_RISK_LIMIT
        target_b = config.DEFAULT_TRACK_B_PROFIT_TARGET
        sl_dist_b = dyn_stop_distance
        final_lots_b = float(config.DEFAULT_TRACK_B_LOTS)  # Strict 0.03 Lots
        tp_dist_b = round(target_b / (final_lots_b * contract_size), 2)  # Strictly <= $3.33
        tp_price_b = round(ask_ref + tp_dist_b if side == 'buy' else bid_ref - tp_dist_b, 2)
        sl_price_b = round(ask_ref - sl_dist_b if side == 'buy' else bid_ref + sl_dist_b, 2)
        stop_acceptable_b = (dyn_stop_distance <= 0.12)

        # ── TRACK C: Quant Hedge Straddle (Strict 0.03 Lots, Max $3.33 Target, Max 12¢ Stop) ──
        risk_c = config.DEFAULT_TRACK_C_RISK_LIMIT
        target_c = config.DEFAULT_TRACK_C_PROFIT_TARGET
        sl_dist_c = dyn_stop_distance
        final_lots_c = float(config.DEFAULT_TRACK_C_LOTS)  # Strict 0.03 Lots
        tp_dist_c = round(target_c / (final_lots_c * contract_size), 2)  # Strictly <= $3.33
        
        # BUY Leg (Anchored to Ask)
        tp_price_c_long = round(ask_ref + tp_dist_c, 2)
        sl_price_c_long = round(ask_ref - sl_dist_c, 2)

        # SELL Leg (Anchored to Bid)
        tp_price_c_short = round(bid_ref - tp_dist_c, 2)
        sl_price_c_short = round(bid_ref + sl_dist_c, 2)
        stop_acceptable_c = (dyn_stop_distance <= 0.12)

        # Solo & Confluence Evaluations (Gated by per-track candle limit)
        is_unified = getattr(snapshot, 'ready_to_simulate', False)
        is_sweetspot = getattr(snapshot, 'is_sweetspot_ignition', False)
        opening_cleared = getattr(snapshot, 'opening_window_cleared', True)
        wick_ok = getattr(snapshot, 'wick_established', True)
        noise_ok = getattr(snapshot, 'counter_noise_ok', True)
        dir_bias = getattr(snapshot.direction, 'bias', 'mixed')
        p_vel = getattr(snapshot.speed, 'price_velocity', 0.0)
        t_vel = getattr(snapshot.speed, 'tick_velocity', 0.0)
        u_ratio = getattr(snapshot.rejection, 'upper_ratio', 0.0) if side == 'buy' else getattr(snapshot.rejection, 'lower_ratio', 0.0)
        struct = snapshot.structure

        # High-Conviction Breakout Bypass check (Strong velocity, clean 5-D snapshot)
        is_high_conviction = bool((is_unified or is_sweetspot) and (p_vel >= 0.20 or t_vel >= 35.0))

        # ── 1. TRACK A (Solo Scalper $20) ──
        sim_ok_a_base, passes_a = self.run_three_pass_simulation(snapshot, entry_price, tp_dist_a, sl_dist_a, side)
        track_a_solo_ok = bool(sim_ok_a_base and stop_acceptable_a and is_sweetspot and opening_cleared and wick_ok and noise_ok and (dir_bias != 'mixed') and (p_vel >= 0.12 or t_vel >= 25.0) and (u_ratio < 0.35) and (spread_val <= 0.08))
        sim_ok_a = ((is_unified and sim_ok_a_base and stop_acceptable_a) or track_a_solo_ok) and self.can_trade_track('A', candle_time, is_high_conviction)

        # ── 2. TRACK B (Solo Sniper $10) ──
        sim_ok_b_base, passes_b = self.run_three_pass_simulation(snapshot, entry_price, tp_dist_b, sl_dist_b, side)
        track_b_solo_ok = bool(sim_ok_b_base and stop_acceptable_b and is_sweetspot and opening_cleared and wick_ok and noise_ok and (dir_bias != 'mixed') and (spread_val <= 0.08))
        sim_ok_b = ((is_unified and sim_ok_b_base and stop_acceptable_b) or track_b_solo_ok) and self.can_trade_track('B', candle_time, is_high_conviction)

        # ── 3. TRACK C (Quant Straddle $10) — Dedicated Dual-Leg 3-Pass Simulations ──
        sim_ok_c_long, passes_c_long = self.run_three_pass_simulation(snapshot, entry_price, tp_dist_c, sl_dist_c, 'buy')
        sim_ok_c_short, passes_c_short = self.run_three_pass_simulation(snapshot, entry_price, tp_dist_c, sl_dist_c, 'sell')
        sim_ok_c_base = bool(sim_ok_c_long and sim_ok_c_short)
        track_c_solo_ok = bool(sim_ok_c_base and stop_acceptable_c and is_sweetspot and opening_cleared and wick_ok and noise_ok and (p_vel >= 0.12 or t_vel >= 25.0) and (spread_val <= 0.08))
        sim_ok_c = ((is_unified and (sim_ok_a_base or sim_ok_b_base or sim_ok_c_base) and stop_acceptable_c) or track_c_solo_ok) and self.can_trade_track('C', candle_time, is_high_conviction)

        chunk_cap = min(float(config.CHUNK_MAX_LOTS), max_lot)

        meta_dict = {
            'direction_bias': dir_bias,
            'direction_score': round(getattr(snapshot.direction, 'score', 0.0), 3),
            'price_velocity': round(p_vel, 3),
            'tick_velocity': round(t_vel, 1),
            'avg_body_size': round(getattr(snapshot.speed, 'avg_body_size', 0.0), 2),
            'speed_class': getattr(snapshot.speed, 'classification', 'medium'),
            'sweetspot_min': round(getattr(snapshot, 'sweetspot_min', 0.10), 2),
            'sweetspot_max': round(getattr(snapshot, 'sweetspot_max', 0.55), 2),
            'is_sweetspot_ignition': is_sweetspot,
            'directional_displacement': round(getattr(snapshot, 'directional_displacement', 0.0), 2),
            'opening_window_cleared': opening_cleared,
            'wick_established': wick_ok,
            'adverse_noise_dist': round(getattr(snapshot, 'adverse_noise_dist', 0.05), 3),
            'adverse_noise_vel': round(getattr(snapshot, 'adverse_noise_vel', 0.02), 3),
            'spread': round(snapshot.spread, 3),
            'upper_wick_ratio': round(getattr(snapshot.rejection, 'upper_ratio', 0.0), 3),
            'lower_wick_ratio': round(getattr(snapshot.rejection, 'lower_ratio', 0.0), 3),
            'reversal_signs': getattr(snapshot.reversal, 'signs', []),
            'nearest_resistance': getattr(snapshot.structure, 'nearest_resistance', None),
            'nearest_support': getattr(snapshot.structure, 'nearest_support', None),
        }

        track_a_dict = {
            'track_id': 'A',
            'track_name': f'TRACK A: ${target_a:.0f} SCALPER',
            'risk_cap': risk_a,
            'target_profit': target_a,
            'side': side,
            'entry_price': round(entry_price, 2),
            'tp_price': tp_price_a,
            'sl_price': sl_price_a,
            'tp_dist': tp_dist_a,
            'sl_dist': sl_dist_a,
            'total_lots': final_lots_a,
            'chunks': self._slice_lots(final_lots_a, chunk_cap, lot_step, min_lot),
            'simulation_passed': sim_ok_a,
            'simulation_passes': passes_a if sim_ok_a else [],
            'potential_profit': target_a,
            'potential_risk': risk_a,
            'candle_time': candle_time,
            'snapshot_metadata': meta_dict,
        }

        track_b_dict = {
            'track_id': 'B',
            'track_name': f'TRACK B: ${target_b:.0f} SNIPER',
            'risk_cap': risk_b,
            'target_profit': target_b,
            'side': side,
            'entry_price': round(entry_price, 2),
            'tp_price': tp_price_b,
            'sl_price': sl_price_b,
            'tp_dist': tp_dist_b,
            'sl_dist': sl_dist_b,
            'total_lots': final_lots_b,
            'chunks': self._slice_lots(final_lots_b, chunk_cap, lot_step, min_lot),
            'simulation_passed': sim_ok_b,
            'simulation_passes': passes_b if sim_ok_b else [],
            'potential_profit': target_b,
            'potential_risk': risk_b,
            'candle_time': candle_time,
            'snapshot_metadata': meta_dict,
        }

        track_c_buy_dict = {
            'track_id': 'C_BUY',
            'track_name': f'TRACK C: ${target_c:.0f} QUANT HEDGE (BUY LEG)',
            'risk_cap': risk_c,
            'target_profit': target_c,
            'side': 'buy',
            'entry_price': round(entry_price, 2),
            'tp_price': tp_price_c_long,
            'sl_price': sl_price_c_long,
            'tp_dist': tp_dist_c,
            'sl_dist': sl_dist_c,
            'total_lots': final_lots_c,
            'chunks': self._slice_lots(final_lots_c, chunk_cap, lot_step, min_lot),
            'simulation_passed': sim_ok_c,
            'simulation_passes': passes_c_long if sim_ok_c else [],
            'potential_profit': target_c,
            'potential_risk': risk_c,
            'candle_time': candle_time,
            'snapshot_metadata': meta_dict,
        }

        track_c_sell_dict = {
            'track_id': 'C_SELL',
            'track_name': f'TRACK C: ${target_c:.0f} QUANT HEDGE (SELL LEG)',
            'risk_cap': risk_c,
            'target_profit': target_c,
            'side': 'sell',
            'entry_price': round(entry_price, 2),
            'tp_price': tp_price_c_short,
            'sl_price': sl_price_c_short,
            'tp_dist': tp_dist_c,
            'sl_dist': sl_dist_c,
            'total_lots': final_lots_c,
            'chunks': self._slice_lots(final_lots_c, chunk_cap, lot_step, min_lot),
            'simulation_passed': sim_ok_c,
            'simulation_passes': passes_c_short if sim_ok_c else [],
            'potential_profit': target_c,
            'potential_risk': risk_c,
            'candle_time': candle_time,
            'snapshot_metadata': meta_dict,
        }

        ready = sim_ok_a or sim_ok_b or sim_ok_c
        primary_track = 'TRACK A: $200 SCALPER' if sim_ok_a else ('TRACK B: $90 SNIPER' if sim_ok_b else 'TRACK C: $90 QUANT HEDGE')
        tp_primary = tp_price_a if sim_ok_a else (tp_price_b if sim_ok_b else tp_price_c_long)
        sl_primary = sl_price_a if sim_ok_a else (sl_price_b if sim_ok_b else sl_price_c_long)

        return {
            'side': side,
            'entry_price': round(entry_price, 2),
            'ready_to_simulate': ready,
            'timestamp': time.time(),
            'candle_time': candle_time,
            'track_a': track_a_dict,
            'track_b': track_b_dict,
            'track_c_buy': track_c_buy_dict,
            'track_c_sell': track_c_sell_dict,
            'track_name': primary_track,
            'tp_price': tp_primary,
            'sl_price': sl_primary,
            'tp_dist': tp_dist_a,
            'sl_dist': sl_dist_a,
            'total_lots': final_lots_a,
            'potential_profit': target_a,
            'potential_risk': risk_a,
        }

    @property
    def has_active_trade(self) -> bool:
        return len(self.active_simulations) > 0 or len(self.live_positions) > 0

    def manage_open_positions(self, current_price: float):
        """Manages live positions in memory (Breakeven & Profit Ratchet)."""
        if self.live_positions and self.account_manager:
            self._manage_live_in_memory(current_price)

    def register_simulation(self, setup: Dict[str, Any], bid: float = 0.0, ask: float = 0.0):
        """Registers active simulated positions or executes live orders if LIVE_EXECUTION_ENABLED is True."""
        c_ts = setup.get('candle_time', 0)
        if ask <= 0:
            ask = round(bid + 0.08, 2) if bid > 0 else 4450.08
        if bid <= 0:
            bid = round(ask - 0.08, 2)

        # ── LIVE EXECUTION BURST HIGHWAY ──
        if config.LIVE_EXECUTION_ENABLED and self.account_manager:
            self._execute_live_burst(setup)
            return

        # ── SIMULATION MODE WITH VIRTUAL BROKER MATCHING ENGINE ──
        log_dir = Path(__file__).parent.parent / "logs"
        md_file = log_dir / "trade_journal.md"
        t_str = time.strftime("%H:%M:%S")

        track_a = setup.get('track_a')
        if track_a and track_a.get('simulation_passed'):
            pos_a = self.virtual_broker.submit_order(
                track_id='A',
                side=track_a['side'],
                qty=track_a['total_lots'],
                sl_price=track_a['sl_price'],
                tp_price=track_a['tp_price'],
                sl_dist=track_a['sl_dist'],
                tp_dist=track_a['tp_dist'],
                bid=bid,
                ask=ask
            )
            if pos_a:
                self.last_candle_traded['A'] = c_ts
                self.active_simulations.append({
                    'setup': track_a,
                    'pos_id': pos_a['position_id'],
                    'order_id': pos_a['order_id'],
                    'entry_time': time.time(),
                    'status': 'open'
                })
                logger.info(f"[TRACK A] Virtual Broker #{pos_a['order_id']} Filled {track_a['side'].upper()} @ ${pos_a['fill_price']} | TP: {track_a['tp_price']} | SL: {track_a['sl_price']}")
                try:
                    row_entry = f"| {t_str} | `#{pos_a['order_id']}` | {track_a['track_name']} | {track_a['side'].upper()} | {track_a['total_lots']:.2f} | ${pos_a['fill_price']:.2f} | ${track_a['sl_price']:.2f} | ${track_a['tp_price']:.2f} | -- | 0.00 | ${self.virtual_broker.balance:.2f} | ${self.virtual_broker.equity - self.virtual_broker.loss_floor:.2f} | FILLED (OPEN) |\n"
                    with open(md_file, "a", encoding="utf-8") as f:
                        f.write(row_entry)
                except Exception:
                    pass

        track_b = setup.get('track_b')
        if track_b and track_b.get('simulation_passed'):
            pos_b = self.virtual_broker.submit_order(
                track_id='B',
                side=track_b['side'],
                qty=track_b['total_lots'],
                sl_price=track_b['sl_price'],
                tp_price=track_b['tp_price'],
                sl_dist=track_b['sl_dist'],
                tp_dist=track_b['tp_dist'],
                bid=bid,
                ask=ask
            )
            if pos_b:
                self.last_candle_traded['B'] = c_ts
                self.active_simulations.append({
                    'setup': track_b,
                    'pos_id': pos_b['position_id'],
                    'order_id': pos_b['order_id'],
                    'entry_time': time.time(),
                    'status': 'open'
                })
                logger.info(f"[TRACK B] Virtual Broker #{pos_b['order_id']} Filled {track_b['side'].upper()} @ ${pos_b['fill_price']} | TP: {track_b['tp_price']} | SL: {track_b['sl_price']}")
                try:
                    row_entry = f"| {t_str} | `#{pos_b['order_id']}` | {track_b['track_name']} | {track_b['side'].upper()} | {track_b['total_lots']:.2f} | ${pos_b['fill_price']:.2f} | ${track_b['sl_price']:.2f} | ${track_b['tp_price']:.2f} | -- | 0.00 | ${self.virtual_broker.balance:.2f} | ${self.virtual_broker.equity - self.virtual_broker.loss_floor:.2f} | FILLED (OPEN) |\n"
                    with open(md_file, "a", encoding="utf-8") as f:
                        f.write(row_entry)
                except Exception:
                    pass

        track_c_buy = setup.get('track_c_buy')
        track_c_sell = setup.get('track_c_sell')
        if track_c_buy and track_c_buy.get('simulation_passed'):
            pos_cb = self.virtual_broker.submit_order(
                track_id='C',
                side='buy',
                qty=track_c_buy['total_lots'],
                sl_price=track_c_buy['sl_price'],
                tp_price=track_c_buy['tp_price'],
                sl_dist=track_c_buy['sl_dist'],
                tp_dist=track_c_buy['tp_dist'],
                bid=bid,
                ask=ask
            )
            pos_cs = self.virtual_broker.submit_order(
                track_id='C',
                side='sell',
                qty=track_c_sell['total_lots'],
                sl_price=track_c_sell['sl_price'],
                tp_price=track_c_sell['tp_price'],
                sl_dist=track_c_sell['sl_dist'],
                tp_dist=track_c_sell['tp_dist'],
                bid=bid,
                ask=ask
            )
            if pos_cb and pos_cs:
                self.last_candle_traded['C'] = c_ts
                self.active_simulations.append({'setup': track_c_buy, 'pos_id': pos_cb['position_id'], 'order_id': pos_cb['order_id'], 'entry_time': time.time(), 'status': 'open'})
                self.active_simulations.append({'setup': track_c_sell, 'pos_id': pos_cs['position_id'], 'order_id': pos_cs['order_id'], 'entry_time': time.time(), 'status': 'open'})
                logger.info(f"[TRACK C] Virtual Broker DUAL STRADDLE Filled (BUY #{pos_cb['order_id']} @ ${pos_cb['fill_price']} | SELL #{pos_cs['order_id']} @ ${pos_cs['fill_price']})")
                try:
                    row_cb = f"| {t_str} | `#{pos_cb['order_id']}` | {track_c_buy['track_name']} | BUY | {track_c_buy['total_lots']:.2f} | ${pos_cb['fill_price']:.2f} | ${track_c_buy['sl_price']:.2f} | ${track_c_buy['tp_price']:.2f} | -- | 0.00 | ${self.virtual_broker.balance:.2f} | ${self.virtual_broker.equity - self.virtual_broker.loss_floor:.2f} | FILLED (OPEN) |\n"
                    row_cs = f"| {t_str} | `#{pos_cs['order_id']}` | {track_c_sell['track_name']} | SELL | {track_c_sell['total_lots']:.2f} | ${pos_cs['fill_price']:.2f} | ${track_c_sell['sl_price']:.2f} | ${track_c_sell['tp_price']:.2f} | -- | 0.00 | ${self.virtual_broker.balance:.2f} | ${self.virtual_broker.equity - self.virtual_broker.loss_floor:.2f} | FILLED (OPEN) |\n"
                    with open(md_file, "a", encoding="utf-8") as f:
                        f.write(row_cb)
                        f.write(row_cs)
                except Exception:
                    pass

    def _execute_live_burst(self, setup: Dict[str, Any]):
        """Zero-Latency Live Execution Burst across all active accounts."""
        c_ts = setup.get('candle_time', 0)

        # 1. Fire Track A Orders
        track_a = setup.get('track_a')
        res_a = []
        if track_a and track_a.get('simulation_passed'):
            res_a = self.account_manager.execute_live_order_burst(
                track_id='A',
                side=track_a['side'],
                sl_price=track_a['sl_price'],
                tp_price=track_a['tp_price']
            )
            if res_a:
                self.last_candle_traded['A'] = c_ts
            for r in res_a:
                entry_a = r.get('fill_price') or track_a['entry_price']
                self.live_positions[str(r['order_id'])] = {
                    'account_id': r['account_id'],
                    'order_id': r['order_id'],
                    'position_id': r.get('position_id', r['order_id']),
                    'track_id': 'A',
                    'side': r['side'],
                    'entry_price': entry_a,
                    'sl_dist': track_a['sl_dist'],
                    'tp_dist': track_a['tp_dist'],
                    'entry_time': time.time(),
                    'be_active': False,
                    'profit_locked': False,
                }

        # 2. Fire Track B Orders
        track_b = setup.get('track_b')
        res_b = []
        if track_b and track_b.get('simulation_passed'):
            res_b = self.account_manager.execute_live_order_burst(
                track_id='B',
                side=track_b['side'],
                sl_price=track_b['sl_price'],
                tp_price=track_b['tp_price']
            )
            if res_b:
                self.last_candle_traded['B'] = c_ts
            for r in res_b:
                entry_b = r.get('fill_price') or track_b['entry_price']
                self.live_positions[str(r['order_id'])] = {
                    'account_id': r['account_id'],
                    'order_id': r['order_id'],
                    'position_id': r.get('position_id', r['order_id']),
                    'track_id': 'B',
                    'side': r['side'],
                    'entry_price': entry_b,
                    'sl_dist': track_b['sl_dist'],
                    'tp_dist': track_b['tp_dist'],
                    'entry_time': time.time(),
                    'be_active': False,
                    'profit_locked': False,
                }

        # 3. Fire Track C Orders (Dual Straddle Hedge)
        track_c_buy = setup.get('track_c_buy')
        res_cb = []
        if track_c_buy and track_c_buy.get('simulation_passed'):
            res_cb = self.account_manager.execute_live_order_burst(
                track_id='C',
                side='buy',
                sl_price=track_c_buy['sl_price'],
                tp_price=track_c_buy['tp_price']
            )
            if res_cb:
                self.last_candle_traded['C'] = c_ts
            for r in res_cb:
                entry_cb = r.get('fill_price') or track_c_buy['entry_price']
                self.live_positions[str(r['order_id'])] = {
                    'account_id': r['account_id'],
                    'order_id': r['order_id'],
                    'position_id': r.get('position_id', r['order_id']),
                    'track_id': 'C',
                    'side': 'buy',
                    'entry_price': entry_cb,
                    'sl_dist': track_c_buy['sl_dist'],
                    'tp_dist': track_c_buy['tp_dist'],
                    'entry_time': time.time(),
                    'be_active': False,
                    'profit_locked': False,
                }

        track_c_sell = setup.get('track_c_sell')
        res_cs = []
        if track_c_sell and track_c_sell.get('simulation_passed'):
            res_cs = self.account_manager.execute_live_order_burst(
                track_id='C',
                side='sell',
                sl_price=track_c_sell['sl_price'],
                tp_price=track_c_sell['tp_price']
            )
            if res_cs:
                self.last_candle_traded['C'] = c_ts
            for r in res_cs:
                entry_cs = r.get('fill_price') or track_c_sell['entry_price']
                self.live_positions[str(r['order_id'])] = {
                    'account_id': r['account_id'],
                    'order_id': r['order_id'],
                    'position_id': r.get('position_id', r['order_id']),
                    'track_id': 'C',
                    'side': 'sell',
                    'entry_price': entry_cs,
                    'sl_dist': track_c_sell['sl_dist'],
                    'tp_dist': track_c_sell['tp_dist'],
                    'entry_time': time.time(),
                    'be_active': False,
                    'profit_locked': False,
                }

        # Attach confirmed live orders to active_simulations for real-time chart feed outcome monitoring
        if res_a:
            self.active_simulations.append({'setup': track_a, 'entry_time': time.time(), 'status': 'open', 'is_live': True})
            logger.info(f"[LIVE TRACK A] Confirmed Order Active on Broker & Chart Monitor")
        if res_b:
            self.active_simulations.append({'setup': track_b, 'entry_time': time.time(), 'status': 'open', 'is_live': True})
            logger.info(f"[LIVE TRACK B] Confirmed Order Active on Broker & Chart Monitor")
        if res_cb:
            self.active_simulations.append({'setup': track_c_buy, 'entry_time': time.time(), 'status': 'open', 'is_live': True})
            logger.info(f"[LIVE TRACK C BUY] Confirmed Order Active on Broker & Chart Monitor")
        if res_cs:
            self.active_simulations.append({'setup': track_c_sell, 'entry_time': time.time(), 'status': 'open', 'is_live': True})
            logger.info(f"[LIVE TRACK C SELL] Confirmed Order Active on Broker & Chart Monitor")

        # Log Live Order Transmission Audit to Trade Journal
        try:
            log_dir = Path(__file__).parent.parent / "logs"
            log_dir.mkdir(exist_ok=True)
            md_file = log_dir / "trade_journal.md"
            t_str = time.strftime("%Y-%m-%d %H:%M:%S")
            
            if self.live_positions:
                audit_msg = f"\n> 🟢 **LIVE BROKER ORDERS FILLED ({t_str})**:\n"
                for pos in self.live_positions.values():
                    audit_msg += f"> - **[{pos['track_id']}]** {pos['side'].upper()} filled on Broker | Order ID: `#{pos['order_id']}` | Entry: `${pos['entry_price']:.2f}`\n"
                audit_msg += "\n---\n"
            else:
                audit_msg = f"\n> ⚠️ **LIVE ORDER PLACEMENT REJECTED / BLOCKED ({t_str})**: Broker returned 0 fills (Rate limit / Margin block). Memory lock reset for next candle.\n\n---\n"

            with open(md_file, "a", encoding="utf-8") as f:
                f.write(audit_msg)
        except Exception:
            pass

        # If all order bursts failed (e.g. Cloudflare / Margin block), reset lock so next setup can execute
        if not self.live_positions:
            self.last_traded_candle_ts = 0

    def update_simulated_positions(self, bid: float, ask: float = None) -> List[Dict[str, Any]]:
        """Checks outcomes for both simulation and live in-memory positions using live dual Bid/Ask orderbook pricing."""
        if ask is None or ask <= 0:
            ask = round(bid + 0.08, 2)

        # Check Live Positions in Memory for Breakeven & Profit Ratchet modifications on Broker
        if self.live_positions and self.account_manager:
            self._manage_live_in_memory(bid)

        # Update Virtual Broker ticks and Prop Firm Floor monitor
        vb_state = self.virtual_broker.update_ticks(bid, ask)

        outcomes = []
        remaining = []
        for sim in self.active_simulations:
            setup = sim['setup']
            side = setup['side']
            tp = setup['tp_price']
            entry = setup['entry_price']
            entry_time = sim['entry_time']
            duration = round(time.time() - entry_time, 1)
            t_name = setup.get('track_name', 'TRADE')

            # Real Dual Bid/Ask Pricing:
            # BUY positions hit TP at Bid, hit SL at Bid
            # SELL positions hit TP at Ask, hit SL at Ask
            eval_price_tp = bid if side == 'buy' else ask
            eval_price_sl = bid if side == 'buy' else ask
            favorable_move = (bid - entry) if side == 'buy' else (entry - ask)

            # Breakeven Shift
            be_threshold = round(max(0.04, setup.get('sl_dist', 0.08) * 0.85), 2)
            if not sim.get('be_active', False) and favorable_move >= be_threshold:
                sim['be_active'] = True
                sim['setup']['sl_price'] = entry
                logger.info(f"[{t_name}] [BREAKEVEN] ACTIVATED @ Bid:{bid} Ask:{ask} -> SL to Entry ${entry:.2f}")

            # Tier-2 Profit Ratchet
            tp_dist = setup.get('tp_dist', 2.0)
            if favorable_move >= (tp_dist * 0.45) and not sim.get('profit_locked', False):
                sim['profit_locked'] = True
                sim['locked_pnl'] = round(setup['potential_profit'] * 0.25, 2)
                sim['setup']['sl_price'] = round(entry + (tp_dist * 0.25) if side == 'buy' else entry - (tp_dist * 0.25), 2)
                logger.info(f"[{t_name}] [RATCHET] PROFIT LOCKED @ Bid:{bid} Ask:{ask} -> SL to ${sim['setup']['sl_price']:.2f}")

            curr_sl = sim['setup']['sl_price']
            hit_tp = (eval_price_tp >= tp) if side == 'buy' else (eval_price_tp <= tp)
            hit_sl = (eval_price_sl <= curr_sl) if side == 'buy' else (eval_price_sl >= curr_sl)

            exit_price = eval_price_tp if hit_tp else eval_price_sl

            if hit_tp:
                self.cooldown_until = time.time() + 20.0
                close_res = self.virtual_broker.close_position(pos_id=sim.get('pos_id', ''), exit_price=round(exit_price, 2), reason='WIN_TP')
                pnl_actual = close_res.get('net_pnl', setup['potential_profit'])

                out_dict = {
                    'outcome': 'WIN_TP',
                    'setup': setup,
                    'close_order_id': close_res.get('close_order_id', sim.get('order_id', 'SIM-ORD')),
                    'entry_order_id': sim.get('order_id', 'SIM-ORD'),
                    'close_side': ('SELL' if setup.get('side') == 'buy' else 'BUY'),
                    'exit_price': round(exit_price, 2),
                    'duration_sec': duration,
                    'pnl': pnl_actual,
                    'virtual_balance': self.virtual_broker.balance,
                    'virtual_equity': self.virtual_broker.equity,
                    'buffer_to_floor': round(self.virtual_broker.equity - self.virtual_broker.loss_floor, 2),
                    'timestamp': time.time(),
                }
                outcomes.append(out_dict)
                
                # Archive Golden Setup parameters only for WIN_TP trades
                self._log_winning_trade_parameters(setup, out_dict)

                # Clear live position tracking & unlock engine
                if sim.get('is_live'):
                    self.live_positions.clear()
                    self.last_traded_candle_ts = 0
            elif hit_sl:
                is_be = sim.get('be_active', False)
                is_lock = sim.get('profit_locked', False)
                self.cooldown_until = time.time() + (15.0 if is_be else 30.0)
                out_type = 'WIN_PROFIT_LOCK' if is_lock else ('BREAKEVEN_EXIT' if is_be else 'LOSS_SL')
                
                close_res = self.virtual_broker.close_position(pos_id=sim.get('pos_id', ''), exit_price=round(exit_price, 2), reason=out_type)
                pnl_val = close_res.get('net_pnl', (sim.get('locked_pnl', round(setup['potential_profit'] * 0.25, 2)) if is_lock else (0.0 if is_be else -setup['potential_risk'])))
                
                # If hard loss on stop loss, lock candle from duplicate churn
                if out_type == 'LOSS_SL':
                    c_ts = setup.get('candle_time', 0)
                    if c_ts:
                        self.failed_candle_ts = c_ts
                        self.cooldown_candle_ts = c_ts
                        logger.info(f"[COOLDOWN] Loss registered on candle #{c_ts}. Candle locked to prevent churn (Active analysis continuing).")

                outcomes.append({
                    'outcome': out_type,
                    'setup': setup,
                    'close_order_id': close_res.get('close_order_id', sim.get('order_id', 'SIM-ORD')),
                    'entry_order_id': sim.get('order_id', 'SIM-ORD'),
                    'close_side': ('SELL' if setup.get('side') == 'buy' else 'BUY'),
                    'exit_price': round(exit_price, 2),
                    'duration_sec': duration,
                    'pnl': pnl_val,
                    'virtual_balance': self.virtual_broker.balance,
                    'virtual_equity': self.virtual_broker.equity,
                    'buffer_to_floor': round(self.virtual_broker.equity - self.virtual_broker.loss_floor, 2),
                    'timestamp': time.time(),
                })
                # Clear live position tracking & unlock engine
                if sim.get('is_live'):
                    self.live_positions.clear()
                    self.last_traded_candle_ts = 0
            else:
                remaining.append(sim)

        self.active_simulations = remaining

        # Append Transaction Audit Rows to trade_journal.md
        for out in outcomes:
            try:
                log_dir = Path(__file__).parent.parent / "logs"
                md_file = log_dir / "trade_journal.md"
                t_str = time.strftime("%H:%M:%S")
                setup = out['setup']
                oid = out.get('close_order_id', 'SIM-ORD')
                t_name = setup.get('track_name', setup.get('track_id', 'A'))
                c_side = out.get('close_side', 'SELL')
                qty = setup.get('total_lots', 0.03)
                entry_p = setup.get('entry_price', 0.0)
                sl_p = setup.get('sl_price', 0.0)
                tp_p = setup.get('tp_price', 0.0)
                exit_p = out.get('exit_price', 0.0)
                pnl = out.get('pnl', 0.0)
                bal = out.get('virtual_balance', self.virtual_broker.balance)
                buf = out.get('buffer_to_floor', round(bal - self.virtual_broker.loss_floor, 2))
                status = out.get('outcome', 'CLOSED')

                row = f"| {t_str} | `#{oid}` | {t_name} | {c_side} | {qty:.2f} | ${entry_p:.2f} | ${sl_p:.2f} | ${tp_p:.2f} | ${exit_p:.2f} | {pnl:+.2f} | ${bal:.2f} | ${buf:.2f} | {status} |\n"
                with open(md_file, "a", encoding="utf-8") as f:
                    f.write(row)
            except Exception:
                pass

        return outcomes

    def _manage_live_in_memory(self, current_price: float):
        """In-memory checks for live broker positions to trigger Breakeven & Profit Ratchet."""
        mods = []
        for pos_key, pos in list(self.live_positions.items()):
            side = pos['side']
            entry = pos['entry_price']
            sl_dist = pos['sl_dist']
            tp_dist = pos['tp_dist']
            favorable_move = (current_price - entry) if side == 'buy' else (entry - current_price)

            # 1. Live Breakeven Modification
            if not pos['be_active'] and favorable_move >= (sl_dist * 0.85):
                pos['be_active'] = True
                mods.append({
                    'account_id': pos['account_id'],
                    'pos_id': pos.get('position_id', pos['order_id']),
                    'new_sl': round(entry, 2)
                })

            # 2. Live Tier-2 Profit Ratchet Modification
            if not pos['profit_locked'] and favorable_move >= (tp_dist * 0.45):
                pos['profit_locked'] = True
                lock_sl = round(entry + (tp_dist * 0.25) if side == 'buy' else entry - (tp_dist * 0.25), 2)
                mods.append({
                    'account_id': pos['account_id'],
                    'pos_id': pos.get('position_id', pos['order_id']),
                    'new_sl': lock_sl
                })

        if mods:
            self.account_manager.modify_live_sl_burst(mods)

    def _log_winning_trade_parameters(self, setup: dict, out: dict):
        """Archives all entry parameters for WIN_TP trades into dedicated analytics files."""
        try:
            log_dir = Path(__file__).parent.parent / "logs"
            log_dir.mkdir(exist_ok=True)
            
            now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            meta = setup.get('snapshot_metadata', {})
            t_name = setup.get('track_name', setup.get('track_id', 'A'))
            
            winning_entry = {
                'closed_at_utc': now_utc,
                'track_name': t_name,
                'track_id': setup.get('track_id'),
                'side': setup.get('side', 'buy').upper(),
                'entry_order_id': out.get('entry_order_id'),
                'close_order_id': out.get('close_order_id'),
                'entry_price': setup.get('entry_price'),
                'exit_price': out.get('exit_price'),
                'tp_target_price': setup.get('tp_price'),
                'sl_price': setup.get('sl_price'),
                'lots': setup.get('total_lots'),
                'net_pnl': out.get('pnl'),
                'trade_duration_sec': out.get('duration_sec'),
                'market_parameters_at_entry': meta
            }
            
            # 1. JSONL Append for quantitative ML / backtesting analysis
            jsonl_file = log_dir / "winning_trade_parameters.jsonl"
            with open(jsonl_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(winning_entry) + "\n")
                
            # 2. Rich Markdown Append for human visual review
            md_file = log_dir / "winning_setups_analysis.md"
            if not md_file.exists():
                with open(md_file, "w", encoding="utf-8") as f:
                    f.write("# Edge Labs -- Winning Trade Parameters Archive\n\nArchive of all high-conviction entries that successfully achieved full Take Profit.\n\n---\n\n")
            
            md_card = f"""### [{t_name}] {winning_entry['side']} WIN (+${winning_entry['net_pnl']:.2f}) -- {now_utc}
- **Execution:** Entry `${winning_entry['entry_price']:.2f}` | Exit `${winning_entry['exit_price']:.2f}` | Lots: `{winning_entry['lots']:.2f}L` | Duration: `{winning_entry['trade_duration_sec']}s`
- **Orders:** Entry `#{winning_entry['entry_order_id']}` -> Liquidation `#{winning_entry['close_order_id']}`
- **Speed & Velocity:** Price Velocity: `{meta.get('price_velocity', 0)} $/min` | Tick Velocity: `{meta.get('tick_velocity', 0)} ticks/min` | Speed Class: `{meta.get('speed_class', 'medium')}`
- **Sweet-Spot Ignition:** Range: `${meta.get('sweetspot_min', 0)} - ${meta.get('sweetspot_max', 0)}` | Ignited: `{meta.get('is_sweetspot_ignition', True)}`
- **Noise & Friction:** Measured Counter-Noise: `{meta.get('adverse_noise_dist', 0)} USD` | Adverse Vel: `{meta.get('adverse_noise_vel', 0)}/s` | Spread: `{meta.get('spread', 0)} USD`
- **Orderflow & Airflow:** Direction Score: `{meta.get('direction_score', 0)}` ({meta.get('direction_bias', 'none')}) | Upper Wick Drag: `{meta.get('upper_wick_ratio', 0)}` | Lower Wick Drag: `{meta.get('lower_wick_ratio', 0)}`
- **Structure Clearance:** Nearest Resistance: `{meta.get('nearest_resistance')}` | Nearest Support: `{meta.get('nearest_support')}`

---

"""
            with open(md_file, "a", encoding="utf-8") as f:
                f.write(md_card)
        except Exception as e:
            logger.warning(f"Failed to log winning trade parameters: {e}")
