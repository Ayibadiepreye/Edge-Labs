"""Edge Labs — M5 Candle Builder
Builds and maintains M5 candles from historical seed + live price polling.
"""
import time
import math
from collections import deque
from typing import Optional, Callable
import pandas as pd
import numpy as np
from datetime import datetime, timezone

class CandleBuilder:
    def __init__(self, max_buffer: int = 500):
        self.candles = deque(maxlen=max_buffer)  # Completed candles
        self.forming_candle: Optional[dict] = None  # Current forming candle
        self.tick_buffer: deque = deque()  # Last 60 seconds of ticks
        self.tick_count_total: int = 0
        self.callbacks: list[Callable] = []  # Called on candle close
        self._last_tick_time: float = 0
    
    def seed_from_history(self, historical_df: pd.DataFrame) -> None:
        """Seeds the buffer with historical completed candles from the API.
        The last candle in the DataFrame might be the forming candle — detect this.
        A forming candle will have very low volume (v <= 5) and its timestamp
        will be within the current M5 period.
        """
        if historical_df.empty:
            return
            
        now_s = time.time()
        current_m5 = self.get_m5_boundary(now_s)
        
        for _, row in historical_df.iterrows():
            candle = {
                't': int(row['t']),
                'o': float(row['o']),
                'h': float(row['h']),
                'l': float(row['l']),
                'c': float(row['c']),
                'v': int(row['v'])
            }
            
            # Check if this is the forming candle
            # (timestamp equals the current M5 boundary, or it's the very last one and in current boundary)
            if candle['t'] == current_m5:
                self.forming_candle = candle
            else:
                self.candles.append(candle)
                
        # If no forming candle was found in history, start a new one based on the last known close if available
        if not self.forming_candle and self.candles:
            self._start_new_candle(self.candles[-1]['c'], current_m5)
    
    @staticmethod
    def get_m5_boundary(timestamp_seconds: float) -> int:
        """Returns the M5 boundary timestamp (in ms) for a given time.
        M5 boundaries: :00, :05, :10, :15, :20, :25, :30, :35, :40, :45, :50, :55
        """
        # Floor to nearest 5-minute boundary
        dt = datetime.fromtimestamp(timestamp_seconds, tz=timezone.utc)
        minute_floored = (dt.minute // 5) * 5
        boundary_dt = dt.replace(minute=minute_floored, second=0, microsecond=0)
        return int(boundary_dt.timestamp() * 1000)
    
    def on_tick(self, bid: float, ask: float, timestamp: float = None) -> None:
        """Process a new price tick. Updates forming candle and tick buffer.
        
        Args:
            bid: Current bid price
            ask: Current ask price  
            timestamp: Epoch seconds (defaults to time.time())
        """
        if timestamp is None:
            timestamp = time.time()
            
        self._last_tick_time = timestamp
        
        # 1. Add to tick buffer, prune ticks older than 60s
        self.tick_buffer.append({'bid': bid, 'ask': ask, 'ts': timestamp})
        self.tick_count_total += 1
        
        # Prune old ticks
        cutoff = timestamp - 60.0
        while self.tick_buffer and self.tick_buffer[0]['ts'] < cutoff:
            self.tick_buffer.popleft()
            
        # 2. Check if we've crossed an M5 boundary
        current_m5_boundary = self.get_m5_boundary(timestamp)
        
        if self.forming_candle is None:
            self._start_new_candle(bid, current_m5_boundary)
        elif current_m5_boundary > self.forming_candle['t']:
            # Crossed boundary
            self._close_forming_candle()
            self._start_new_candle(bid, current_m5_boundary)
            
        # 3. Update forming candle OHLC (using bid price)
        self.forming_candle['c'] = bid
        if bid > self.forming_candle['h']:
            self.forming_candle['h'] = bid
        if bid < self.forming_candle['l']:
            self.forming_candle['l'] = bid
        self.forming_candle['v'] += 1
    
    def get_all_candles(self) -> list[dict]:
        """Returns all completed candles + forming candle as list of dicts."""
        res = list(self.candles)
        if self.forming_candle:
            res.append(self.forming_candle)
        return res
    
    def get_completed_candles(self, n: int = None) -> list[dict]:
        """Returns last N completed candles (not including forming)."""
        res = list(self.candles)
        if n is not None and n > 0:
            return res[-n:]
        return res
    
    def get_forming_candle(self) -> Optional[dict]:
        """Returns the current forming candle."""
        return self.forming_candle
    
    def get_tick_velocity(self) -> float:
        """Returns ticks per minute in the last 60 seconds."""
        if not self.tick_buffer:
            return 0.0
        
        if len(self.tick_buffer) < 2:
            return float(len(self.tick_buffer))
            
        first_ts = self.tick_buffer[0]['ts']
        last_ts = self.tick_buffer[-1]['ts']
        duration_s = last_ts - first_ts
        
        if duration_s <= 0:
            return 0.0
            
        # Extrapolate to ticks per minute
        return len(self.tick_buffer) * (60.0 / max(duration_s, 1.0))
    
    def get_price_velocity(self) -> float:
        """Returns price change ($/min) in the rolling buffer."""
        if len(self.tick_buffer) < 2:
            return 0.0
            
        first = self.tick_buffer[0]
        last = self.tick_buffer[-1]
        
        price_diff = last['bid'] - first['bid']
        duration_s = last['ts'] - first['ts']
        
        if duration_s <= 0:
            return 0.0
            
        # $/min
        return price_diff * (60.0 / max(duration_s, 1.0))

    def get_instant_price_velocity(self, window_sec: float = 5.0) -> float:
        """Returns instant price velocity ($/sec) over the last 3-5 seconds."""
        if len(self.tick_buffer) < 2:
            return 0.0
        # If no new ticks arrived in last 4 seconds (market closed/frozen), velocity is zero
        if (time.time() - self._last_tick_time) > 4.0:
            return 0.0
        now = self.tick_buffer[-1]['ts']
        recent = [t for t in self.tick_buffer if (now - t['ts']) <= window_sec]
        if len(recent) < 2:
            return 0.0
        diff = recent[-1]['bid'] - recent[0]['bid']
        dur = max(1.0, recent[-1]['ts'] - recent[0]['ts'])
        return diff / dur  # $/sec

    def get_instant_tick_velocity(self, window_sec: float = 5.0) -> float:
        """Returns instant tick frequency (ticks/sec) over the last 3-5 seconds."""
        if not self.tick_buffer:
            return 0.0
        # If no new ticks arrived in last 4 seconds (market closed/frozen), tick velocity is zero
        if (time.time() - self._last_tick_time) > 4.0:
            return 0.0
        now = self.tick_buffer[-1]['ts']
        recent = [t for t in self.tick_buffer if (now - t['ts']) <= window_sec]
        dur = max(1.0, (recent[-1]['ts'] - recent[0]['ts']) if len(recent) > 1 else 1.0)
        return len(recent) / dur  # ticks/sec

    def get_recent_tick_flow(self, n: int = 5) -> list[dict]:
        """Returns the last N ticks for sub-second flow confirmation."""
        if len(self.tick_buffer) < n:
            return list(self.tick_buffer)
        return list(self.tick_buffer)[-n:]

    def get_cumulative_tick_delta(self, window_sec: float = 10.0) -> dict:
        """Calculates institutional Orderflow Delta:
        - delta_ratio: Net directional tick volume (+1.0 = 100% buy pressure, -1.0 = 100% sell)
        - acceleration: Ratio of instant tick speed vs 60s baseline
        """
        if len(self.tick_buffer) < 3:
            return {'delta_ratio': 0.0, 'up_ticks': 0, 'down_ticks': 0, 'acceleration': 1.0}

        now = self.tick_buffer[-1]['ts']
        recent = [t for t in self.tick_buffer if (now - t['ts']) <= window_sec]
        if len(recent) < 3:
            return {'delta_ratio': 0.0, 'up_ticks': 0, 'down_ticks': 0, 'acceleration': 1.0}

        up_ticks = 0
        down_ticks = 0
        for i in range(1, len(recent)):
            diff = recent[i]['bid'] - recent[i-1]['bid']
            if diff > 0.001:
                up_ticks += 1
            elif diff < -0.001:
                down_ticks += 1

        total = up_ticks + down_ticks
        delta_ratio = (up_ticks - down_ticks) / max(1, total) if total > 0 else 0.0

        # Acceleration: recent tick frequency / 60s baseline frequency
        recent_freq = len(recent) / max(0.5, window_sec)
        baseline_freq = len(self.tick_buffer) / 60.0
        accel = recent_freq / max(0.2, baseline_freq) if baseline_freq > 0 else 1.0

        return {
            'delta_ratio': round(delta_ratio, 3),
            'up_ticks': up_ticks,
            'down_ticks': down_ticks,
            'acceleration': round(accel, 2)
        }
    
    def on_candle_close(self, callback: Callable) -> None:
        """Register a callback for when a candle closes."""
        self.callbacks.append(callback)
    
    def _close_forming_candle(self) -> None:
        """Close the current forming candle and push to buffer."""
        if self.forming_candle:
            closed_candle = self.forming_candle.copy()
            self.candles.append(closed_candle)
            self.forming_candle = None
            
            for cb in self.callbacks:
                try:
                    cb(closed_candle)
                except Exception as e:
                    print(f"Error in candle close callback: {e}")
    
    def _start_new_candle(self, price: float, boundary_ts: int) -> None:
        """Start a new forming candle."""
        self.forming_candle = {
            't': boundary_ts,
            'o': price,
            'h': price,
            'l': price,
            'c': price,
            'v': 0
        }
