"""Edge Labs — TradeLocker API Client
Wraps the tradelocker SDK with smart rate limiting and multi-method price fetching.
"""
import os
import time
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed, FIRST_COMPLETED, wait
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from tradelocker import TLAPI
import pandas as pd
import numpy as np

# Adjust import according to the project structure
from utils.rate_limiter import AdaptiveRateLimiter


class EdgeLabsClient:
    """High-performance TradeLocker API client for XAUUSD."""
    
    def __init__(self):
        """Initialize connection, discover rate limits, resolve XAUUSD."""
        load_dotenv()
        env = os.environ.get('TL_ENVIRONMENT', 'https://demo.tradelocker.com')
        user = os.environ.get('TL_USERNAME')
        pw = os.environ.get('TL_PASSWORD')
        server = os.environ.get('TL_SERVER')
        
        if not all([env, user, pw, server]):
            raise ValueError("Missing TradeLocker credentials in .env")

        self.tl = TLAPI(environment=env, username=user, password=pw, server=server, log_level='warning')
        
        # Auto-detect XAUUSD instrument ID
        self.instrument_id = self._detect_xauusd_id()
        if not self.instrument_id:
            raise ValueError("Could not detect XAUUSD instrument ID.")

        # In-RAM Caching of Instrument Metrics (Fetched once at startup/daily)
        # Prevents unnecessary network calls during fast price execution
        self.instrument_details = self._load_instrument_details()
        self.contract_size: float = float(self.instrument_details.get('lotSize', 100.0))
        self.lot_step: float      = float(self.instrument_details.get('lotStep', 0.01))
        self.min_lot: float       = float(self.instrument_details.get('minLot', 0.01))
        self.max_lot: float       = float(self.instrument_details.get('maxLot', 50.0))
        self.tick_size: float     = 0.01
        self.leverage: float      = float(self.instrument_details.get('leverage', 100.0))
            
        # Initialize Rate Limiter
        try:
            config = self.tl.get_config()
            self.quotes_limit = 10
            self.history_limit = 3
        except Exception:
            self.quotes_limit = 10
            self.history_limit = 3

        self.rate_limiter = AdaptiveRateLimiter()
        self.rate_limiter.configure_endpoint('QUOTES', self.quotes_limit, 1.0)
        self.rate_limiter.configure_endpoint('QUOTES_HISTORY', self.history_limit, 1.0)

        # Direct High-Speed Keep-Alive HTTP Session (~120ms latency vs 1500ms old SDK)
        self._http_session = requests.Session()
        self._base_url = self.tl.get_base_url()
        self._quote_url = f"{self._base_url}/trade/quotes"
        try:
            self._route_id = self.tl.get_info_route_id(self.instrument_id)
        except Exception:
            self._route_id = None
        self._acc_num = getattr(self.tl, 'acc_num', getattr(self.tl, 'account_id', 1))

        # ThreadPool for non-blocking background fetches
        self.executor = ThreadPoolExecutor(max_workers=2)

        # Price cache
        self._last_price_time = 0.0
        self._cached_price: Optional[Dict[str, float]] = None
        self._price_lock = threading.Lock()
        self._backoff_until: float = 0.0
        self._consecutive_429: int = 0

    def _load_instrument_details(self) -> Dict[str, Any]:
        """Fetches contract metrics once on startup to be stored in RAM."""
        try:
            details = self.tl.get_instrument_details(self.instrument_id)
            if isinstance(details, dict):
                return details
        except Exception:
            pass
        return {
            'name': 'XAUUSD',
            'lotSize': 100.0,
            'lotStep': 0.01,
            'minLot': 0.01,
            'maxLot': 50.0,
            'leverage': 100.0,
        }

    def _detect_xauusd_id(self) -> Optional[int]:
        """Tries to find the instrument ID for XAUUSD."""
        symbols_to_try = ['XAUUSD', 'XAU/USD', 'Gold', 'GOLD']
        for symbol in symbols_to_try:
            try:
                inst_id = self.tl.get_instrument_id_from_symbol_name(symbol)
                if inst_id is not None:
                    return inst_id
            except Exception:
                continue
        return 4709

    def _fetch_quote_raw(self) -> Dict[str, float]:
        """High-speed single quote fetch with Keep-Alive connection pooling."""
        now = time.time()
        if now < self._backoff_until:
            remaining = self._backoff_until - now
            time.sleep(min(remaining, 2.0))

        t_req = time.perf_counter()

        # Try fast persistent HTTP session path first
        try:
            token = self.tl.get_access_token()
            headers = {
                'Authorization': f'Bearer {token}',
                'Accept': 'application/json',
                'accNum': str(self._acc_num),
                'User-Agent': 'TradeLocker Python SDK'
            }
            params = {
                'tradableInstrumentId': self.instrument_id,
            }
            if self._route_id:
                params['routeId'] = self._route_id

            resp = self._http_session.get(self._quote_url, headers=headers, params=params, timeout=2.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('s') == 'ok' and 'd' in data:
                    d = data['d']
                    ask = float(d['ap'])
                    bid = float(d['bp'])
                    self._consecutive_429 = 0
                    lat_ms = round((time.perf_counter() - t_req) * 1000.0, 1)
                    return {'bid': bid, 'ask': ask, 'spread': round(ask - bid, 2), 'ts': time.time(), 'latency_ms': lat_ms}
            elif resp.status_code == 429 or resp.status_code == 1015:
                self._handle_rate_limit_response(resp.text)
        except Exception:
            pass

        # Fallback to standard SDK method
        try:
            res = self.rate_limiter.execute('QUOTES', self.tl.get_quotes, self.instrument_id)
            if isinstance(res, dict) and 'ap' in res and 'bp' in res:
                self._consecutive_429 = 0
                ask = float(res['ap'])
                bid = float(res['bp'])
                lat_ms = round((time.perf_counter() - t_req) * 1000.0, 1)
                return {'bid': bid, 'ask': ask, 'spread': round(ask - bid, 2), 'ts': time.time(), 'latency_ms': lat_ms}
            else:
                self._handle_rate_limit_response(res)
        except Exception as e:
            self._handle_rate_limit_response(str(e))

        # If rate limited, return cached price gracefully
        if self._cached_price:
            p = dict(self._cached_price)
            p['latency_ms'] = round((time.perf_counter() - t_req) * 1000.0, 1)
            return p
        raise ValueError("Live quote unavailable during rate-limit cooldown.")

    def _handle_rate_limit_response(self, response):
        """Called when we detect a 429 or Cloudflare 1015. Back off exponentially."""
        self._consecutive_429 += 1
        backoff = min(3 * self._consecutive_429, 30)  # 3s, 6s, 9s, capped at 30s
        self._backoff_until = time.time() + backoff
        self.rate_limiter.report_429('QUOTES')

    def get_live_price(self) -> Dict[str, float]:
        """Returns cached price if <150ms old, otherwise fetches fresh."""
        with self._price_lock:
            now = time.time()
            if self._cached_price and (now - self._last_price_time) < 0.15:
                return self._cached_price

        price_data = self._fetch_quote_raw()
        with self._price_lock:
            self._cached_price = price_data
            self._last_price_time = price_data['ts']
        return price_data

    def get_live_price_multi(self) -> Dict[str, float]:
        """Fetch latest price. Uses cache if fresh, otherwise single fetch.
        
        NOTE: We intentionally use single requests (not concurrent) to avoid
        triggering Cloudflare's IP-level rate limiter (HTTP 1015). The rate
        limit allows 10 req/sec but Cloudflare blocks bursts from the same IP.
        """
        return self.get_live_price()

    def get_historical_candles(self, lookback_period: str = '3D') -> pd.DataFrame:
        """Fetches completed M5 candles. Strips the forming candle (last row if v<=2).
        Returns DataFrame with columns ['t', 'o', 'h', 'l', 'c', 'v'].
        Timestamps converted to datetime.
        """
        res = self.tl.get_price_history(
            self.instrument_id, resolution='5m', lookback_period=lookback_period)

        # Handle None response from SDK (market closed)
        if res is None:
            return pd.DataFrame()

        if not isinstance(res, pd.DataFrame):
            if isinstance(res, dict) and all(k in res for k in ['t', 'o', 'h', 'l', 'c', 'v']):
                df = pd.DataFrame(res)
            else:
                return pd.DataFrame()
        else:
            df = res.copy()

        if df.empty:
            return df

        # Check for forming candle (last row with low volume usually v<=2)
        if df.iloc[-1]['v'] <= 2:
            df = df.iloc[:-1].copy()

        if not df.empty:
            df['datetime'] = pd.to_datetime(df['t'], unit='ms')
        return df

    def get_forming_candle(self) -> Optional[Dict[str, Any]]:
        """Gets the current forming candle from history endpoint."""
        for period in ['1D', '3D']:
            try:
                res = self.tl.get_price_history(
                    self.instrument_id, resolution='5m', lookback_period=period)
                if res is None:
                    continue
                df = res if isinstance(res, pd.DataFrame) else pd.DataFrame(res)
                if not df.empty and df.iloc[-1]['v'] <= 2:
                    return df.iloc[-1].to_dict()
            except Exception:
                continue
        return None

    def get_spread(self) -> float:
        """Current spread = ask - bid."""
        return self.get_live_price()['spread']

    def get_account_state(self) -> Dict[str, Any]:
        """Returns equity, balance, margin info."""
        try:
            return self.tl.get_account_state()
        except Exception:
            return {}

    def get_instrument_details(self) -> Dict[str, Any]:
        """Returns pip size, min lot, max lot, etc for XAUUSD."""
        try:
            return self.tl.get_instrument_details(self.instrument_id)
        except Exception:
            return {}
