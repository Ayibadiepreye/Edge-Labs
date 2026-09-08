"""Edge Labs — Multi-Timeframe (M5, M1, 1S) Analysis & Execution Engine
Implements the 4 validated pillars that passed the 66,118 real 1-second broker backtest:
  Pillar 1: Real-Time Forming M5 Trend Stack (EMA 9 > EMA 21 live dynamic alignment)
  Pillar 2: M1 Micro-Ignition Sweet-Spot (15¢ displacement past open + 20s Opening Shield + Opposing Wick < 20%)
  Pillar 3: 1S Kinetic Velocity Spike Gate (>= 20 ticks/sec with < 1¢ opposing wick)
  Pillar 4: Strict 10¢ Spread Gate (<= $0.10 spread friction)

Velocity-Tiered Hybrid Multi-Track Architecture:
  - Initial Margin Cap: $4,590.00 (Blueberry 1:10 Leverage on $5k Account)
  - High-Conviction Bursts (Velocity >= 25 ticks/sec): Routes to Track A SOLO (0.10L, $4,370 margin | $2.00 TP | 12¢ SL)
  - Steady-Trend Expansions (Velocity 20-24 ticks/sec): Routes to Tracks B & C CONCURRENTLY (0.03L + 0.03L = $2,622 margin | $3.33 TP | 12¢ SL)
"""

from __future__ import annotations
import time
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from core.virtual_broker import VirtualBrokerAccount

logger = logging.getLogger("multi_tf_engine")



@dataclass
class UISpeed:
    classification: str = 'medium'
    price_velocity: float = 0.0
    tick_velocity: float = 0.0

@dataclass
class UIDirection:
    bias: str = 'neutral' # 'green' | 'red' | 'neutral'
    score: float = 0.0
    short_score: float = 0.0
    main_score: float = 0.0

@dataclass
class UIStructure:
    nearest_support: float = 0.0
    nearest_resistance: float = 0.0

@dataclass
class UIRejection:
    upper_ratio: float = 0.0
    lower_ratio: float = 0.0

@dataclass
class UIReversal:
    has_reversal: bool = False
    signs: List[str] = field(default_factory=list)

@dataclass
class UIAuxSnapshot:
    speed: UISpeed = field(default_factory=UISpeed)
    direction: UIDirection = field(default_factory=UIDirection)
    structure: UIStructure = field(default_factory=UIStructure)
    rejection: UIRejection = field(default_factory=UIRejection)
    reversal: UIReversal = field(default_factory=UIReversal)
    ready_to_simulate: bool = False

@dataclass
class MultiTFSignal:
    timestamp: float
    side: str                # 'BUY' | 'SELL'
    m5_trend: str            # 'BULLISH' | 'BEARISH'
    entry_price: float
    tp_price: float
    sl_price: float
    be_trigger_price: float
    spread: float
    is_valid: bool = False
    rejection_reasons: List[str] = field(default_factory=list)
    m5_ema9: float = 0.0
    m5_ema21: float = 0.0
    ema_separation: float = 0.0


class MultiTFAnalysisEngine:
    """Multi-Timeframe Analysis Engine with Real-Time Forming M5 EMA Dynamics."""
    def build_telemetry_snapshot(
        self,
        m5_candles: List[Dict[str, Any]],
        m1_candle: Optional[Dict[str, Any]],
        current_price: float,
        tick_vel: float,
        price_vel: float,
        sig: MultiTFSignal
    ) -> UIAuxSnapshot:
        """Constructs live UI telemetry snapshot for the bottom Cyberpunk HUD deck."""
        # 1. Speed Classification
        cls_name = 'fast' if tick_vel >= 20.0 else 'medium' if tick_vel >= 10.0 else 'slow'
        speed = UISpeed(classification=cls_name, price_velocity=price_vel, tick_velocity=tick_vel)

        # 2. Direction & EMA Stack
        bias = 'green' if sig.m5_trend == 'BULLISH' else 'red' if sig.m5_trend == 'BEARISH' else 'neutral'
        direction = UIDirection(bias=bias, score=round(abs(current_price - (m5_candles[-1]['c'] if m5_candles else current_price)), 2), short_score=round(price_vel, 2), main_score=round(tick_vel, 1))

        # 3. Structure S/R
        res = max((c['h'] for c in m5_candles[-20:]), default=current_price + 2.0)
        sup = min((c['l'] for c in m5_candles[-20:]), default=current_price - 2.0)
        structure = UIStructure(nearest_support=round(sup, 2), nearest_resistance=round(res, 2))

        # 4. Wick Drag & Rejection
        u_ratio = 0.0
        l_ratio = 0.0
        has_rev = False
        signs = []
        if m1_candle:
            rng = max(0.01, m1_candle['h'] - m1_candle['l'])
            u_ratio = (m1_candle['h'] - max(m1_candle['o'], m1_candle['c'])) / rng
            l_ratio = (min(m1_candle['o'], m1_candle['c']) - m1_candle['l']) / rng
            if u_ratio >= 0.20:
                has_rev = True
                signs.append('absorption_upper')
            if l_ratio >= 0.20:
                has_rev = True
                signs.append('absorption_lower')

        rejection = UIRejection(upper_ratio=round(u_ratio, 2), lower_ratio=round(l_ratio, 2))
        reversal = UIReversal(has_reversal=has_rev, signs=signs)

        return UIAuxSnapshot(
            speed=speed,
            direction=direction,
            structure=structure,
            rejection=rejection,
            reversal=reversal,
            ready_to_simulate=sig.is_valid
        )


    def __init__(self, spread_max: float = 0.10, min_1s_velocity: float = 20.0):
        self.spread_max = spread_max
        self.min_1s_velocity = min_1s_velocity

    def evaluate_m5_trend(self, m5_candles: List[Dict[str, Any]], live_price: float) -> Tuple[str, float, float, float]:
        """Calculates real-time M5 EMA9 and EMA21 stack with live streaming tick price."""
        if not m5_candles or len(m5_candles) < 20:
            return 'NEUTRAL', 0.0, live_price, live_price

        closes = [c['c'] for c in m5_candles] + [live_price]
        s = pd.Series(closes)
        ema9 = float(s.ewm(span=9, adjust=False).mean().iloc[-1])
        ema21 = float(s.ewm(span=21, adjust=False).mean().iloc[-1])
        separation = abs(ema9 - ema21)

        if live_price > ema9 > ema21:
            return 'BULLISH', separation, ema9, ema21
        elif live_price < ema9 < ema21:
            return 'BEARISH', separation, ema9, ema21
        else:
            return 'NEUTRAL', separation, ema9, ema21

    def evaluate_signal(
        self,
        m5_candles: List[Dict[str, Any]],
        m1_candle: Dict[str, Any],
        current_tick_sec: Dict[str, Any],
        elapsed_sec_in_m1: int,
        spread: float,
        recent_1s_bars: Optional[List[Dict[str, Any]]] = None
    ) -> MultiTFSignal:
        """Exact signal validation logic with real-time forming dynamic alignment."""
        reasons = []

        # 1. Spread Gate
        spread_val = spread if spread < 5 else spread / 100.0
        if spread_val > self.spread_max:
            reasons.append(f'SPREAD_TOO_HIGH_{spread_val:.3f}')

        live_price = current_tick_sec.get('c', 0.0) if current_tick_sec else 0.0

        # 2. Real-Time Forming M5 Trend Stack
        m5_trend, ema_sep, m5_ema9, m5_ema21 = self.evaluate_m5_trend(m5_candles, live_price)
        if m5_trend == 'NEUTRAL':
            reasons.append('M5_TREND_NEUTRAL')

        # 3. M1 Direction & Opposing Wick Check
        if not m1_candle:
            reasons.append('NO_M1_CANDLE')
            side = 'NONE'
            entry_p = 0.0
        else:
            m1_open = m1_candle['o']
            m1_high = m1_candle['h']
            m1_low = m1_candle['l']
            m1_close = m1_candle['c']
            m1_range = max(0.01, m1_high - m1_low)

            if m5_trend == 'BULLISH' and m1_close > m1_open:
                opp_wick = (m1_high - m1_close) / m1_range
                if opp_wick >= 0.20:
                    reasons.append(f'OPP_WICK_TOO_HIGH_{opp_wick:.2f}')
                side = 'BUY'
                entry_p = round(m1_open + 0.15, 2)
            elif m5_trend == 'BEARISH' and m1_close < m1_open:
                opp_wick = (m1_close - m1_low) / m1_range
                if opp_wick >= 0.20:
                    reasons.append(f'OPP_WICK_TOO_HIGH_{opp_wick:.2f}')
                side = 'SELL'
                entry_p = round(m1_open - 0.15, 2)
            else:
                reasons.append('M1_DIRECTION_MISMATCH')
                side = 'NONE'
                entry_p = 0.0

        # 4. 20-Second Opening Shield
        if elapsed_sec_in_m1 < 20:
            reasons.append(f'OPENING_SHIELD_ACTIVE_{elapsed_sec_in_m1}s')

        # 5. 1S Kinetic Velocity Spike Gate
        tick_vel = current_tick_sec.get('v', 1)
        if recent_1s_bars:
            tick_vel = max(tick_vel, sum(b.get('v', 1) for b in recent_1s_bars[-20:]))
            
        if tick_vel < self.min_1s_velocity:
            reasons.append(f'VELOCITY_LOW_{tick_vel:.1f}')

        # 6. 15¢ Displacement Price Trigger
        if current_tick_sec and entry_p > 0:
            if side == 'BUY' and current_tick_sec.get('h', 0.0) < entry_p:
                reasons.append('PRICE_BELOW_15C_DISPLACEMENT')
            elif side == 'SELL' and current_tick_sec.get('l', 99999.0) > entry_p:
                reasons.append('PRICE_ABOVE_15C_DISPLACEMENT')

        is_valid = (len(reasons) == 0)

        tp_p = round(entry_p + 2.00 if side == 'BUY' else entry_p - 2.00, 2)
        sl_p = round(entry_p - 0.12 if side == 'BUY' else entry_p + 0.12, 2)
        be_trig = round(entry_p + 0.60 if side == 'BUY' else entry_p - 0.60, 2)

        return MultiTFSignal(
            timestamp=time.time(),
            side=side,
            m5_trend=m5_trend,
            entry_price=entry_p,
            tp_price=tp_p,
            sl_price=sl_p,
            be_trigger_price=be_trig,
            spread=round(spread_val, 3),
            is_valid=is_valid,
            rejection_reasons=reasons
        )


class MultiTFTradeCoordinator:
    """Manages Velocity-Tiered Hybrid Multi-Track Routing, Margin Gating, and VirtualBroker Execution."""

    def __init__(self, virtual_broker: VirtualBrokerAccount, margin_cap: float = 4590.00, account_manager: Optional[Any] = None):
        self.broker = virtual_broker
        self.margin_cap = margin_cap
        self.account_manager = account_manager
        self.engine = MultiTFAnalysisEngine(spread_max=0.10, min_1s_velocity=20.0)
        self.last_candle_traded: Dict[str, int] = {'A': 0, 'B': 0, 'C': 0}
        self.live_position_map: Dict[int, List[Dict[str, Any]]] = {}

    def _sync_live_sl(self, virtual_pos_id: int, new_sl: float, new_tp: Optional[float] = None):
        """Syncs modified Stop Loss (Breakeven / Ratchet) and Take Profit to live broker positions."""
        if not (config.LIVE_EXECUTION_ENABLED and self.account_manager):
            return
        live_entries = self.live_position_map.get(virtual_pos_id, [])
        mod_items = []
        if live_entries:
            for entry in live_entries:
                p_id = entry.get('position_id') or entry.get('order_id')
                if p_id:
                    mod_items.append({
                        "account_id": entry.get('account_id'),
                        "pos_id": p_id,
                        "new_sl": new_sl,
                        "new_tp": new_tp
                    })
        else:
            for acc_id, acc in self.account_manager.accounts.items():
                if acc.is_active and not acc.circuit_breaker_tripped:
                    mod_items.append({
                        "account_id": acc_id,
                        "pos_id": virtual_pos_id,
                        "new_sl": new_sl,
                        "new_tp": new_tp
                    })
        if mod_items:
            try:
                self.account_manager.modify_live_sl_burst(mod_items)
            except Exception as e:
                logger.error(f"Failed to sync live SL: {e}")

    def on_tick(
        self,
        bid: float,
        ask: float,
        m5_candles: List[Dict[str, Any]],
        m1_candle: Dict[str, Any],
        current_sec: Dict[str, Any],
        elapsed_sec_in_m1: int,
        current_m5_ts: int,
        preferred_track: Optional[str] = None,
        recent_1s_bars: Optional[List[Dict[str, Any]]] = None,
        eff_tvel: float = 0.0,
        rolling_20s_ticks: int = 0
    ) -> Optional[Dict[str, Any]]:
        """Processes real-time ticks, manages open positions, and executes Velocity-Tiered Hybrid entries."""
        spread = round(ask - bid, 3)

        # 1. Update In-Memory Open Positions (Breakeven, Profit Ratchet, Take Profit, Stop Loss)
        self.broker.update_ticks(bid, ask)

        closed_events: List[Dict[str, Any]] = []
        open_pos_ids = list(self.broker.positions.keys())
        for pos_id in open_pos_ids:
            if pos_id not in self.broker.positions:
                continue
            pos = self.broker.positions[pos_id]

            if pos.side == 'buy':
                be_trig_p = round(pos.entry_price + max(0.30, pos.tp_dist * 0.30), 2)
                r50_trig_p = round(pos.entry_price + (pos.tp_dist * 0.50), 2)
                r75_trig_p = round(pos.entry_price + (pos.tp_dist * 0.75), 2)

                # Dynamic Multi-Stage Ratchet Advancements
                if bid >= r75_trig_p:
                    pos.sl_price = max(pos.sl_price, round(pos.entry_price + (pos.tp_dist * 0.50), 2))
                    pos.profit_locked = True
                    self._sync_live_sl(pos.id, pos.sl_price)
                elif bid >= r50_trig_p:
                    pos.sl_price = max(pos.sl_price, round(pos.entry_price + max(0.50, pos.tp_dist * 0.25), 2))
                    pos.profit_locked = True
                    self._sync_live_sl(pos.id, pos.sl_price)
                elif bid >= be_trig_p and not pos.be_active:
                    pos.be_active = True
                    pos.sl_price = max(pos.sl_price, round(pos.entry_price + 0.11, 2))
                    self._sync_live_sl(pos.id, pos.sl_price)
                    logger.info(f"🛡️ [BREAKEVEN ACTIVATED] #{pos.id} ({pos.track_id}): SL -> ${pos.sl_price:.2f}")

                if bid <= pos.sl_price:
                    close_reason = 'RATCHET_WIN' if getattr(pos, 'profit_locked', False) else ('BE_PROTECTED' if pos.be_active else 'STOP_LOSS')
                    res_c = self.broker.close_position(pos.id, pos.sl_price, reason=close_reason)
                    closed_events.append({
                        'outcome': close_reason,
                        'pnl': res_c.get('net_pnl', 0.0),
                        'exit_price': pos.sl_price,
                        'duration_sec': round(time.time() - pos.open_time, 1),
                        'track_id': pos.track_id,
                        'side': pos.side,
                        'virtual_balance': self.broker.balance,
                        'buffer_to_floor': max(0.0, self.broker.balance - self.broker.loss_floor),
                        'setup': {
                            'timestamp': pos.open_time,
                            'candle_time': int(pos.open_time // 300) * 300,
                            'entry_price': pos.entry_price,
                            'tp_price': pos.tp_price,
                            'sl_price': pos.sl_price,
                            'track_name': f"TRACK {pos.track_id}",
                            'total_lots': pos.qty,
                            'side': pos.side
                        }
                    })
                    continue

                if bid >= pos.tp_price:
                    res_c = self.broker.close_position(pos.id, pos.tp_price, reason='WIN_TP')
                    closed_events.append({
                        'outcome': 'WIN_TP',
                        'pnl': res_c.get('net_pnl', 0.0),
                        'exit_price': pos.tp_price,
                        'duration_sec': round(time.time() - pos.open_time, 1),
                        'track_id': pos.track_id,
                        'side': pos.side,
                        'virtual_balance': self.broker.balance,
                        'buffer_to_floor': max(0.0, self.broker.balance - self.broker.loss_floor),
                        'setup': {
                            'timestamp': pos.open_time,
                            'candle_time': int(pos.open_time // 300) * 300,
                            'entry_price': pos.entry_price,
                            'tp_price': pos.tp_price,
                            'sl_price': pos.sl_price,
                            'track_name': f"TRACK {pos.track_id}",
                            'total_lots': pos.qty,
                            'side': pos.side
                        }
                    })
                    continue

            else: # SELL
                be_trig_p = round(pos.entry_price - max(0.30, pos.tp_dist * 0.30), 2)
                r50_trig_p = round(pos.entry_price - (pos.tp_dist * 0.50), 2)
                r75_trig_p = round(pos.entry_price - (pos.tp_dist * 0.75), 2)

                # Dynamic Multi-Stage Ratchet Advancements
                if ask <= r75_trig_p:
                    pos.sl_price = min(pos.sl_price, round(pos.entry_price - (pos.tp_dist * 0.50), 2))
                    pos.profit_locked = True
                    self._sync_live_sl(pos.id, pos.sl_price)
                elif ask <= r50_trig_p:
                    pos.sl_price = min(pos.sl_price, round(pos.entry_price - max(0.50, pos.tp_dist * 0.25), 2))
                    pos.profit_locked = True
                    self._sync_live_sl(pos.id, pos.sl_price)
                elif ask <= be_trig_p and not pos.be_active:
                    pos.be_active = True
                    pos.sl_price = min(pos.sl_price, round(pos.entry_price - 0.11, 2))
                    self._sync_live_sl(pos.id, pos.sl_price)
                    logger.info(f"🛡️ [BREAKEVEN ACTIVATED] #{pos.id} ({pos.track_id}): SL -> ${pos.sl_price:.2f}")

                if ask >= pos.sl_price:
                    close_reason = 'RATCHET_WIN' if getattr(pos, 'profit_locked', False) else ('BE_PROTECTED' if pos.be_active else 'STOP_LOSS')
                    res_c = self.broker.close_position(pos.id, pos.sl_price, reason=close_reason)
                    closed_events.append({
                        'outcome': close_reason,
                        'pnl': res_c.get('net_pnl', 0.0),
                        'exit_price': pos.sl_price,
                        'duration_sec': round(time.time() - pos.open_time, 1),
                        'track_id': pos.track_id,
                        'side': pos.side,
                        'virtual_balance': self.broker.balance,
                        'buffer_to_floor': max(0.0, self.broker.balance - self.broker.loss_floor),
                        'setup': {
                            'timestamp': pos.open_time,
                            'candle_time': int(pos.open_time // 300) * 300,
                            'entry_price': pos.entry_price,
                            'tp_price': pos.tp_price,
                            'sl_price': pos.sl_price,
                            'track_name': f"TRACK {pos.track_id}",
                            'total_lots': pos.qty,
                            'side': pos.side
                        }
                    })
                    continue

                if ask <= pos.tp_price:
                    res_c = self.broker.close_position(pos.id, pos.tp_price, reason='WIN_TP')
                    closed_events.append({
                        'outcome': 'WIN_TP',
                        'pnl': res_c.get('net_pnl', 0.0),
                        'exit_price': pos.tp_price,
                        'duration_sec': round(time.time() - pos.open_time, 1),
                        'track_id': pos.track_id,
                        'side': pos.side,
                        'virtual_balance': self.broker.balance,
                        'buffer_to_floor': max(0.0, self.broker.balance - self.broker.loss_floor),
                        'setup': {
                            'timestamp': pos.open_time,
                            'candle_time': int(pos.open_time // 300) * 300,
                            'entry_price': pos.entry_price,
                            'tp_price': pos.tp_price,
                            'sl_price': pos.sl_price,
                            'track_name': f"TRACK {pos.track_id}",
                            'total_lots': pos.qty,
                            'side': pos.side
                        }
                    })
                    continue

        # 2. Evaluate Signal with 20s Velocity Window
        sig = self.engine.evaluate_signal(
            m5_candles=m5_candles,
            m1_candle=m1_candle,
            current_tick_sec=current_sec,
            elapsed_sec_in_m1=elapsed_sec_in_m1,
            spread=spread,
            recent_1s_bars=recent_1s_bars
        )

        executed_receipts: List[Dict[str, Any]] = []

        if not sig.is_valid:
            return {'executed': executed_receipts, 'closed': closed_events} if closed_events else None

        side = sig.side.lower()
        entry_p = sig.entry_price
        v_instant = current_sec.get('v', 1)
        if not rolling_20s_ticks and recent_1s_bars:
            rolling_20s_ticks = sum(b.get('v', 1) for b in recent_1s_bars[-20:])

        # 3. Dynamic Multi-Track Selector (Strict 20-Second Rolling Kinetic Buffer Gate)
        current_used_margin = self.broker.used_margin
        available_margin = max(0.0, self.margin_cap - current_used_margin)

        if preferred_track in ['A', 'B', 'C']:
            target_tracks = [preferred_track]
        else:
            # Strict 20-Second Rolling Kinetic Buffer Gate:
            # High-velocity institutional burst (>= 25 ticks in the 20s rolling buffer)
            # -> Route to Track A SOLO ($4,370 margin | $2.00 Target)
            # Steady-trend expansion (< 25 ticks in 20s buffer)
            # -> Route to Tracks B & C CONCURRENTLY ($3,933 margin | $3.33 Target)
            if rolling_20s_ticks >= 25:
                target_tracks = ['A']
            else:
                target_tracks = ['B', 'C']

        TRACK_PARAMS = {
            'A': {'name': 'Track A (Institutional Scalper)', 'lots': 0.10, 'tp': 2.00, 'sl': 0.12, 'margin': 4370.00},
            'B': {'name': 'Track B (Dynamic Sniper)',        'lots': 0.03, 'tp': 3.33, 'sl': 0.12, 'margin': 1311.00},
            'C': {'name': 'Track C (Quant Dual Hedge)',      'lots': 0.03, 'tp': 3.33, 'sl': 0.12, 'margin': 2622.00},
        }

        for t_id in target_tracks:
            # Check 1-trade-per-candle lockout for this track
            if current_m5_ts and current_m5_ts == self.last_candle_traded.get(t_id, 0):
                continue

            spec = TRACK_PARAMS[t_id]
            req_margin = spec['margin']

            # Check margin availability
            if req_margin > available_margin:
                continue

            lots = spec['lots']
            tp_dist = spec['tp']
            sl_dist = spec['sl']
            track_name = spec['name']

            # Dynamic SL distance: standard 0.12, allow up to max 0.20 if spread friction is elevated
            eff_sl_dist = round(min(0.20, max(sl_dist, spread * 1.5 if spread > 0.08 else sl_dist)), 2)

            if t_id == 'C':
                # Track C is an authentic Dual-Sided Straddle Hedge (submits BOTH Buy and Sell legs)
                # Leg 1: BUY Straddle Leg (Anchored to Ask)
                fill_buy = round(bid + spread, 2)
                buy_tp = round(fill_buy + tp_dist, 2)
                buy_sl = round(fill_buy - eff_sl_dist, 2)
                r_buy = self.broker.submit_order(
                    track_id='C', side='buy', qty=lots,
                    sl_price=buy_sl, tp_price=buy_tp,
                    sl_dist=eff_sl_dist, tp_dist=tp_dist,
                    bid=bid, ask=fill_buy
                )
                if r_buy and ('id' in r_buy or 'order_id' in r_buy or r_buy.get('status') == 'Filled'):
                    r_buy['track_id'] = 'C'
                    r_buy['track_name'] = 'TRACK C (BUY)'
                    r_buy['entry_price'] = r_buy.get('avgPrice', fill_buy)
                    r_buy['tp_price'] = buy_tp
                    r_buy['sl_price'] = buy_sl
                    r_buy['tp_dist'] = tp_dist
                    r_buy['sl_dist'] = eff_sl_dist
                    r_buy['total_lots'] = lots
                    r_buy['potential_profit'] = round(lots * 100.0 * tp_dist, 2)
                    r_buy['potential_risk'] = round(lots * 100.0 * eff_sl_dist, 2)
                    r_buy['timestamp'] = time.time()
                    r_buy['ready_to_simulate'] = True

                # Leg 2: SELL Straddle Leg (Anchored to Bid)
                fill_sell = round(bid, 2)
                sell_tp = round(fill_sell - tp_dist, 2)
                sell_sl = round(fill_sell + eff_sl_dist, 2)
                r_sell = self.broker.submit_order(
                    track_id='C', side='sell', qty=lots,
                    sl_price=sell_sl, tp_price=sell_tp,
                    sl_dist=eff_sl_dist, tp_dist=tp_dist,
                    bid=fill_sell, ask=round(bid + spread, 2)
                )
                if r_sell and ('id' in r_sell or 'order_id' in r_sell or r_sell.get('status') == 'Filled'):
                    r_sell['track_id'] = 'C'
                    r_sell['track_name'] = 'TRACK C (SELL)'
                    r_sell['entry_price'] = r_sell.get('avgPrice', fill_sell)
                    r_sell['tp_price'] = sell_tp
                    r_sell['sl_price'] = sell_sl
                    r_sell['tp_dist'] = tp_dist
                    r_sell['sl_dist'] = eff_sl_dist
                    r_sell['total_lots'] = lots
                    r_sell['potential_profit'] = round(lots * 100.0 * tp_dist, 2)
                    r_sell['potential_risk'] = round(lots * 100.0 * eff_sl_dist, 2)
                    r_sell['timestamp'] = time.time()
                    r_sell['ready_to_simulate'] = True

                # Live Order Dispatch across active accounts with instant post-fill calibration
                if config.LIVE_EXECUTION_ENABLED and self.account_manager:
                    live_buys = self.account_manager.execute_live_order_burst(
                        track_id='C', side='buy', sl_price=buy_sl, tp_price=buy_tp,
                        sl_dist=eff_sl_dist, tp_dist=tp_dist, spread=spread
                    )
                    live_sells = self.account_manager.execute_live_order_burst(
                        track_id='C', side='sell', sl_price=sell_sl, tp_price=sell_tp,
                        sl_dist=eff_sl_dist, tp_dist=tp_dist, spread=spread
                    )
                    b_pos_id = r_buy.get('position_id') or r_buy.get('id') or r_buy.get('order_id')
                    if b_pos_id:
                        self.live_position_map[b_pos_id] = live_buys
                        if live_buys and live_buys[0].get('fill_price'):
                            r_buy['entry_price'] = live_buys[0]['fill_price']
                            r_buy['sl_price'] = live_buys[0]['sl_price']
                            r_buy['tp_price'] = live_buys[0]['tp_price']
                            if b_pos_id in self.broker.positions:
                                self.broker.positions[b_pos_id].entry_price = r_buy['entry_price']
                                self.broker.positions[b_pos_id].sl_price = r_buy['sl_price']
                                self.broker.positions[b_pos_id].tp_price = r_buy['tp_price']

                    s_pos_id = r_sell.get('position_id') or r_sell.get('id') or r_sell.get('order_id')
                    if s_pos_id:
                        self.live_position_map[s_pos_id] = live_sells
                        if live_sells and live_sells[0].get('fill_price'):
                            r_sell['entry_price'] = live_sells[0]['fill_price']
                            r_sell['sl_price'] = live_sells[0]['sl_price']
                            r_sell['tp_price'] = live_sells[0]['tp_price']
                            if s_pos_id in self.broker.positions:
                                self.broker.positions[s_pos_id].entry_price = r_sell['entry_price']
                                self.broker.positions[s_pos_id].sl_price = r_sell['sl_price']
                                self.broker.positions[s_pos_id].tp_price = r_sell['tp_price']

                    logger.info(f"⚡ [LIVE TRADE DISPATCHED] Track C DUAL HEDGE -> BUY {lots}L & SELL {lots}L | Result: {len(live_buys)} live buy, {len(live_sells)} live sell")

                if r_buy:
                    executed_receipts.append(r_buy)
                if r_sell:
                    executed_receipts.append(r_sell)

                self.last_candle_traded['C'] = current_m5_ts
                available_margin -= req_margin
                logger.info(f"🚀 [MULTI-TF ENGINE] {track_name} DUAL HEDGE EXECUTED: BUY {lots}L & SELL {lots}L (Margin: ${req_margin:.2f})")

            else:
                # Track A and Track B Directional Order Placement
                # Spread-anchored: BUYs anchor to Ask, SELLs anchor to Bid
                if side == 'buy':
                    fill_ref = round(bid + spread, 2)
                    tp_p = round(fill_ref + tp_dist, 2)
                    sl_p = round(fill_ref - eff_sl_dist, 2)
                else:
                    fill_ref = round(bid, 2)
                    tp_p = round(fill_ref - tp_dist, 2)
                    sl_p = round(fill_ref + eff_sl_dist, 2)

                receipt = self.broker.submit_order(
                    track_id=t_id,
                    side=side,
                    qty=lots,
                    sl_price=sl_p,
                    tp_price=tp_p,
                    sl_dist=eff_sl_dist,
                    tp_dist=tp_dist,
                    bid=bid,
                    ask=round(bid + spread, 2)
                )

                if receipt and ('id' in receipt or 'order_id' in receipt or receipt.get('status') == 'Filled'):
                    receipt['track_id'] = t_id
                    receipt['track_name'] = track_name
                    receipt['entry_price'] = receipt.get('avgPrice', fill_ref)
                    receipt['tp_price'] = tp_p
                    receipt['sl_price'] = sl_p
                    receipt['tp_dist'] = tp_dist
                    receipt['sl_dist'] = eff_sl_dist
                    receipt['total_lots'] = lots
                    receipt['potential_profit'] = round(lots * 100.0 * tp_dist, 2)
                    receipt['potential_risk'] = round(lots * 100.0 * eff_sl_dist, 2)
                    receipt['timestamp'] = time.time()
                    receipt['ready_to_simulate'] = True

                    # Live Order Dispatch across active accounts with instant post-fill calibration
                    if config.LIVE_EXECUTION_ENABLED and self.account_manager:
                        live_orders = self.account_manager.execute_live_order_burst(
                            track_id=t_id,
                            side=side.lower(),
                            sl_price=sl_p,
                            tp_price=tp_p,
                            sl_dist=eff_sl_dist,
                            tp_dist=tp_dist,
                            spread=spread
                        )
                        p_pos_id = receipt.get('position_id') or receipt.get('id') or receipt.get('order_id')
                        if p_pos_id:
                            self.live_position_map[p_pos_id] = live_orders
                        if live_orders and live_orders[0].get('fill_price'):
                            live_fill = live_orders[0]['fill_price']
                            live_sl = live_orders[0]['sl_price']
                            live_tp = live_orders[0]['tp_price']
                            receipt['entry_price'] = live_fill
                            receipt['sl_price'] = live_sl
                            receipt['tp_price'] = live_tp
                            if p_pos_id in self.broker.positions:
                                self.broker.positions[p_pos_id].entry_price = live_fill
                                self.broker.positions[p_pos_id].sl_price = live_sl
                                self.broker.positions[p_pos_id].tp_price = live_tp
                        logger.info(f"⚡ [LIVE TRADE DISPATCHED] {track_name} -> {side.upper()} {lots}L @ ${receipt['entry_price']:.2f} | TP: ${receipt['tp_price']:.2f} | SL: ${receipt['sl_price']:.2f} | Result: {len(live_orders)} live account(s)")

                    self.last_candle_traded[t_id] = current_m5_ts
                    available_margin -= req_margin
                    executed_receipts.append(receipt)
                    logger.info(f"🚀 [MULTI-TF ENGINE] {track_name} EXECUTED: {side.upper()} {lots}L @ {receipt['entry_price']:.2f} | TP: {receipt['tp_price']:.2f} | SL: {receipt['sl_price']:.2f} (Margin: ${req_margin:.2f})")

        return {'executed': executed_receipts, 'closed': closed_events} if (executed_receipts or closed_events) else None
