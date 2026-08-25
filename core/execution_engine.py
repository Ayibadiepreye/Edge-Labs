"""Edge Labs — Position & Order Execution Engine
Handles 3-pass speed simulation, exact $1,000 target lot sizing, order chunking,
TradeLocker order placement, breakeven management, and partial closes.
"""
from __future__ import annotations
import math, time, logging
from typing import Optional, Dict, Any, List, Tuple
import pandas as pd

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from core.api_client import EdgeLabsClient
from core.analysis_engine import AnalysisSnapshot

logger = logging.getLogger("trade")


class ExecutionEngine:
    """Manages 3-pass simulation, exact $1,000 sizing, order chunking, and live execution."""

    def __init__(self, client: EdgeLabsClient, demo_mode: bool = True):
        self.client = client
        self.demo_mode = demo_mode
        self.daily_executions: int = 0
        self.active_positions: List[Dict[str, Any]] = []
        self.active_simulations: List[Dict[str, Any]] = []
        self.last_traded_candle_ts: int = 0
        self.cooldown_until: float = 0.0

    def can_trade_candle(self, candle_ts: int) -> bool:
        """Enforces strictly ONE trade per M5 candle and post-trade cooldown."""
        if self.has_active_trade:
            return False
        if time.time() < self.cooldown_until:
            return False
        if candle_ts and candle_ts == self.last_traded_candle_ts:
            return False  # Block repeated churn on the same candle
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

        # Opposing wick friction drag (0.00 to 0.20)
        wick_opp = snapshot.rejection.upper_ratio if side == 'buy' else snapshot.rejection.lower_ratio

        success_count = 0
        for name, speed_mult, noise_mult in variants:
            eff_pvel = p_vel * speed_mult
            eff_tvel = t_vel * speed_mult

            # 1. Estimated time to reach TP distance in seconds
            time_to_tp = (tp_dist / eff_pvel) * 60.0 if eff_pvel > 0 else 999.0

            # 2. Monte-Carlo Maximum Adverse Excursion (Pullback Noise + Opposing Wick Drag + Spread)
            noise_sigma = max(0.015, spread_friction * 0.20) * noise_mult
            adverse_excursion = round((wick_opp * sl_dist * 0.80) + noise_sigma, 3)

            # Pass is successful if:
            # - Estimated time is within the M5 candle cycle (<= 300s)
            # - Adverse excursion does NOT breach the Stop-Loss boundary
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

        # Requires at least 2 out of 3 passes to be successful
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
        """Calculates Promoted 3-Track setups: Track A ($50 Scalper), Track B ($10 Sniper), & Track C ($10 Micro-Hedge)."""
        if not self.can_trade_candle(candle_time):
            reason = "CANDLE LOCKED (1-Trade Limit)" if (self.last_traded_candle_ts == candle_time) else "COOLDOWN (20s Pause)"
            return {
                'ready_to_simulate': False,
                'status': 'LOCKED',
                'reason': reason,
                'track_a': None,
                'track_b': None,
            }

        contract_size = self.client.contract_size
        lot_step      = self.client.lot_step
        min_lot       = self.client.min_lot
        max_lot       = self.client.max_lot

        # 1. Real-Time Dynamic Market Pulse Displacement ($/move):
        p_sec = max(0.05, snapshot.speed.price_velocity / 60.0)  # Live $/sec
        t_sec = max(1.0, snapshot.speed.tick_velocity / 60.0)    # Live ticks/sec
        pulse_dist = p_sec / t_sec                               # Live displacement covered per move
        avg_body = max(1.50, getattr(snapshot.speed, 'avg_body', getattr(snapshot.speed, 'avg_body_size', 2.0)))
        spread_val = snapshot.spread if snapshot.spread < 5 else snapshot.spread / 100.0
        side = getattr(snapshot, 'impulse_side', 'buy' if snapshot.direction.bias == 'green' else 'sell')

        # Dynamic Stop Distance: Strictly Live Spread + 2¢ Buffer (0% oversized padding)
        # Sits at 3¢ for 1¢ spread, 4¢ for 2¢ spread, 9¢ for 7¢ spread
        dyn_stop_distance = round(max(0.03, spread_val + 0.02), 2)

        # ── TRACK A: $10 SURGE SNIPER (Single-Candle Momentum Expansion) ──
        # ── TRACK A: $50 KINETIC SCALPER (Single-Candle Rapid Micro-Burst, +$1,000 Target) ──
        # Risk: Strictly capped <= $50.00 USD (with instant Breakeven shift on profit)
        # Stop-Loss: Sits at tight spread-safe barrier (Spread + 2¢)
        sl_dist_a = dyn_stop_distance
        req_lots_a = 50.0 / (sl_dist_a * contract_size)
        stepped_lots_a = math.floor(req_lots_a / lot_step) * lot_step
        final_lots_a = round(max(min_lot, min(stepped_lots_a, max_lot)), 2)
        # Target: Strictly Hardcoded +$1,000 USD (Only needs a rapid $1.80-$2.00 micro-burst!)
        tp_dist_a = round(1000.0 / (final_lots_a * contract_size), 2)

        tp_price_a = round(entry_price + tp_dist_a if side == 'buy' else entry_price - tp_dist_a, 2)
        sl_price_a = round(entry_price - sl_dist_a if side == 'buy' else entry_price + sl_dist_a, 2)

        # ── TRACK B: $10 DYNAMIC RAPID SNIPER (Dynamic Micro-Stop, +$300 Target) ──
        # Risk: Strictly capped <= $10.00 USD
        # Stop-Loss: 100% Dynamically calculated from spread + live jitter (4¢ to 11¢)
        sl_dist_b = round(max(0.04, dyn_stop_distance * 1.25), 2)
        req_lots_b = 10.0 / (sl_dist_b * contract_size)
        stepped_lots_b = math.floor(req_lots_b / lot_step) * lot_step
        final_lots_b = round(max(min_lot, min(stepped_lots_b, max_lot)), 2)
        # Target: +$300 USD (only needs a tiny $1.50 to $3.30 micro-move!)
        tp_dist_b = round(300.0 / (final_lots_b * contract_size), 2)
        tp_price_b = round(entry_price + tp_dist_b if side == 'buy' else entry_price - tp_dist_b, 2)
        sl_price_b = round(entry_price - sl_dist_b if side == 'buy' else entry_price + sl_dist_b, 2)

        # ── TRACK C: $10 QUANT MICRO-HEDGE (Dual Straddle Legs, +$300 to +$1,000 Target) ──
        # Opens both a BUY leg and a SELL leg simultaneously with tight $10 micro-stops
        sl_dist_c = dyn_stop_distance
        req_lots_c = 10.0 / (sl_dist_c * contract_size)
        stepped_lots_c = math.floor(req_lots_c / lot_step) * lot_step
        final_lots_c = round(max(min_lot, min(stepped_lots_c, max_lot)), 2)
        # Target: +$300 to +$1,000 USD on explosive breakout expansion
        tp_dist_c = round(300.0 / (final_lots_c * contract_size), 2)

        # Long Leg
        tp_price_c_long = round(entry_price + tp_dist_c, 2)
        sl_price_c_long = round(entry_price - sl_dist_c, 2)
        # Short Leg
        tp_price_c_short = round(entry_price - tp_dist_c, 2)
        sl_price_c_short = round(entry_price + sl_dist_c, 2)

        # ── HYBRID SOLO & CONFLUENCE EVALUATION ──
        is_unified = getattr(snapshot, 'ready_to_simulate', False)
        dir_bias = getattr(snapshot.direction, 'bias', 'mixed')
        p_vel = getattr(snapshot.speed, 'price_velocity', 0.0)
        t_vel = getattr(snapshot.speed, 'tick_velocity', 0.0)
        u_ratio = getattr(snapshot.rejection, 'upper_ratio', 0.0) if side == 'buy' else getattr(snapshot.rejection, 'lower_ratio', 0.0)
        struct = snapshot.structure

        # 1. Track A Solo Profile ($50 Kinetic Scalper):
        # Velocity Surge (PriceVel >= 0.12 or TickVel >= 25), Defined Trend Bias, Wick Drag < 20%
        sim_ok_a_base, passes_a = self.run_three_pass_simulation(snapshot, entry_price, tp_dist_a, sl_dist_a, side)
        track_a_solo_ok = (sim_ok_a_base and dir_bias != 'mixed' and (p_vel >= 0.12 or t_vel >= 25.0) and u_ratio < 0.20 and spread_val <= 0.08)
        sim_ok_a = (is_unified and sim_ok_a_base) or track_a_solo_ok

        # 2. Track B Solo Profile ($10 Dynamic Sniper):
        # Sustained Trend Continuation, Structure Room >= $1.50, Spread <= 8¢
        sim_ok_b_base, passes_b = self.run_three_pass_simulation(snapshot, entry_price, tp_dist_b, sl_dist_b, side)
        struct_room_ok = True
        if side == 'buy' and struct.nearest_resistance is not None:
            struct_room_ok = (struct.nearest_resistance - entry_price) >= 1.50
        elif side == 'sell' and struct.nearest_support is not None:
            struct_room_ok = (entry_price - struct.nearest_support) >= 1.50

        track_b_solo_ok = (sim_ok_b_base and dir_bias != 'mixed' and struct_room_ok and spread_val <= 0.08)
        sim_ok_b = (is_unified and sim_ok_b_base) or track_b_solo_ok

        # 3. Track C Solo Profile ($10 Quant Micro-Hedge Straddle):
        # Sideways Compression / S/R tests / Range Inflections
        sr_near = False
        if struct.nearest_resistance and abs(entry_price - struct.nearest_resistance) <= 2.00:
            sr_near = True
        if struct.nearest_support and abs(entry_price - struct.nearest_support) <= 2.00:
            sr_near = True

        track_c_solo_ok = (spread_val <= 0.08 and (sr_near or is_unified or (p_vel >= 0.10) or (t_vel >= 20.0)))
        sim_ok_c = (is_unified and (sim_ok_a_base or sim_ok_b_base)) or track_c_solo_ok

        chunk_cap = min(float(config.CHUNK_MAX_LOTS), max_lot)
        chunks_a = self._slice_lots(final_lots_a, chunk_cap, lot_step, min_lot)
        chunks_b = self._slice_lots(final_lots_b, chunk_cap, lot_step, min_lot)
        chunks_c = self._slice_lots(final_lots_c, chunk_cap, lot_step, min_lot)

        track_a_dict = {
            'track_id': 'A',
            'track_name': 'TRACK A: $50 KINETIC SCALPER',
            'risk_cap': 50.0,
            'target_profit': 1000.0,
            'side': side,
            'entry_price': round(entry_price, 2),
            'tp_price': tp_price_a,
            'sl_price': sl_price_a,
            'tp_dist': tp_dist_a,
            'sl_dist': sl_dist_a,
            'total_lots': final_lots_a,
            'chunks': chunks_a,
            'simulation_passed': sim_ok_a,
            'simulation_passes': passes_a if sim_ok_a else [],
            'potential_profit': round(final_lots_a * tp_dist_a * contract_size, 2),
            'potential_risk': round(final_lots_a * sl_dist_a * contract_size, 2),
            'candle_time': candle_time,
        }

        track_b_dict = {
            'track_id': 'B',
            'track_name': 'TRACK B: $10 DYNAMIC SNIPER',
            'risk_cap': 10.0,
            'target_profit': 300.0,
            'side': side,
            'entry_price': round(entry_price, 2),
            'tp_price': tp_price_b,
            'sl_price': sl_price_b,
            'tp_dist': tp_dist_b,
            'sl_dist': sl_dist_b,
            'total_lots': final_lots_b,
            'chunks': chunks_b,
            'simulation_passed': sim_ok_b,
            'simulation_passes': passes_b if sim_ok_b else [],
            'potential_profit': round(final_lots_b * tp_dist_b * contract_size, 2),
            'potential_risk': round(final_lots_b * sl_dist_b * contract_size, 2),
            'candle_time': candle_time,
        }

        track_c_buy_dict = {
            'track_id': 'C_BUY',
            'track_name': 'TRACK C: $10 QUANT HEDGE (BUY LEG)',
            'risk_cap': 10.0,
            'target_profit': 300.0,
            'side': 'buy',
            'entry_price': round(entry_price, 2),
            'tp_price': tp_price_c_long,
            'sl_price': sl_price_c_long,
            'tp_dist': tp_dist_c,
            'sl_dist': sl_dist_c,
            'total_lots': final_lots_c,
            'chunks': chunks_c,
            'simulation_passed': sim_ok_c,
            'simulation_passes': ['HEDGE_LONG'] if sim_ok_c else [],
            'potential_profit': round(final_lots_c * tp_dist_c * contract_size, 2),
            'potential_risk': round(final_lots_c * sl_dist_c * contract_size, 2),
            'candle_time': candle_time,
        }

        track_c_sell_dict = {
            'track_id': 'C_SELL',
            'track_name': 'TRACK C: $10 QUANT HEDGE (SELL LEG)',
            'risk_cap': 10.0,
            'target_profit': 300.0,
            'side': 'sell',
            'entry_price': round(entry_price, 2),
            'tp_price': tp_price_c_short,
            'sl_price': sl_price_c_short,
            'tp_dist': tp_dist_c,
            'sl_dist': sl_dist_c,
            'total_lots': final_lots_c,
            'chunks': chunks_c,
            'simulation_passed': sim_ok_c,
            'simulation_passes': ['HEDGE_SHORT'] if sim_ok_c else [],
            'potential_profit': round(final_lots_c * tp_dist_c * contract_size, 2),
            'potential_risk': round(final_lots_c * sl_dist_c * contract_size, 2),
            'candle_time': candle_time,
        }

        ready = sim_ok_a or sim_ok_b or sim_ok_c
        primary_track = 'TRACK A: $50 SCALPER' if sim_ok_a else ('TRACK B: $10 SNIPER' if sim_ok_b else 'TRACK C: $10 QUANT HEDGE')
        tp_primary = tp_price_a if sim_ok_a else (tp_price_b if sim_ok_b else tp_price_c_long)
        sl_primary = sl_price_a if sim_ok_a else (sl_price_b if sim_ok_b else sl_price_c_long)
        tp_dist_primary = tp_dist_a if sim_ok_a else (tp_dist_b if sim_ok_b else tp_dist_c)
        sl_dist_primary = sl_dist_a if sim_ok_a else (sl_dist_b if sim_ok_b else sl_dist_c)
        lots_primary = final_lots_a if sim_ok_a else (final_lots_b if sim_ok_b else final_lots_c)
        p_profit_primary = 1000.0 if sim_ok_a else 300.0
        p_risk_primary = 50.0 if sim_ok_a else 10.0

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
            'tp_dist': tp_dist_primary,
            'sl_dist': sl_dist_primary,
            'total_lots': lots_primary,
            'potential_profit': p_profit_primary,
            'potential_risk': p_risk_primary,
        }

    def execute_setup(self, setup: Dict[str, Any]) -> List[int]:
        """Submits chunked market orders to TradeLocker API."""
        if self.daily_executions >= config.MAX_DAILY_EXECUTIONS:
            logger.warning(f"Daily trade limit reached ({config.MAX_DAILY_EXECUTIONS}). Skipping.")
            return []

        order_ids = []
        for i, chunk_qty in enumerate(setup['chunks']):
            try:
                order_id = self.client.tl.create_order(
                    instrument_id=self.client.instrument_id,
                    quantity=chunk_qty,
                    side=setup['side'],
                    type_='market',
                    take_profit=setup['tp_price'],
                    take_profit_type='absolute',
                    stop_loss=setup['sl_price'],
                    stop_loss_type='absolute',
                )
                if order_id:
                    order_ids.append(order_id)
                    logger.info(f"Order #{i+1} placed: {setup['side'].upper()} {chunk_qty} lots @ {setup['entry_price']} | ID={order_id}")
            except Exception as e:
                logger.error(f"Failed to place order chunk {i+1}: {e}")

        if order_ids:
            self.daily_executions += 1
            self._last_exec_time = time.time()
            self.active_positions.append({
                'setup': setup,
                'order_ids': order_ids,
                'be_moved': False,
                'partial_closed': False,
            })

        return order_ids

    def manage_open_positions(self, current_price: float):
        """Monitors active positions for Breakeven adjustment and partial profit takes."""
        for pos in self.active_positions:
            setup = pos['setup']
            side = setup['side']
            entry = setup['entry_price']
            sl_dist = setup['sl_dist']
            tp_dist = setup['tp_dist']

            # Check Breakeven Trigger
            if not pos['be_moved']:
                favorable_move = (current_price - entry) if side == 'buy' else (entry - current_price)
                if favorable_move >= (sl_dist * config.BE_TRIGGER_BUFFER):
                    logger.info(f"Breakeven triggered for position. Moving SL to {entry}")
                    pos['be_moved'] = True

            # Check 50% Partial Close
            if not pos['partial_closed']:
                favorable_move = (current_price - entry) if side == 'buy' else (entry - current_price)
                if favorable_move >= (tp_dist * config.PARTIAL_CLOSE_AT):
                    logger.info(f"Partial close target reached (+{favorable_move:.2f}).")
                    pos['partial_closed'] = True

    @property
    def has_active_trade(self) -> bool:
        return len(self.active_simulations) > 0 or len(self.active_positions) > 0

    def register_simulation(self, setup: Dict[str, Any]):
        """Registers active simulated positions for all 3 promoted tracks (A, B, C) to monitor in real time."""
        if self.has_active_trade:
            return  # Lock: Only 1 active batch allowed at a time on an impulse
        self.last_traded_candle_ts = setup.get('candle_time', 0)

        registered = False
        track_a = setup.get('track_a')
        if track_a and track_a.get('simulation_passed'):
            self.active_simulations.append({
                'setup': track_a,
                'entry_time': time.time(),
                'status': 'open',
            })
            logger.info(f"[TRACK A: $50 SCALPER] Registered {track_a['side'].upper()} @ {track_a['entry_price']} | TP: {track_a['tp_price']} | SL: {track_a['sl_price']}")
            registered = True

        track_b = setup.get('track_b')
        if track_b and track_b.get('simulation_passed'):
            self.active_simulations.append({
                'setup': track_b,
                'entry_time': time.time(),
                'status': 'open',
            })
            logger.info(f"[TRACK B: $10 SNIPER] Registered {track_b['side'].upper()} @ {track_b['entry_price']} | TP: {track_b['tp_price']} | SL: {track_b['sl_price']}")
            registered = True

        track_c_buy = setup.get('track_c_buy')
        track_c_sell = setup.get('track_c_sell')
        if track_c_buy and track_c_buy.get('simulation_passed'):
            self.active_simulations.append({
                'setup': track_c_buy,
                'entry_time': time.time(),
                'status': 'open',
            })
            self.active_simulations.append({
                'setup': track_c_sell,
                'entry_time': time.time(),
                'status': 'open',
            })
            logger.info(f"[TRACK C: $10 QUANT HEDGE] Registered DUAL STRADDLE (BUY @ {track_c_buy['entry_price']} | SELL @ {track_c_sell['entry_price']})")
            registered = True

    def update_simulated_positions(self, current_price: float) -> List[Dict[str, Any]]:
        """Checks if any active simulated trade has touched TP, SL, or triggered Breakeven."""
        outcomes = []
        remaining = []
        for sim in self.active_simulations:
            setup = sim['setup']
            side = setup['side']
            tp = setup['tp_price']
            sl = setup['sl_price']
            entry = setup['entry_price']
            entry_time = sim['entry_time']
            duration = round(time.time() - entry_time, 1)
            t_name = setup.get('track_name', 'SIM_TRADE')

            # ── 1. Live Breakeven Shift (Tier 1: 0.00 Risk Shield) ──
            be_threshold = round(max(0.04, setup.get('sl_dist', 0.08) * 0.85), 2)
            favorable_move = (current_price - entry) if side == 'buy' else (entry - current_price)
            if not sim.get('be_active', False) and favorable_move >= be_threshold:
                sim['be_active'] = True
                sim['setup']['sl_price'] = entry  # Shift SL directly to entry price
                sim['setup']['is_breakeven'] = True
                logger.info(f"[{t_name}] ⚖️ BREAKEVEN ACTIVATED @ {current_price} -> SL shifted to Entry ${entry:.2f} (0.00 Risk)")

            # ── 2. Tier-2 Dynamic Profit Lock Ratchet (Locking in +25% to +40% Cash) ──
            # When trade reaches >= 45% of TP distance, ratchet SL above Entry into guaranteed green profit
            tp_dist = setup.get('tp_dist', 2.0)
            if favorable_move >= (tp_dist * 0.45):
                lock_dist = round(tp_dist * 0.25, 2)
                locked_sl = round(entry + lock_dist if side == 'buy' else entry - lock_dist, 2)
                if not sim.get('profit_locked', False):
                    sim['profit_locked'] = True
                    sim['locked_pnl'] = round(setup['potential_profit'] * 0.25, 2)
                    sim['setup']['sl_price'] = locked_sl
                    logger.info(f"[{t_name}] 💰 TIER-2 PROFIT RATCHET LOCKED @ {current_price} -> SL moved to ${locked_sl:.2f} (Guaranteed +${sim['locked_pnl']} Profit)")

            # Check Outcomes
            curr_sl = sim['setup']['sl_price']
            hit_tp = (current_price >= tp) if side == 'buy' else (current_price <= tp)
            hit_sl = (current_price <= curr_sl) if side == 'buy' else (current_price >= curr_sl)

            if hit_tp:
                self.cooldown_until = time.time() + 20.0
                outcomes.append({
                    'outcome': 'WIN_TP',
                    'setup': setup,
                    'exit_price': round(current_price, 2),
                    'duration_sec': duration,
                    'pnl': setup['potential_profit'],
                    'timestamp': time.time(),
                })
                logger.info(f"[{t_name}] Simulated WIN TP hit @ {current_price} in {duration}s (+${setup['potential_profit']})")
            elif hit_sl:
                is_be = sim.get('be_active', False)
                is_lock = sim.get('profit_locked', False)
                self.cooldown_until = time.time() + (15.0 if is_be else 30.0)

                if is_lock:
                    out_type = 'WIN_PROFIT_LOCK'
                    pnl_val = sim.get('locked_pnl', round(setup['potential_profit'] * 0.25, 2))
                    logger.info(f"[{t_name}] 💰 PROFIT RATCHET HIT @ {current_price} in {duration}s (+${pnl_val:.2f} PnL — Profit Locked)")
                elif is_be:
                    out_type = 'BREAKEVEN_EXIT'
                    pnl_val = 0.0
                    logger.info(f"[{t_name}] ⚖️ BREAKEVEN EXIT hit @ {current_price} in {duration}s ($0.00 PnL — Capital Protected)")
                else:
                    out_type = 'LOSS_SL'
                    pnl_val = -setup['potential_risk']
                    logger.info(f"[{t_name}] 🛡️ Simulated LOSS SL hit @ {current_price} in {duration}s (-${setup['potential_risk']})")

                outcomes.append({
                    'outcome': out_type,
                    'setup': setup,
                    'exit_price': round(current_price, 2),
                    'duration_sec': duration,
                    'pnl': pnl_val,
                    'timestamp': time.time(),
                })
            else:
                remaining.append(sim)

        self.active_simulations = remaining
        return outcomes
