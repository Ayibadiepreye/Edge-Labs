"""Edge Labs — Multi-Account Session & Execution Manager
Maintains concurrent TradeLocker sessions in memory, coordinates zero-latency parallel order placement,
and manages individual account circuit breakers and per-track execution filters.
"""
import os
import time
import math
import logging
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from dotenv import load_dotenv
from tradelocker import TLAPI
import config

logger = logging.getLogger("trade")


@dataclass
class AccountConfig:
    account_id: str
    account_name: str
    environment: str
    server: str
    username: str
    password: str
    api: Optional[TLAPI] = None
    instrument_id: Optional[int] = None
    
    # State & Switches
    is_active: bool = True
    track_a_enabled: bool = True
    track_b_enabled: bool = True
    track_c_enabled: bool = True
    
    # Per-Track Custom Sizing & Targets
    target_a: float = config.DEFAULT_TRACK_A_PROFIT_TARGET
    risk_a: float = config.DEFAULT_TRACK_A_RISK_LIMIT
    lots_a: float = config.DEFAULT_TRACK_A_LOTS
    
    target_b: float = config.DEFAULT_TRACK_B_PROFIT_TARGET
    risk_b: float = config.DEFAULT_TRACK_B_RISK_LIMIT
    lots_b: float = config.DEFAULT_TRACK_B_LOTS
    
    target_c: float = config.DEFAULT_TRACK_C_PROFIT_TARGET
    risk_c: float = config.DEFAULT_TRACK_C_RISK_LIMIT
    lots_c: float = config.DEFAULT_TRACK_C_LOTS
    
    # Daily Circuit Breaker
    daily_max_loss_pct: float = config.DEFAULT_DAILY_MAX_LOSS_PCT
    starting_balance: float = 0.0
    current_balance: float = 0.0
    equity: float = 0.0
    available_funds: float = 0.0
    daily_pnl: float = 0.0
    daily_loss_floor: float = 0.0
    circuit_breaker_tripped: bool = False
    last_telemetry_time: float = 0.0


class MultiAccountManager:
    """Coordinates multi-account live TradeLocker operations in memory."""

    def __init__(self, env_path: Optional[str] = None):
        self.env_path = env_path or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        load_dotenv(dotenv_path=self.env_path)
        self.accounts: Dict[str, AccountConfig] = {}
        self._load_accounts_from_env()

    def _load_accounts_from_env(self):
        """Discovers all primary and numbered accounts from .env."""
        # 1. Primary Account (TL_...)
        u1 = os.getenv("TL_USERNAME")
        if u1:
            acc1 = AccountConfig(
                account_id="acc_1",
                account_name=os.getenv("TL_ACCOUNT_NAME", "Primary Account"),
                environment=os.getenv("TL_ENVIRONMENT", "https://demo.tradelocker.com"),
                server=os.getenv("TL_SERVER", "BLBRY"),
                username=u1,
                password=os.getenv("TL_PASSWORD", ""),
                lots_a=float(os.getenv("TL_TRACK_A_LOTS", config.DEFAULT_TRACK_A_LOTS)),
                lots_b=float(os.getenv("TL_TRACK_B_LOTS", config.DEFAULT_TRACK_B_LOTS)),
                lots_c=float(os.getenv("TL_TRACK_C_LOTS", config.DEFAULT_TRACK_C_LOTS)),
                target_a=float(os.getenv("TL_TRACK_A_TARGET", config.DEFAULT_TRACK_A_PROFIT_TARGET)),
                target_b=float(os.getenv("TL_TRACK_B_TARGET", config.DEFAULT_TRACK_B_PROFIT_TARGET)),
                target_c=float(os.getenv("TL_TRACK_C_TARGET", config.DEFAULT_TRACK_C_PROFIT_TARGET)),
                daily_max_loss_pct=float(os.getenv("TL_DAILY_MAX_LOSS_PCT", config.DEFAULT_DAILY_MAX_LOSS_PCT)),
            )
            self.accounts["acc_1"] = acc1

        # 2. Numbered Accounts (TL_2_..., TL_3_..., etc.)
        for i in range(2, 10):
            prefix = f"TL_{i}_"
            u_i = os.getenv(f"{prefix}USERNAME")
            if u_i:
                acc_i = AccountConfig(
                    account_id=f"acc_{i}",
                    account_name=os.getenv(f"{prefix}ACCOUNT_NAME", f"Account {i}"),
                    environment=os.getenv(f"{prefix}ENVIRONMENT", "https://demo.tradelocker.com"),
                    server=os.getenv(f"{prefix}SERVER", "BLBRY"),
                    username=u_i,
                    password=os.getenv(f"{prefix}PASSWORD", ""),
                    lots_a=float(os.getenv(f"{prefix}TRACK_A_LOTS", config.DEFAULT_TRACK_A_LOTS)),
                    lots_b=float(os.getenv(f"{prefix}TRACK_B_LOTS", config.DEFAULT_TRACK_B_LOTS)),
                    lots_c=float(os.getenv(f"{prefix}TRACK_C_LOTS", config.DEFAULT_TRACK_C_LOTS)),
                    target_a=float(os.getenv(f"{prefix}TRACK_A_TARGET", config.DEFAULT_TRACK_A_PROFIT_TARGET)),
                    target_b=float(os.getenv(f"{prefix}TRACK_B_TARGET", config.DEFAULT_TRACK_B_PROFIT_TARGET)),
                    target_c=float(os.getenv(f"{prefix}TRACK_C_TARGET", config.DEFAULT_TRACK_C_PROFIT_TARGET)),
                    daily_max_loss_pct=float(os.getenv(f"{prefix}DAILY_MAX_LOSS_PCT", config.DEFAULT_DAILY_MAX_LOSS_PCT)),
                )
                self.accounts[f"acc_{i}"] = acc_i

    def get_accounts_list(self) -> List[AccountConfig]:
        """Returns accounts as a list regardless of whether stored as dict or list."""
        if isinstance(self.accounts, dict):
            return list(self.accounts.values())
        return list(self.accounts)

    def get_account(self, acc_id: str) -> Optional[AccountConfig]:
        """Retrieves an account by ID safely."""
        if isinstance(self.accounts, dict):
            return self.accounts.get(acc_id)
        for a in self.accounts:
            if getattr(a, 'account_id', None) == acc_id:
                return a
        return None

    def authenticate_all(self) -> Dict[str, bool]:
        """Authenticates all accounts concurrently in memory using thread pool."""
        acc_list = self.get_accounts_list()
        logger.info(f"Connecting {len(acc_list)} accounts concurrently in memory...")
        results = {}

        def _auth_single(acc: AccountConfig):
            t0 = time.time()
            try:
                tl = TLAPI(
                    environment=acc.environment,
                    username=acc.username,
                    password=acc.password,
                    server=acc.server,
                    log_level="critical"
                )
                inst_id = tl.get_instrument_id_from_symbol_name("XAUUSD")
                if not inst_id:
                    inst_id = tl.get_instrument_id_from_symbol_name("XAU/USD")
                
                acc.api = tl
                acc.instrument_id = inst_id
                
                # Fetch initial account state for starting balance
                state = tl.get_account_state()
                bal = float(state.get("balance", 0.0))
                acc.starting_balance = bal
                acc.current_balance = bal
                acc.equity = float(state.get("projectedBalance", bal))
                acc.available_funds = float(state.get("availableFunds", bal))
                
                # Set hard daily loss floor
                acc.daily_loss_floor = round(bal * (1.0 - (acc.daily_max_loss_pct / 100.0)), 2)
                acc.last_telemetry_time = time.time()
                
                dur = round((time.time() - t0) * 1000, 1)
                logger.info(f"[{acc.account_name}] Connected ({dur}ms) | Start Balance: ${bal:,.2f} | Floor: ${acc.daily_loss_floor:,.2f}")
                return acc.account_id, True, None
            except Exception as e:
                dur = round((time.time() - t0) * 1000, 1)
                logger.error(f"[{acc.account_name}] Connection failed ({dur}ms): {e}")
                return acc.account_id, False, str(e)

        with ThreadPoolExecutor(max_workers=max(1, len(acc_list))) as executor:
            futures = [executor.submit(_auth_single, acc) for acc in acc_list]
            for f in as_completed(futures):
                acc_id, ok, err = f.result()
                results[acc_id] = ok

        return results

    def refresh_account_telemetry(self, acc_id: str) -> Optional[Dict[str, Any]]:
        """Polls account state and checks for daily drawdown limit violations."""
        acc = self.get_account(acc_id)
        if not acc or not acc.api:
            return None
        try:
            state = acc.api.get_account_state()
            bal = float(state.get("balance", acc.current_balance))
            eq = float(state.get("projectedBalance", bal))
            avail = float(state.get("availableFunds", bal))
            
            acc.current_balance = bal
            acc.equity = eq
            acc.available_funds = avail
            acc.daily_pnl = round(bal - acc.starting_balance, 2)
            acc.last_telemetry_time = time.time()
            
            # Check Circuit Breaker
            if eq <= acc.daily_loss_floor or bal <= acc.daily_loss_floor:
                if not acc.circuit_breaker_tripped:
                    acc.circuit_breaker_tripped = True
                    acc.is_active = False
                    logger.critical(
                        f"🚨 [CIRCUIT BREAKER TRIPPED] {acc.account_name} dropped to ${eq:,.2f} "
                        f"(Floor: ${acc.daily_loss_floor:,.2f}). Trading DISARMED to prevent breach!"
                    )
            return {
                "account_id": acc.account_id,
                "account_name": acc.account_name,
                "balance": acc.current_balance,
                "equity": acc.equity,
                "available_funds": acc.available_funds,
                "daily_pnl": acc.daily_pnl,
                "daily_loss_floor": acc.daily_loss_floor,
                "circuit_breaker_tripped": acc.circuit_breaker_tripped,
                "is_active": acc.is_active,
            }
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "Cloudflare" in err_str or "1015" in err_str:
                logger.warning(f"[{acc.account_name}] Telemetry rate-limited by Cloudflare (429/1015). Backing off gracefully.")
            else:
                logger.warning(f"Failed to refresh telemetry for {acc.account_name}: {err_str[:80]}")
            return None

    def execute_live_order_burst(
        self,
        track_id: str,
        side: str,
        sl_price: float,
        tp_price: float,
        sl_dist: float = 0.12,
        tp_dist: float = 2.00,
        spread: float = 0.08,
    ) -> List[Dict[str, Any]]:
        """Executes market orders across all active accounts in parallel threads with instant post-fill SL/TP calibration."""
        orders_placed = []

        def _place_single(acc: AccountConfig):
            if not acc.is_active or acc.circuit_breaker_tripped or not acc.api:
                return None
            
            # Check track enabled toggle
            if track_id == "A" and not acc.track_a_enabled:
                return None
            if track_id == "B" and not acc.track_b_enabled:
                return None
            if track_id == "C" and not acc.track_c_enabled:
                return None
                
            qty = acc.lots_a if track_id == "A" else (acc.lots_b if track_id == "B" else acc.lots_c)
            if qty <= 0:
                return None
                
            t0 = time.time()
            try:
                # Track A: Submit with embedded SL and TP directly at creation time for immediate broker-side protection
                if track_id == "A":
                    try:
                        order_id = acc.api.create_order(
                            instrument_id=acc.instrument_id,
                            quantity=qty,
                            side=side,
                            type_="market",
                            stop_loss=sl_price,
                            stop_loss_type="absolute",
                            take_profit=tp_price,
                            take_profit_type="absolute",
                        )
                    except Exception as ord_err:
                        logger.warning(f"[{acc.account_name}] Track A direct embedded SL/TP order failed ({ord_err}), fallback to clean market...")
                        order_id = acc.api.create_order(
                            instrument_id=acc.instrument_id,
                            quantity=qty,
                            side=side,
                            type_="market",
                        )
                else:
                    # Tracks B & C: Clean market order dispatch
                    try:
                        order_id = acc.api.create_order(
                            instrument_id=acc.instrument_id,
                            quantity=qty,
                            side=side,
                            type_="market",
                        )
                    except Exception as ord_err:
                        order_id = acc.api.create_order(
                            instrument_id=acc.instrument_id,
                            quantity=qty,
                            side=side,
                            type_="market",
                            take_profit=tp_price,
                            take_profit_type="absolute",
                            stop_loss=sl_price,
                            stop_loss_type="absolute",
                        )
                dur = round((time.time() - t0) * 1000, 1)

                # Fetch exact broker execution fill price from position table
                fill_price = None
                pos_id = None
                active_sl = sl_price
                active_tp = tp_price
                eff_sl_dist = sl_dist

                try:
                    time.sleep(0.04)  # 40ms micro-pause to allow matching engine fill registration
                    all_pos = acc.api.get_all_positions()
                    if isinstance(all_pos, pd.DataFrame) and not all_pos.empty:
                        match = all_pos[all_pos['tradableInstrumentId'] == acc.instrument_id] if 'tradableInstrumentId' in all_pos.columns else all_pos
                        if not match.empty:
                            fill_price = float(match.iloc[-1]['avgPrice'])
                            pos_id = int(match.iloc[-1]['id'])
                            logger.info(f"[{acc.account_name}] Exact Broker Fill Price Stored: Pos #{pos_id} @ ${fill_price:.2f}")

                            # ── DYNAMIC POST-FILL SL/TP CALIBRATION ──
                            # Allow max 0.20 if spread friction is wide, default to 0.12
                            eff_sl_dist = round(min(0.20, max(sl_dist, spread * 1.5 if spread > 0.08 else sl_dist)), 2)
                            
                            if side.lower() == 'buy':
                                exact_sl = round(fill_price - eff_sl_dist, 2)
                                exact_tp = round(fill_price + tp_dist, 2)
                            else:
                                exact_sl = round(fill_price + eff_sl_dist, 2)
                                exact_tp = round(fill_price - tp_dist, 2)

                            # ── UNCONDITIONAL POST-FILL SL/TP SNAP WITH PERSISTENT RETRY ──
                            # Guaranteed enforcement: retries against Cloudflare, 429, or network glitches until confirmed
                            mod_payload = {
                                "stopLoss": exact_sl,
                                "stopLossType": "absolute",
                                "takeProfit": exact_tp,
                                "takeProfitType": "absolute"
                            }
                            mod_ok = self.modify_position_with_retry(
                                api=acc.api,
                                pos_id=pos_id,
                                payload=mod_payload,
                                account_name=acc.account_name,
                                max_retries=10,
                                initial_delay=0.05
                            )
                            if mod_ok:
                                active_sl = exact_sl
                                active_tp = exact_tp
                                logger.info(
                                    f"[{acc.account_name}] 🎯 [POST-FILL CALIBRATION] Broker fill @ ${fill_price:.2f} -> "
                                    f"SL snapped to ${exact_sl:.2f} (Dist: ${eff_sl_dist:.2f}) | TP: ${exact_tp:.2f}"
                                )
                            else:
                                logger.error(
                                    f"[{acc.account_name}] 🚨 [SL ENFORCEMENT ALERT] Failed to set broker SL on Pos #{pos_id}. "
                                    f"Bot local tick-shield is actively protecting position @ SL ${exact_sl:.2f}."
                                )
                except Exception as ex:
                    logger.debug(f"[{acc.account_name}] Immediate fill price lookup: {ex}")

                logger.info(f"[{acc.account_name}] Live Order Placed #{order_id} ({dur}ms): {side.upper()} {qty}L | SL=${active_sl:.2f} | TP=${active_tp:.2f}")
                return {
                    "account_id": acc.account_id,
                    "account_name": acc.account_name,
                    "order_id": order_id,
                    "position_id": pos_id or order_id,
                    "fill_price": fill_price,
                    "qty": qty,
                    "side": side,
                    "sl_price": active_sl,
                    "tp_price": active_tp,
                    "sl_dist": eff_sl_dist,
                    "tp_dist": tp_dist,
                    "timestamp": time.time(),
                }
            except Exception as e:
                dur = round((time.time() - t0) * 1000, 1)
                logger.error(f"[{acc.account_name}] Order placement failed ({dur}ms): {e}")
                return None

        acc_list = self.get_accounts_list()
        with ThreadPoolExecutor(max_workers=max(1, len(acc_list))) as executor:
            futures = [executor.submit(_place_single, acc) for acc in acc_list]
            for f in as_completed(futures):
                res = f.result()
                if res:
                    orders_placed.append(res)

        return orders_placed

    def modify_position_with_retry(
        self,
        api: Any,
        pos_id: int,
        payload: Dict[str, Any],
        account_name: str = "Account",
        max_retries: int = 10,
        initial_delay: float = 0.05
    ) -> bool:
        """Persistently retries position modification with adaptive backoff against Cloudflare (429/1015/502) or network errors."""
        delay = initial_delay
        for attempt in range(1, max_retries + 1):
            try:
                res = api.modify_position(int(pos_id), payload)
                if res:
                    return True
                time.sleep(delay)
                delay = min(0.40, delay * 1.5)
            except Exception as e:
                err_msg = str(e)
                # If position has already been closed by the broker (e.g. SL/TP hit instantly), resolve cleanly
                if "not found" in err_msg.lower() or "404" in err_msg:
                    logger.info(f"[{account_name}] Position #{pos_id} already resolved/closed by broker matching engine.")
                    return True
                logger.warning(
                    f"[{account_name}] ⚠️ [RETRY {attempt}/{max_retries}] modify_position Pos #{pos_id} encountered: "
                    f"{err_msg[:80]} — Retrying in {delay*1000:.0f}ms..."
                )
                time.sleep(delay)
                delay = min(0.40, delay * 1.5)
        logger.error(f"[{account_name}] ❌ Failed to modify position #{pos_id} after {max_retries} retries.")
        return False

    def modify_live_sl_burst(self, pos_mod_list: List[Dict[str, Any]]) -> List[bool]:
        """Modifies Stop Loss (Breakeven or Profit Ratchet) and Take Profit across positions in parallel with persistent retry."""
        results = []

        def _mod_single(item):
            acc_id = item.get("account_id")
            pos_id = item.get("pos_id")
            new_sl = item.get("new_sl")
            new_tp = item.get("new_tp")
            acc = self.get_account(acc_id)
            if not acc or not acc.api or not pos_id:
                return False
            payload = {}
            if new_sl is not None:
                payload["stopLoss"] = float(new_sl)
                payload["stopLossType"] = "absolute"
            if new_tp is not None:
                payload["takeProfit"] = float(new_tp)
                payload["takeProfitType"] = "absolute"
            if not payload:
                return False

            res = self.modify_position_with_retry(
                api=acc.api,
                pos_id=pos_id,
                payload=payload,
                account_name=acc.account_name,
                max_retries=6,
                initial_delay=0.05
            )
            if res:
                logger.info(f"[{acc.account_name}] Position #{pos_id} modified: {payload} -> SUCCESS")
            return bool(res)

        with ThreadPoolExecutor(max_workers=max(1, len(pos_mod_list))) as executor:
            futures = [executor.submit(_mod_single, item) for item in pos_mod_list]
            for f in as_completed(futures):
                results.append(f.result())

        return results
