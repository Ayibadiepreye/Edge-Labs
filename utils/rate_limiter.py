"""Adaptive Rate Limiter for TradeLocker API
Maximizes request throughput without triggering 429 rate limit errors.
"""
import time
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Any, Optional

@dataclass 
class EndpointState:
    limit_per_interval: int = 10
    interval_seconds: float = 1.0
    current_multiplier: float = 0.80  # Start at 80% of limit
    tokens: float = 10.0
    last_refill: float = field(default_factory=time.time)
    last_429_time: float = 0.0
    consecutive_success: int = 0
    last_result: Any = None
    last_result_time: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)

class AdaptiveRateLimiter:
    def __init__(self, rate_limits: dict = None):
        self.endpoints = defaultdict(EndpointState)
        if rate_limits:
            for name, (limit, interval) in rate_limits.items():
                self.configure_endpoint(name, limit, interval)
        self.executor = ThreadPoolExecutor(max_workers=20)
    
    def configure_endpoint(self, name: str, limit: int, interval: float):
        self.endpoints[name] = EndpointState(
            limit_per_interval=limit,
            interval_seconds=interval,
            tokens=limit * 0.80
        )
    
    def _refill(self, state: EndpointState):
        now = time.time()
        elapsed = now - state.last_refill
        
        effective_rate = (state.limit_per_interval * state.current_multiplier) / state.interval_seconds
        
        added_tokens = elapsed * effective_rate
        state.tokens = min(float(state.limit_per_interval), state.tokens + added_tokens)
        state.last_refill = now

    def _acquire_token(self, state: EndpointState):
        while True:
            with state.lock:
                self._refill(state)
                
                now = time.time()
                time_since_429 = now - state.last_429_time
                
                # Exponential/Hard backoff on 429
                if time_since_429 < 2.0:
                    sleep_time = 2.0 - time_since_429
                elif state.tokens >= 1.0:
                    state.tokens -= 1.0
                    return
                else:
                    effective_rate = (state.limit_per_interval * state.current_multiplier) / state.interval_seconds
                    sleep_time = (1.0 - state.tokens) / effective_rate
            
            if sleep_time > 0:
                time.sleep(max(0.001, sleep_time))

    def execute(self, endpoint_name: str, func: Callable, *args, **kwargs) -> Any:
        """Execute a rate-limited API call. Blocks until a token is available."""
        state = self.endpoints[endpoint_name]
        self._acquire_token(state)
        
        try:
            # Can be executed in the thread pool for parallel requests
            # Currently executes inline (assumes caller can use threads)
            result = func(*args, **kwargs)
            self.report_success(endpoint_name)
            
            with state.lock:
                state.last_result = result
                state.last_result_time = time.time()
                
            return result
        except Exception as e:
            if "429" in str(e) or getattr(e, 'status_code', None) == 429:
                self.report_429(endpoint_name)
            raise

    def execute_fast(self, endpoint_name: str, func: Callable, *args, **kwargs) -> Any:
        """Execute with deduplication — returns cached result if fresh enough."""
        state = self.endpoints[endpoint_name]
        with state.lock:
            now = time.time()
            if now - state.last_result_time < 0.05 and state.last_result is not None:
                return state.last_result
                
        return self.execute(endpoint_name, func, *args, **kwargs)
    
    def report_429(self, endpoint_name: str):
        """Called when a 429 is received. Backs off."""
        state = self.endpoints[endpoint_name]
        with state.lock:
            state.last_429_time = time.time()
            state.current_multiplier = max(0.1, state.current_multiplier * 0.5)
            state.consecutive_success = 0

    def report_success(self, endpoint_name: str):
        """Called on success. Ramps up if enough consecutive successes."""
        state = self.endpoints[endpoint_name]
        with state.lock:
            state.consecutive_success += 1
            if state.consecutive_success >= 10:
                state.current_multiplier = min(0.95, state.current_multiplier + 0.05)
                state.consecutive_success = 0

    def get_stats(self) -> dict:
        """Returns current rate limiter statistics per endpoint."""
        stats = {}
        for name, state in self.endpoints.items():
            with state.lock:
                stats[name] = {
                    "limit_per_interval": state.limit_per_interval,
                    "interval_seconds": state.interval_seconds,
                    "multiplier": state.current_multiplier,
                    "tokens": state.tokens,
                    "consecutive_success": state.consecutive_success
                }
        return stats
