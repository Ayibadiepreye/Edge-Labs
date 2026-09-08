"""Edge Labs — Atomic Live Market Dynamics & Trade Execution Telemetry Logger
Continuously logs every incoming market tick with 30+ atomic parameters, movement metrics,
multi-timeframe indicators, and trade lifecycle events into structured CSV datasets for backtesting.
"""

from __future__ import annotations
import os
import time
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

logger = logging.getLogger("system")

class LiveTelemetryLogger:
    """High-frequency atomic tick and trade event logger."""
    
    def __init__(self, logs_dir: Optional[str] = None):
        if logs_dir is None:
            self.logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
        else:
            self.logs_dir = logs_dir
            
        os.makedirs(self.logs_dir, exist_ok=True)
        
        # State tracking for movement & tick counts
        self.total_tick_count: int = 0
        self.m1_tick_count: int = 0
        self.m5_tick_count: int = 0
        self.current_m1_ts: int = 0
        self.current_m5_ts: int = 0
        self.last_price: float = 0.0
        
        # Determine today's file paths
        today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        self.tick_csv_path = os.path.join(self.logs_dir, f"live_tick_telemetry_{today_str}.csv")
        self.event_csv_path = os.path.join(self.logs_dir, f"atomic_trade_events_{today_str}.csv")
        
        self._init_csv_headers()

    def _init_csv_headers(self):
        """Initializes CSV files with headers if they do not exist."""
        if not os.path.exists(self.tick_csv_path):
            with open(self.tick_csv_path, "w", encoding="utf-8") as f:
                f.write(
                    "timestamp_utc,epoch_ts,tick_total,tick_in_m1,tick_in_m5,"
                    "bid,ask,spread_cents,spread_status,tick_delta_cents,tick_direction,"
                    "disp_m1_cents,disp_m5_cents,tick_vel_per_sec,price_vel_cents_sec,pulse_move_cents,speed_tier,"
                    "m5_open,m5_high,m5_low,m5_close,m5_ema9,m5_ema21,m5_ema_sep_cents,m5_trend,m5_range_cents,"
                    "m1_open,m1_high,m1_low,m1_close,m1_elapsed_sec,shield_status,m1_range_cents,m1_body_cents,"
                    "m1_uwick_cents,m1_lwick_cents,m1_uwick_pct,m1_lwick_pct,opp_wick_pct,wick_gate_status,"
                    "breakout_trigger,dist_to_trigger_cents,breakout_triggered,recommended_track,"
                    "active_pos_count,used_margin,margin_buffer,loss_floor_buffer,signal_valid,decision_reason\n"
                )

        if not os.path.exists(self.event_csv_path):
            with open(self.event_csv_path, "w", encoding="utf-8") as f:
                f.write(
                    "timestamp_utc,epoch_ts,event_type,order_id,position_id,track_id,side,qty_lots,"
                    "trigger_price,fill_price,exit_price,slippage_cents,initial_sl,active_sl,tp_price,"
                    "market_spread_cents,tick_vel_at_event,trade_duration_sec,ticks_during_trade,"
                    "gross_pnl,broker_fee,net_pnl,balance,loss_floor_buffer,reason\n"
                )

    def log_tick(
        self,
        bid: float,
        ask: float,
        spread: float,
        eff_tvel: float,
        eff_pvel: float,
        m5_candles: List[Dict[str, Any]],
        m1_candle: Optional[Dict[str, Any]],
        sig: Any,
        snap: Any,
        broker_state: Optional[Dict[str, Any]] = None,
        now_ts: Optional[float] = None
    ):
        """Logs a single market tick with full 30+ atomic parameter telemetry."""
        if now_ts is None:
            now_ts = time.time()
            
        dt_str = datetime.fromtimestamp(now_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        self.total_tick_count += 1
        
        # 1. Intra-Candle Pulse Counters
        m1_boundary = int(now_ts // 60) * 60
        m5_boundary = int(now_ts // 300) * 300
        
        if m1_boundary != self.current_m1_ts:
            self.current_m1_ts = m1_boundary
            self.m1_tick_count = 1
        else:
            self.m1_tick_count += 1
            
        if m5_boundary != self.current_m5_ts:
            self.current_m5_ts = m5_boundary
            self.m5_tick_count = 1
        else:
            self.m5_tick_count += 1
            
        # 2. Tick Delta & Direction
        tick_delta = (bid - self.last_price) if self.last_price > 0 else 0.0
        tick_delta_cents = round(tick_delta * 100.0, 1)
        tick_dir = "UP" if tick_delta > 0 else "DOWN" if tick_delta < 0 else "FLAT"
        self.last_price = bid
        
        # 3. Spread Metrics
        spread_cents = round((spread if spread < 5 else spread / 100.0) * 100.0, 1)
        spread_status = "PASS_<=10c" if spread_cents <= 10.0 else f"BLOCKED_{spread_cents:.1f}c"
        
        # 4. Kinetic Velocity & Momentum Pulse
        t_vel = round(eff_tvel / 60.0, 1) if eff_tvel > 0 else 1.0
        p_vel_cents = round((eff_pvel / 60.0) * 100.0, 2)
        pulse_move_cents = round((abs(p_vel_cents) / max(0.5, t_vel)), 2)
        speed_tier = "FAST" if t_vel >= 20.0 else "MEDIUM" if t_vel >= 10.0 else "SLOW"
        
        # 5. M5 Candle & Trend Dynamics
        m5_o = m5_candles[-1]['o'] if m5_candles else bid
        m5_h = max((c['h'] for c in m5_candles[-1:]), default=bid)
        m5_l = min((c['l'] for c in m5_candles[-1:]), default=bid)
        m5_c = m5_candles[-1]['c'] if m5_candles else bid
        m5_range_c = round((m5_h - m5_l) * 100.0, 1)
        disp_m5_cents = round((bid - m5_o) * 100.0, 1)
        
        m5_trend = getattr(sig, 'm5_trend', 'NEUTRAL')
        ema_sep_c = round(getattr(sig, 'ema_separation', 0.0) * 100.0, 1)
        m5_ema9 = round(getattr(sig, 'm5_ema9', bid), 2)
        m5_ema21 = round(getattr(sig, 'm5_ema21', bid), 2)
        
        # 6. M1 Microstructure & Wick Resistance
        if m1_candle:
            m1_o = float(m1_candle.get('o', bid))
            m1_h = float(m1_candle.get('h', bid))
            m1_l = float(m1_candle.get('l', bid))
            m1_c = float(m1_candle.get('c', bid))
        else:
            m1_o = m1_h = m1_l = m1_c = bid
            
        disp_m1_cents = round((bid - m1_o) * 100.0, 1)
        m1_range = max(0.01, m1_h - m1_l)
        m1_range_c = round(m1_range * 100.0, 1)
        m1_body_c = round(abs(m1_c - m1_o) * 100.0, 1)
        
        m1_uwick = max(0.0, m1_h - max(m1_o, m1_c))
        m1_lwick = max(0.0, min(m1_o, m1_c) - m1_l)
        m1_uwick_c = round(m1_uwick * 100.0, 1)
        m1_lwick_c = round(m1_lwick * 100.0, 1)
        m1_uwick_pct = round((m1_uwick / m1_range) * 100.0, 1)
        m1_lwick_pct = round((m1_lwick / m1_range) * 100.0, 1)
        
        elapsed_s = int(now_ts) % 60
        shield_status = "CLEARED_>=20s" if elapsed_s >= 20 else f"ACTIVE_{elapsed_s}s"
        
        if m5_trend == 'BULLISH':
            opp_wick_pct = m1_uwick_pct
        elif m5_trend == 'BEARISH':
            opp_wick_pct = m1_lwick_pct
        else:
            opp_wick_pct = max(m1_uwick_pct, m1_lwick_pct)
            
        wick_gate_status = "PASS_<20%" if opp_wick_pct < 20.0 else f"BLOCKED_{opp_wick_pct:.1f}%"
        
        # 7. Breakout Trigger & Distance
        trigger_p = getattr(sig, 'entry_price', 0.0)
        if trigger_p > 0:
            dist_to_trigger_cents = round(abs(trigger_p - bid) * 100.0, 1)
        else:
            dist_to_trigger_cents = 0.0
            
        breakout_triggered = "YES" if (getattr(sig, 'is_valid', False)) else "NO"
        
        # 8. Multi-Track Recommendation & Margin State
        if t_vel >= 25.0:
            recommended_track = "TRACK_A_SOLO_0.10L"
        elif t_vel >= 20.0:
            recommended_track = "TRACKS_B_C_CONCURRENT_0.06L"
        else:
            recommended_track = "STANDBY_VEL_LOW"
            
        bs = broker_state or {}
        active_pos_count = bs.get('active_positions', 0)
        used_margin = bs.get('used_margin', 0.0)
        balance = bs.get('balance', 4775.66)
        margin_cap = 4590.00
        loss_floor = 4700.00
        margin_buffer = round(max(0.0, margin_cap - used_margin), 2)
        loss_floor_buffer = round(max(0.0, balance - loss_floor), 2)
        
        # 9. Signal Validity & Primary Reason
        sig_valid = "TRUE" if getattr(sig, 'is_valid', False) else "FALSE"
        reasons = getattr(sig, 'rejection_reasons', [])
        primary_reason = "|".join(reasons) if reasons else "READY_TO_FIRE"
        
        # Write CSV Row
        try:
            row = (
                f"{dt_str},{now_ts:.3f},{self.total_tick_count},{self.m1_tick_count},{self.m5_tick_count},"
                f"{bid:.2f},{ask:.2f},{spread_cents:.1f},{spread_status},{tick_delta_cents:+.1f},{tick_dir},"
                f"{disp_m1_cents:+.1f},{disp_m5_cents:+.1f},{t_vel:.1f},{p_vel_cents:+.2f},{pulse_move_cents:.2f},{speed_tier},"
                f"{m5_o:.2f},{m5_h:.2f},{m5_l:.2f},{m5_c:.2f},{m5_ema9:.2f},{m5_ema21:.2f},{ema_sep_c:.1f},{m5_trend},{m5_range_c:.1f},"
                f"{m1_o:.2f},{m1_h:.2f},{m1_l:.2f},{m1_c:.2f},{elapsed_s},{shield_status},{m1_range_c:.1f},{m1_body_c:.1f},"
                f"{m1_uwick_c:.1f},{m1_lwick_c:.1f},{m1_uwick_pct:.1f},{m1_lwick_pct:.1f},{opp_wick_pct:.1f},{wick_gate_status},"
                f"{trigger_p:.2f},{dist_to_trigger_cents:.1f},{breakout_triggered},{recommended_track},"
                f"{active_pos_count},{used_margin:.2f},{margin_buffer:.2f},{loss_floor_buffer:.2f},{sig_valid},{primary_reason}\n"
            )
            with open(self.tick_csv_path, "a", encoding="utf-8") as f:
                f.write(row)
        except Exception as e:
            logger.error(f"[TELEMETRY LOGGER ERROR] Failed to write tick: {e}")

    def log_trade_event(
        self,
        event_type: str,
        order_id: int,
        position_id: int,
        track_id: str,
        side: str,
        qty: float,
        trigger_price: float,
        fill_price: float,
        exit_price: float = 0.0,
        initial_sl: float = 0.0,
        active_sl: float = 0.0,
        tp_price: float = 0.0,
        spread_cents: float = 0.0,
        tick_vel: float = 0.0,
        trade_duration: float = 0.0,
        ticks_during_trade: int = 0,
        gross_pnl: float = 0.0,
        broker_fee: float = 0.0,
        net_pnl: float = 0.0,
        balance: float = 4775.66,
        reason: str = "EXECUTION"
    ):
        """Logs atomic trade lifecycle event with sub-second timestamps and exact execution metrics."""
        now_ts = time.time()
        dt_str = datetime.fromtimestamp(now_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        slippage_cents = round((fill_price - trigger_price) * 100.0, 1) if trigger_price > 0 else 0.0
        floor_buffer = max(0.0, balance - 4700.00)
        
        try:
            row = (
                f"{dt_str},{now_ts:.3f},{event_type},{order_id},{position_id},{track_id},{side.upper()},{qty:.2f},"
                f"{trigger_price:.2f},{fill_price:.2f},{exit_price:.2f},{slippage_cents:+.1f},"
                f"{initial_sl:.2f},{active_sl:.2f},{tp_price:.2f},{spread_cents:.1f},{tick_vel:.1f},"
                f"{trade_duration:.2f},{ticks_during_trade},{gross_pnl:.2f},{broker_fee:.2f},{net_pnl:.2f},"
                f"{balance:.2f},{floor_buffer:.2f},{reason}\n"
            )
            with open(self.event_csv_path, "a", encoding="utf-8") as f:
                f.write(row)
        except Exception as e:
            logger.error(f"[TELEMETRY LOGGER ERROR] Failed to write trade event: {e}")
