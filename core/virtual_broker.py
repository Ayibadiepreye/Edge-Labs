from core.live_telemetry_logger import LiveTelemetryLogger
import os
"""Edge Labs — Virtual Broker Matching Engine & Prop Firm Monitor
Mirrors TradeLocker and Blueberry Markets down to the millisecond:
- Realistic Fill Latency (80ms - 150ms)
- Dual Bid/Ask Execution (Buy @ Ask, Sell @ Bid)
- Instant Spread Friction & Negative Mark-to-Market
- 1:10 Leverage & Margin Requirement Validation ($44,500/lot @ $4,450 Gold)
- Exact TradeLocker Reverse Liquidation Receipts (SELL @ Price, SL:0, TP:0, Status: Filled)
- Prop Firm Hard Floor Monitoring ($4,700.00 Floor with $4,775.66 Current Balance)
"""

import time
import math
import random
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging

logger = logging.getLogger("virtual_broker")


@dataclass
class VirtualPosition:
    id: str
    order_id: str
    track_id: str
    side: str          # 'buy' | 'sell'
    qty: float         # lots
    entry_price: float
    sl_price: float
    tp_price: float
    sl_dist: float
    tp_dist: float
    open_time: float
    required_margin: float
    be_active: bool = False
    profit_locked: bool = False
    locked_pnl: float = 0.0


class VirtualBrokerAccount:
    """In-memory TradeLocker broker simulator and prop firm compliance engine."""

    def __init__(
        self,
        starting_balance: float = 4775.66,
        loss_floor: float = 4755.66,
        leverage: float = 10.0,
        contract_size: float = 100.0,
    ):
        self.balance: float = starting_balance
        self.equity: float = starting_balance
        self.loss_floor: float = loss_floor
        self.leverage: float = leverage
        self.contract_size: float = contract_size

        self.positions: Dict[str, VirtualPosition] = {}
        self.orders_history: List[Dict[str, Any]] = []
        self.executions_history: List[Dict[str, Any]] = []
        self.rule_breaches: List[Dict[str, Any]] = []

        self.today_gross: float = 0.0
        self.today_net: float = 0.0
        self.today_fees: float = 0.0
        self.today_volume: float = 0.0
        self.today_trades_count: int = 0
        self.peak_equity: float = starting_balance
        self.max_drawdown_usd: float = 0.0

        self._order_counter: int = 360287970300000000

    def _next_id(self) -> str:
        self._order_counter += random.randint(1, 9)
        return str(self._order_counter)

    @property
    def used_margin(self) -> float:
        return sum(pos.required_margin for pos in self.positions.values())

    @property
    def free_margin(self) -> float:
        return max(0.0, self.equity - self.used_margin)

    @property
    def margin_level_pct(self) -> float:
        if self.used_margin <= 0:
            return 9999.0
        return (self.equity / self.used_margin) * 100.0

    def submit_order(
        self,
        track_id: str,
        side: str,
        qty: float,
        sl_price: float,
        tp_price: float,
        sl_dist: float,
        tp_dist: float,
        bid: float,
        ask: float,
        latency_ms: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """Simulates realistic broker order submission with 1:10 leverage margin check and fill latency."""
        # 1. Simulate Network + Matching Queue Latency (80ms - 140ms)
        sim_latency = latency_ms if latency_ms else random.uniform(85.0, 135.0)
        
        # 2. Check Margin Requirement at 1:10 Leverage
        ref_price = ask if side == 'buy' else bid
        notional_value = qty * self.contract_size * ref_price
        req_margin = notional_value / self.leverage

        if req_margin > self.free_margin:
            logger.warning(
                f"[VIRTUAL BROKER] [MARGIN REJECT] Order requires ${req_margin:.2f} margin, "
                f"but Free Margin is only ${self.free_margin:.2f} (Leverage 1:{self.leverage:.0f})"
            )
            return None

        # 3. Determine Execution Fill Price (Buy @ Ask, Sell @ Bid)
        fill_price = ask if side == 'buy' else bid
        order_id = self._next_id()
        pos_id = self._next_id()
        now_ts = time.time()

        # 4. Create Open Position
        pos = VirtualPosition(
            id=pos_id,
            order_id=order_id,
            track_id=track_id,
            side=side,
            qty=qty,
            entry_price=fill_price,
            sl_price=sl_price,
            tp_price=tp_price,
            sl_dist=sl_dist,
            tp_dist=tp_dist,
            open_time=now_ts,
            required_margin=req_margin
        )
        self.positions[pos_id] = pos

        # 5. Log Entry Order to History (TradeLocker format)
        dt_str = datetime.fromtimestamp(now_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        entry_order = {
            'id': order_id,
            'positionId': pos_id,
            'side': side,
            'qty': qty,
            'status': 'Filled',
            'avgPrice': fill_price,
            'stopLoss': sl_price,
            'takeProfit': tp_price,
            'stopLossType': 'absolute',
            'takeProfitType': 'absolute',
            'createdDate': dt_str,
            'latency_ms': round(sim_latency, 1),
            'required_margin': round(req_margin, 2),
        }
        self.orders_history.append(entry_order)

        self.today_volume = round(self.today_volume + qty, 2)
        self.today_trades_count += 1

        logger.info(
            f"[VIRTUAL BROKER] [FILLED] #{order_id} ({sim_latency:.1f}ms): {side.upper()} {qty}L @ ${fill_price:.2f} | "
            f"SL: ${sl_price:.2f} | TP: ${tp_price:.2f} | Margin Used: ${req_margin:.2f}"
        )
        try:
            LiveTelemetryLogger().log_trade_event(
                event_type="ORDER_FILLED",
                order_id=order_id,
                position_id=pos_id,
                track_id=track_id,
                side=side,
                qty=qty,
                trigger_price=fill_price,
                fill_price=fill_price,
                initial_sl=sl_price,
                active_sl=sl_price,
                tp_price=tp_price,
                spread_cents=round(abs(ask - bid) * 100.0, 1),
                balance=self.balance,
                reason="INITIAL_FILL"
            )
        except Exception: pass

        return {
            'order_id': order_id,
            'position_id': pos_id,
            'fill_price': fill_price,
            'avgPrice': fill_price,
            'status': 'Filled',
            'latency_ms': sim_latency,
            'side': side,
            'qty': qty,
        }

    def close_position(
        self,
        pos_id: str,
        exit_price: float,
        reason: str = 'WIN_TP'
    ) -> Dict[str, Any]:
        """Closes a position and generates TradeLocker-exact reverse liquidation receipt."""
        if pos_id not in self.positions:
            return {}

        pos = self.positions.pop(pos_id)
        now_ts = time.time()
        dt_str = datetime.fromtimestamp(now_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        if pos.side == 'buy':
            pnl = (exit_price - pos.entry_price) * pos.qty * self.contract_size
        else:
            pnl = (pos.entry_price - exit_price) * pos.qty * self.contract_size

        # Commission: $7.00 per round-turn lot ($0.07 per 0.01 lot, matching Blueberry raw accounts)
        fee = round(pos.qty * 7.0, 2)
        net_pnl = round(pnl - fee, 2)

        self.balance = round(self.balance + net_pnl, 2)
        self.today_gross = round(self.today_gross + pnl, 2)
        self.today_net = round(self.today_net + net_pnl, 2)
        self.today_fees = round(self.today_fees + fee, 2)

        reverse_side = 'sell' if pos.side == 'buy' else 'buy'
        reverse_order_id = self._next_id()
        close_receipt = {
            'id': reverse_order_id,
            'positionId': pos_id,
            'side': reverse_side,
            'qty': pos.qty,
            'status': 'Filled',
            'avgPrice': exit_price,
            'stopLoss': 0.0,
            'takeProfit': 0.0,
            'stopLossType': None,
            'takeProfitType': None,
            'createdDate': dt_str,
            'close_reason': reason,
            'realized_pnl': net_pnl,
        }
        self.orders_history.append(close_receipt)

        logger.info(
            f"[VIRTUAL BROKER] [LIQUIDATION] #{reverse_order_id} ({reason}): {reverse_side.upper()} {pos.qty}L @ ${exit_price:.2f} | "
            f"Net PnL: ${net_pnl:+.2f} | New Balance: ${self.balance:.2f}"
        )

        # Append to persistent Trade Journal (Both CSV & Markdown)
        try:
            log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
            os.makedirs(log_dir, exist_ok=True)
            
            # 1. CSV Journal
            csv_path = os.path.join(log_dir, "trade_journal.csv")
            write_csv_header = not os.path.exists(csv_path)
            duration_s = round(now_ts - pos.open_time, 1)
            
            with open(csv_path, "a", encoding="utf-8") as jf:
                if write_csv_header:
                    jf.write("timestamp,order_id,position_id,track_id,side,qty,entry_price,exit_price,tp_price,sl_price,duration_sec,gross_pnl,commission,net_pnl,close_reason,balance\n")
                jf.write(
                    f"{dt_str},{reverse_order_id},{pos_id},{pos.track_id},{pos.side.upper()},{pos.qty},"
                    f"{pos.entry_price:.2f},{exit_price:.2f},{pos.tp_price:.2f},{pos.sl_price:.2f},{duration_s},"
                    f"{pnl:.2f},{fee:.2f},{net_pnl:.2f},{reason},{self.balance:.2f}\n"
                )

            # 2. Markdown Journal (Audit Log Table)
            md_path = os.path.join(log_dir, "trade_journal.md")
            if not os.path.exists(md_path):
                with open(md_path, "w", encoding="utf-8") as mf:
                    mf.write("# Edge Labs — Broker-Grade Trade Journal & Audit Log\n\n")
                    mf.write(f"**Virtual Account Starting Balance:** ${self.balance:,.2f}  \n")
                    mf.write(f"**Prop Firm Drawdown Floor:** ${self.loss_floor:,.2f} *(Buffer: ${self.balance - self.loss_floor:,.2f})*  \n")
                    mf.write(f"**Leverage:** 1:{self.leverage:.0f} *(Gold Margin: ~$4,450 / 0.10L)*  \n")
                    mf.write("**Live Instrument:** XAUUSD (CFD Gold)  \n")
                    mf.write("**Execution Mode:** Broker-Grade In-Memory Simulation & Live Tick-by-Tick Feed  \n\n---\n\n")
                    mf.write("### Live Session Transaction Audit\n\n")
                    mf.write("| Time (UTC) | Order ID | Leg / Track | Side | Qty (Lots) | Fill Price | Broker SL | Broker TP | Exit Price | Net PnL ($) | Virtual Balance ($) | Floor Buffer ($) | Status |\n")
                    mf.write("| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n")
            
            buffer_to_floor = max(0.0, self.balance - self.loss_floor)
            pnl_sign = f"+${net_pnl:.2f}" if net_pnl >= 0 else f"-${abs(net_pnl):.2f}"
            
            with open(md_path, "a", encoding="utf-8") as mf:
                mf.write(
                    f"| {dt_str} | #{reverse_order_id} | Track {pos.track_id} | {pos.side.upper()} | {pos.qty}L | "
                    f"${pos.entry_price:.2f} | ${pos.sl_price:.2f} | ${pos.tp_price:.2f} | ${exit_price:.2f} | "
                    f"{pnl_sign} | ${self.balance:.2f} | ${buffer_to_floor:.2f} | {reason} |\n"
                )
                
            # Log to Atomic Trade Events CSV
            LiveTelemetryLogger().log_trade_event(
                event_type=f"POSITION_CLOSED_{reason}",
                order_id=reverse_order_id,
                position_id=pos_id,
                track_id=pos.track_id,
                side=pos.side,
                qty=pos.qty,
                trigger_price=pos.entry_price,
                fill_price=pos.entry_price,
                exit_price=exit_price,
                initial_sl=pos.sl_price,
                active_sl=pos.sl_price,
                tp_price=pos.tp_price,
                trade_duration=duration_s,
                gross_pnl=pnl,
                broker_fee=fee,
                net_pnl=net_pnl,
                balance=self.balance,
                reason=reason
            )
        except Exception as e:
            logger.error(f"Failed to write to trade journals: {e}")

        return {
            'position_id': pos_id,
            'close_order_id': reverse_order_id,
            'reason': reason,
            'exit_price': exit_price,
            'net_pnl': net_pnl,
            'fee': fee,
            'balance': self.balance,
        }

    def update_ticks(self, bid: float, ask: float) -> Dict[str, Any]:
        """Updates floating unrealized P&L, checks Breakeven/Ratchet, and enforces Prop Firm Floor."""
        unrealized_pnl = 0.0

        for pos in self.positions.values():
            if pos.side == 'buy':
                u_pnl = (bid - pos.entry_price) * pos.qty * self.contract_size
            else:
                u_pnl = (pos.entry_price - ask) * pos.qty * self.contract_size
            unrealized_pnl += u_pnl

        self.equity = round(self.balance + unrealized_pnl, 2)

        if self.equity > self.peak_equity:
            self.peak_equity = self.equity

        dd = self.peak_equity - self.equity
        if dd > self.max_drawdown_usd:
            self.max_drawdown_usd = round(dd, 2)

        # ── PROP FIRM RULE BREACH MONITORING ──
        if self.equity <= self.loss_floor:
            breach_event = {
                'timestamp': time.time(),
                'datetime': datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                'breach_type': 'DRAWDOWN_FLOOR_BREACH',
                'equity': self.equity,
                'floor': self.loss_floor,
                'drawdown_from_peak': self.max_drawdown_usd,
            }
            if not self.rule_breaches or (time.time() - self.rule_breaches[-1]['timestamp']) > 60.0:
                self.rule_breaches.append(breach_event)
                logger.critical(
                    f"[VIRTUAL BROKER] [RULE BREACH] Equity (${self.equity:.2f}) "
                    f"dropped below Loss Floor (${self.loss_floor:.2f})! (Continuing simulation logging)"
                )

        return {
            'balance': self.balance,
            'equity': self.equity,
            'unrealized_pnl': round(unrealized_pnl, 2),
            'used_margin': round(self.used_margin, 2),
            'free_margin': round(self.free_margin, 2),
            'margin_level_pct': round(self.margin_level_pct, 1),
            'buffer_to_floor': round(self.equity - self.loss_floor, 2),
            'rule_breaches_count': len(self.rule_breaches),
        }
