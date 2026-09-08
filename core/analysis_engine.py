"""Edge Labs — Market Analysis Engine
Implements all 5 analysis dimensions from the spec:
  4.1 Direction (weighted 3-window bias)
  4.2 Speed (tick velocity + price velocity + body size)
  4.3 Rejection (wick-to-body ratio detection)
  4.4 Reversal Signs (momentum drop, color flip, engulfing, double top/bottom)
  4.5 Structure Levels (recent highs/lows from last 100 candles)
All computations are pure NumPy/Pandas — fast, in-memory.
"""
from __future__ import annotations
import numpy as np
import time
from collections import deque
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


# ──────────────────────────────────────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class DirectionResult:
    bias: str           # 'green' | 'red' | 'mixed'
    score: float        # Weighted score (-1.0 … +1.0)
    short_score: float  # Immediate 20-candle window
    main_score:  float  # Primary  100-candle window
    long_score:  float  # Background 500-candle window

@dataclass
class SpeedResult:
    classification: str   # 'fast' | 'medium' | 'slow'
    tick_velocity: float  # ticks/minute
    price_velocity: float # $/minute (absolute)
    avg_body_size: float  # avg candle body $ over last 5
    micro_step: float = 0.30  # Smallest, fastest dynamic price distance in cents ($0.20 - $0.60)
    avg_body: float = 0.0

    def __post_init__(self):
        if not self.avg_body:
            self.avg_body = self.avg_body_size

@dataclass
class RejectionResult:
    level: str   # 'none' | 'moderate' | 'strong'
    side: str    # 'upper' | 'lower' | 'both' | 'none'
    upper_ratio: float  # upper wick / body
    lower_ratio: float  # lower wick / body

@dataclass
class ReversalResult:
    has_reversal: bool
    signs: list[str] = field(default_factory=list)
    # Possible signs: 'momentum_drop', 'color_flip', 'engulfing',
    #                 'double_top', 'double_bottom'

@dataclass
class StructureLevels:
    recent_highs: list[float] = field(default_factory=list)
    recent_lows:  list[float] = field(default_factory=list)
    equal_highs:  list[float] = field(default_factory=list)
    equal_lows:   list[float] = field(default_factory=list)
    nearest_resistance: Optional[float] = None
    nearest_support:    Optional[float] = None

@dataclass
class AnalysisSnapshot:
    timestamp: float
    direction: DirectionResult
    speed:     SpeedResult
    rejection: RejectionResult
    reversal:  ReversalResult
    structure: StructureLevels
    spread:    float = 0.0
    tick_noise: float = 0.06
    adverse_noise_dist: float = 0.05
    adverse_noise_vel: float = 0.02
    is_sweetspot_ignition: bool = False
    sweetspot_min: float = 0.10
    sweetspot_max: float = 0.55
    directional_displacement: float = 0.0
    opening_window_cleared: bool = True
    wick_established: bool = True
    counter_noise_ok: bool = True
    sample_size_used: int = 3
    ready_to_simulate: bool = False
    impulse_side: str = 'buy'


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _candle_body(candle: dict) -> float:
    return abs(candle['c'] - candle['o'])

def _candle_upper_wick(candle: dict) -> float:
    return candle['h'] - max(candle['o'], candle['c'])

def _candle_lower_wick(candle: dict) -> float:
    return min(candle['o'], candle['c']) - candle['l']

def _is_green(candle: dict) -> bool:
    return candle['c'] >= candle['o']

def _calculate_ignition_sweetspot(completed_candles: list[dict], n_lookback: int = 10) -> tuple[float, float]:
    """Analyzes recent completed candles to determine the historical breakout ignition sweet-spot:
    - min_ignition: Minimum displacement needed to confirm directional commitment and avoid color flips (e.g. 15-20% of avg body).
    - max_ignition: Maximum allowable displacement before the candle is considered extended / chasing (e.g. 40-45% of avg body).
    """
    if not completed_candles:
        return 0.10, 0.55
    window = completed_candles[-n_lookback:]
    bodies = [_candle_body(c) for c in window if _candle_body(c) > 0.10]
    avg_body = float(np.mean(bodies)) if bodies else 1.00

    min_ignition = max(0.10, round(avg_body * 0.18, 2))
    max_ignition = max(0.35, round(avg_body * 0.42, 2))
    return min_ignition, max_ignition


# ──────────────────────────────────────────────────────────────────────────────
# 4.1  Direction
# ──────────────────────────────────────────────────────────────────────────────

def analyse_direction(
    completed_candles: list[dict],
    forming_candle: Optional[dict] = None
) -> DirectionResult:
    """Classifies directional bias balancing 70% immediate active momentum with 30% recent 20-candle context."""
    all_candles = list(completed_candles)
    if forming_candle:
        all_candles.append(forming_candle)

    if not all_candles:
        return DirectionResult('mixed', 0.0, 0.0, 0.0, 0.0)

    def _score_window(window: list[dict]) -> float:
        if not window:
            return 0.0
        bodies = np.array([_candle_body(c) for c in window], dtype=float)
        avg_body = float(np.mean(bodies)) if len(bodies) > 0 else 0.0
        total = 0.0
        for i, c in enumerate(window):
            sign = 1.0 if _is_green(c) else -1.0
            bonus = 0.5 if (avg_body > 0 and bodies[i] > config.LARGE_BODY_MULTIPLIER * avg_body) else 0.0
            total += sign + sign * bonus
        max_possible = len(window) * (1.0 + config.LARGE_BODY_BONUS)
        return total / max_possible if max_possible > 0 else 0.0

    # 1. Immediate Active Momentum Flow (Active Candle + Last 3 Bars) -> 70% Weight
    active_seq = all_candles[-4:]
    ref = active_seq[-1]
    ref_body = ref['c'] - ref['o']
    ref_dir = 1.0 if ref_body > 0 else (-1.0 if ref_body < 0 else 0.0)
    ref_strength = min(1.0, abs(ref_body) / 1.50)
    active_score = (ref_dir * ref_strength * 0.50) + (_score_window(active_seq) * 0.50)

    # 2. Recent 20-Candle Wave Context -> 30% Weight
    recent_20_window = all_candles[-min(20, len(all_candles)):]
    context_score = _score_window(recent_20_window)

    # Combined Directional Momentum (70% Immediate Active Flow, 30% Recent 20-Candle Context)
    weighted = (active_score * 0.70) + (context_score * 0.30)

    eps = 0.05
    if weighted > eps:
        bias = 'green'
    elif weighted < -eps:
        bias = 'red'
    else:
        bias = 'mixed'

    return DirectionResult(bias, round(weighted, 4), round(active_score, 4),
                           round(context_score, 4), 0.0)


# ──────────────────────────────────────────────────────────────────────────────
# 4.2  Speed & Active Momentum
# ──────────────────────────────────────────────────────────────────────────────

def analyse_speed(
    tick_velocity:  float,   # ticks/minute  (from CandleBuilder)
    price_velocity: float,   # $/minute       (from CandleBuilder, absolute)
    recent_candles: list[dict],
    n_body: int = 5
) -> SpeedResult:
    """Classify market speed based on active real-time tick velocity and price displacement."""
    price_vel_abs = abs(price_velocity)

    # Average body of last N candles
    bodies = [_candle_body(c) for c in recent_candles[-n_body:]] if recent_candles else []
    avg_body = float(np.mean(bodies)) if bodies else 0.0

    # 1. Classify Speed Tier based strictly on Active Real-Time Velocity:
    # Priority is given to live market movement (ticks/min and $/min velocity)
    is_live_fast = (tick_velocity >= config.FAST_SPEED_TICKS or price_vel_abs >= config.FAST_SPEED_PRICE_VEL)
    is_live_medium = (tick_velocity >= config.MEDIUM_SPEED_TICKS or price_vel_abs >= config.MEDIUM_SPEED_PRICE_VEL)

    # When market is closed / idle (very low live ticks), hard-lock classification to slow
    if tick_velocity < 15.0 and price_vel_abs < 0.10:
        classification = 'slow'
    elif is_live_fast:
        classification = 'fast'
    elif is_live_medium:
        classification = 'medium'
    else:
        classification = 'slow'

    # 2. Universal Adaptive Impulse Step:
    # Fully dynamic — scales naturally from 20 cents up to multi-dollar moves based on live volatility
    if classification == 'fast':
        # Fast momentum: Capture the first 25% of the average candle impulse
        micro_step = max(0.20, round(avg_body * 0.25, 2) if avg_body > 0 else 0.30)
    elif classification == 'medium':
        # Medium momentum: Capture 35% of the average candle impulse
        micro_step = max(0.30, round(avg_body * 0.35, 2) if avg_body > 0 else 0.50)
    else:
        # Slow regime
        micro_step = max(0.50, round(avg_body * 0.50, 2) if avg_body > 0 else 1.00)

    return SpeedResult(classification, round(tick_velocity, 1),
                       round(price_vel_abs, 4), round(avg_body, 4),
                       micro_step=round(micro_step, 2))


# ──────────────────────────────────────────────────────────────────────────────
# 4.3  Rejection
# ──────────────────────────────────────────────────────────────────────────────

def analyse_rejection(candle: dict) -> RejectionResult:
    """Detect wick rejection on the forming (or any) candle per spec §4.3."""
    body = _candle_body(candle)
    upper = _candle_upper_wick(candle)
    lower = _candle_lower_wick(candle)

    # Avoid division by zero — treat zero-body doji as body = 0.001
    eff_body = body if body > 0.001 else 0.001

    upper_ratio = upper / eff_body
    lower_ratio = lower / eff_body

    strong_upper = upper_ratio > config.REJECTION_STRONG_WICK
    strong_lower = lower_ratio > config.REJECTION_STRONG_WICK
    mod_upper    = upper_ratio > config.REJECTION_MODERATE_WICK
    mod_lower    = lower_ratio > config.REJECTION_MODERATE_WICK

    # Determine side
    if strong_upper and strong_lower:
        level, side = 'strong', 'both'
    elif strong_upper:
        level, side = 'strong', 'upper'
    elif strong_lower:
        level, side = 'strong', 'lower'
    elif mod_upper and mod_lower:
        # Both wicks moderate — treat as strong per spec ("long wicks on both ends")
        level, side = 'strong', 'both'
    elif mod_upper:
        level, side = 'moderate', 'upper'
    elif mod_lower:
        level, side = 'moderate', 'lower'
    else:
        level, side = 'none', 'none'

    return RejectionResult(level, side, round(upper_ratio, 3), round(lower_ratio, 3))


# ──────────────────────────────────────────────────────────────────────────────
# 4.4  Reversal Signs
# ──────────────────────────────────────────────────────────────────────────────

def analyse_reversals(
    completed_candles: list[dict],
    forming_candle:    Optional[dict],
    prev_speed:        Optional[str] = None,
    current_speed:     Optional[str] = None,
) -> ReversalResult:
    """Dynamic Kinetic Drag & Orderflow Absorption Engine (§4.4).
    Replaces static lagging geometric patterns with real-time micro-physics:
    1. Momentum Decay: Rapid velocity drop or shrinking candle impulse bodies.
    2. Kinetic Drag (Orderflow Absorption): Opposing wick drag >= 25% absorbing pressure.
    3. Color Flip: Active candle reversing back through open.
    4. Over-Expansion: Extended > $3.00 from open without pullback (exhaustion risk).
    """
    signs: list[str] = []
    all_c = list(completed_candles)
    forming = forming_candle

    # 1. Momentum Decay
    if len(all_c) >= 3:
        last3 = all_c[-3:]
        colors = [_is_green(c) for c in last3]
        if len(set(colors)) == 1:
            bodies = [_candle_body(c) for c in last3]
            if bodies[0] > bodies[1] > bodies[2]:
                signs.append('momentum_drop')
    speed_rank = {'fast': 2, 'medium': 1, 'slow': 0}
    if (prev_speed and current_speed and
            speed_rank.get(current_speed, 0) < speed_rank.get(prev_speed, 0)):
        if 'momentum_drop' not in signs:
            signs.append('momentum_drop')

    # 2. Color Flip
    if forming and len(all_c) >= 3:
        last3_colors = [_is_green(c) for c in all_c[-3:]]
        if len(set(last3_colors)) == 1:
            if _is_green(forming) != last3_colors[0]:
                signs.append('color_flip')

    # 3. Kinetic Drag (Orderflow Absorption) on Forming Candle
    if forming:
        total_range = max(0.01, forming['h'] - forming['l'])
        if total_range >= 0.25:
            if _is_green(forming):
                upper_drag = (forming['h'] - forming['c']) / total_range
                if upper_drag >= 0.25:
                    signs.append('absorption_upper')
            else:
                lower_drag = (forming['c'] - forming['l']) / total_range
                if lower_drag >= 0.25:
                    signs.append('absorption_lower')

    # 4. Over-Expansion Guard (> $3.00 expansion from open)
    if forming:
        expansion = abs(forming['c'] - forming['o'])
        if expansion >= 3.00:
            signs.append('over_expanded')

    return ReversalResult(has_reversal=len(signs) > 0, signs=signs)


# ──────────────────────────────────────────────────────────────────────────────
# 4.5  Structure Levels
# ──────────────────────────────────────────────────────────────────────────────

def analyse_structure(
    completed_candles: list[dict],
    current_price:     float,
    lookback: int = 100,
    tolerance: float = 0.0010  # 0.1% tolerance for "equal" levels
) -> StructureLevels:
    """Find recent highs/lows and equal levels per spec §4.5."""
    window = completed_candles[-lookback:]
    if not window:
        return StructureLevels()

    highs = np.array([c['h'] for c in window])
    lows  = np.array([c['l'] for c in window])

    # Find swing highs (local maxima)
    swing_highs = []
    for i in range(1, len(highs) - 1):
        if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
            swing_highs.append(float(highs[i]))

    # Find swing lows (local minima)
    swing_lows = []
    for i in range(1, len(lows) - 1):
        if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
            swing_lows.append(float(lows[i]))

    # Find equal highs/lows (within tolerance)
    def _find_equal_levels(levels: list[float]) -> list[float]:
        equal = []
        seen: list[float] = []
        for lvl in levels:
            for s in seen:
                if abs(lvl - s) / max(s, 0.01) < tolerance:
                    if lvl not in equal:
                        equal.append(round(lvl, 2))
                    break
            seen.append(lvl)
        return equal

    equal_highs = _find_equal_levels(swing_highs)
    equal_lows  = _find_equal_levels(swing_lows)

    # Nearest resistance (above current price)
    above = [h for h in swing_highs if h > current_price]
    nearest_resistance = min(above) if above else None

    # Nearest support (below current price)
    below = [l for l in swing_lows if l < current_price]
    nearest_support = max(below) if below else None

    return StructureLevels(
        recent_highs=[round(h, 2) for h in sorted(swing_highs, reverse=True)[:5]],
        recent_lows =[round(l, 2) for l in sorted(swing_lows)[:5]],
        equal_highs =equal_highs[:3],
        equal_lows  =equal_lows[:3],
        nearest_resistance=round(nearest_resistance, 2) if nearest_resistance else None,
        nearest_support   =round(nearest_support,    2) if nearest_support    else None,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Main: Full Analysis Snapshot
# ──────────────────────────────────────────────────────────────────────────────

class AnalysisEngine:
    """Runs all 5 analysis modules and returns a unified snapshot with dynamic in-memory candle lifecycle calibration."""

    def __init__(self):
        self._prev_speed: Optional[str] = None
        self._prev_snapshot: Optional[AnalysisSnapshot] = None
        self._candle_lifecycle_memory: deque = deque(maxlen=50)  # In-memory completed candle lifecycle database
        self._active_candle_t: Optional[int] = None
        self._active_pre_breakout_dip: float = 0.0
        self._active_expansion: float = 0.0

    def _update_candle_lifecycle_memory(self, forming_candle: Optional[dict]):
        """Tracks the active forming candle's entire journey from open to completion in RAM."""
        if forming_candle:
            c_t = forming_candle.get('t')
            open_p = forming_candle.get('o', 0.0)
            high_p = forming_candle.get('h', 0.0)
            low_p = forming_candle.get('l', 0.0)
            curr_c = forming_candle.get('c', 0.0)

            # If brand new candle started, archive the completed profile
            if self._active_candle_t is not None and self._active_candle_t != c_t:
                profile = {
                    'pre_breakout_dip': round(self._active_pre_breakout_dip, 3),
                    'expansion': round(self._active_expansion, 3),
                    'body': round(abs(curr_c - open_p), 3) if open_p > 0 else 0.0,
                }
                self._candle_lifecycle_memory.append(profile)
                self._active_pre_breakout_dip = 0.0
                self._active_expansion = 0.0

            self._active_candle_t = c_t
            if open_p > 0:
                is_green = (curr_c >= open_p)
                if is_green:
                    dip = max(0.0, open_p - low_p)
                    push = max(0.0, high_p - open_p)
                else:
                    dip = max(0.0, high_p - open_p)
                    push = max(0.0, open_p - low_p)

                self._active_pre_breakout_dip = max(self._active_pre_breakout_dip, dip)
                self._active_expansion = max(self._active_expansion, push)

    def _determine_dynamic_sample_size(self, completed_candles: list[dict]) -> int:
        """Dynamically adjusts the number of in-memory candle profiles to analyze:
        - Frequent directional flips or chop: Expands to 5-8 candles for statistical confirmation.
        - Clean, consistent trend: Focuses on the last 2-3 candles for instant, responsive calibration.
        """
        if not completed_candles or len(completed_candles) < 3:
            return max(2, min(5, len(self._candle_lifecycle_memory)))

        recent = completed_candles[-6:]
        colors = [_is_green(c) for c in recent]
        flips = sum(1 for i in range(1, len(colors)) if colors[i] != colors[i-1])

        if flips >= 3:
            return min(len(self._candle_lifecycle_memory), 8) if len(self._candle_lifecycle_memory) > 0 else 5
        elif flips == 0:
            return 2
        else:
            return 4

    def get_dynamic_sweetspot_window(self, completed_candles: list[dict], orderflow_delta: Optional[dict] = None) -> tuple[float, float, int]:
        """Dynamically computes the non-reversing sweet-spot entry threshold from in-memory observed candle lifecycles,
        with dynamic sample sizing and high-conviction bypass."""
        sample_size = self._determine_dynamic_sample_size(completed_candles)
        
        # Strong signal bypass (Explosive delta >= 0.45): tighter sample size for immediate capture
        if orderflow_delta and isinstance(orderflow_delta, dict) and abs(orderflow_delta.get('delta_ratio', 0.0)) >= 0.45:
            sample_size = 2

        if len(self._candle_lifecycle_memory) >= 2:
            subset = list(self._candle_lifecycle_memory)[-sample_size:]
            dips = [p['pre_breakout_dip'] for p in subset if p['pre_breakout_dip'] > 0.02]
            expansions = [p['expansion'] for p in subset if p['expansion'] > 0.10]
            avg_dip = float(np.median(dips)) if dips else 0.12
            avg_exp = float(np.mean(expansions)) if expansions else 1.00

            min_sweetspot = max(0.10, min(0.20, round(avg_dip * 1.30, 2)))  # Clears opposing pullback vibration (10¢-20¢)
            max_sweetspot = max(0.35, min(0.65, round(avg_exp * 0.42, 2)))  # Prevents late top-buying (35¢-65¢)
            return min_sweetspot, max_sweetspot, sample_size
        elif self._active_pre_breakout_dip > 0.02:
            min_sweetspot = max(0.10, min(0.20, round(self._active_pre_breakout_dip * 1.30, 2)))
            max_sweetspot = max(0.35, min(0.65, round(max(0.80, self._active_expansion) * 0.40, 2)))
            return min_sweetspot, max_sweetspot, 1
        else:
            return 0.12, 0.50, 1

    def analyse(
        self,
        completed_candles: list[dict],
        forming_candle: Optional[dict],
        tick_velocity: float,
        price_velocity: float,
        current_price: float,
        spread: float,
        recent_ticks: Optional[list] = None,
        orderflow_delta: Optional[dict] = None,
        tick_noise: Any = 0.06,
    ) -> AnalysisSnapshot:
        """Run full 5-D analysis pipeline per Section 4."""
        # 0. In-Memory Candle Lifecycle Profiling
        self._update_candle_lifecycle_memory(forming_candle)

        # 4.1 Direction
        direction = analyse_direction(completed_candles, forming_candle)

        # 4.2 Speed
        speed = analyse_speed(tick_velocity, price_velocity,
                                completed_candles, n_body=5)

        # 4.3 Rejection — analyse forming candle if exists, else last completed
        ref_candle = forming_candle if forming_candle else (
            completed_candles[-1] if completed_candles else None
        )
        rejection = analyse_rejection(ref_candle) if ref_candle else RejectionResult('none', 'none', 0.0, 0.0)

        # 4.4 Reversals
        reversal = analyse_reversals(
            completed_candles, forming_candle,
            prev_speed=self._prev_speed,
            current_speed=speed.classification
        )
        self._prev_speed = speed.classification

        # 4.5 Structure
        structure = analyse_structure(completed_candles, current_price)

        impulse_side = 'buy' if (ref_candle and _is_green(ref_candle)) else 'sell'
        if direction.bias == 'green':
            impulse_side = 'buy'
        elif direction.bias == 'red':
            impulse_side = 'sell'

        # 1. Institutional Order Flow Delta (CVD) Validation
        delta_ok = True
        if orderflow_delta:
            d_ratio = orderflow_delta.get('delta_ratio', 0.0)
            if impulse_side == 'buy':
                delta_ok = (d_ratio >= 0.40)  # Strong net buy imbalance
            else:
                delta_ok = (d_ratio <= -0.40) # Strong net sell imbalance

        # Directional Displacement Calculation (Eliminates opposing opening wick traps)
        if ref_candle:
            c_open = ref_candle.get('o', current_price)
            c_close = ref_candle.get('c', current_price)
            c_high = ref_candle.get('h', current_price)
            c_low = ref_candle.get('l', current_price)
            c_ts = ref_candle.get('t', 0)
            
            # Elapsed seconds in the current M5 candle
            now_ms = time.time() * 1000
            elapsed_sec = max(0.0, (now_ms - c_ts) / 1000.0) if c_ts > 0 else 999.0
            
            if impulse_side == 'buy':
                directional_disp = round(c_close - c_open, 2)
                is_correct_color = (directional_disp > 0)
                wick_established = bool(c_low < (c_open - 0.02) or elapsed_sec >= 20.0)
            else:
                directional_disp = round(c_open - c_close, 2)
                is_correct_color = (directional_disp > 0)
                wick_established = bool(c_high > (c_open + 0.02) or elapsed_sec >= 20.0)
        else:
            directional_disp = 0.0
            is_correct_color = False
            wick_established = True
            elapsed_sec = 999.0

        # 2. Dynamic Momentum Ignition & Breakout Trigger (Requires >= 12¢ Directional Expansion)
        breakout_ok = False
        if completed_candles and len(completed_candles) >= 1:
            prev_c = completed_candles[-1]
            if impulse_side == 'buy' and (current_price >= (prev_c['h'] - 0.05) or directional_disp >= 0.12):
                breakout_ok = True
            elif impulse_side == 'sell' and (current_price <= (prev_c['l'] + 0.05) or directional_disp >= 0.12):
                breakout_ok = True
        else:
            breakout_ok = bool(directional_disp >= 0.12)

        # 3. Dynamic Sweet-Spot Ignition Window (Directional Expansion)
        min_ign, max_ign, sample_size = self.get_dynamic_sweetspot_window(completed_candles, orderflow_delta)
        is_early_ignition = bool(is_correct_color and (min_ign <= directional_disp <= max_ign))
        direction_ok = (direction.bias != 'mixed')
        
        # 4. Opening 20-Second Wick Probe Protection (Allows analysis every tick, blocks premature execution unless extreme surge)
        is_extreme_surge = bool(orderflow_delta and abs(orderflow_delta.get('delta_ratio', 0.0)) >= 0.50 and speed.price_velocity >= 0.30 and directional_disp >= 0.15)
        opening_window_cleared = bool((elapsed_sec >= 20.0) or is_extreme_surge)

        # Parse real-time opposing counter-trend adverse noise
        if isinstance(tick_noise, dict):
            noise_dist = tick_noise.get('adverse_distance', 0.05)
            noise_vel = tick_noise.get('adverse_velocity', 0.02)
        else:
            noise_dist = float(tick_noise) if tick_noise else 0.05
            noise_vel = 0.02

        # 5. Net Directional Tick Flow Stream Confirmation
        flow_ok = True
        if recent_ticks and len(recent_ticks) >= 3:
            net_tick_move = (recent_ticks[-1]['bid'] - recent_ticks[0]['bid'])
            if impulse_side == 'buy':
                flow_ok = (net_tick_move >= -0.01)  # No immediate hard drop against the move
            else:
                flow_ok = (net_tick_move <= 0.01)   # No immediate hard pop against the short

        # 6. Spread Gate: Only execute when spread is compressed (<= 8¢) so TP distance stays short and fast
        spread_val = spread if spread < 5 else spread / 100.0
        spread_ok = (spread_val <= 0.08)

        # 7. Rejection & Clean Airflow Check (Wick Drag < 18% for clean frictionless runway)
        rejection_ok = (rejection.upper_ratio < 0.18 if impulse_side == 'buy' else rejection.lower_ratio < 0.18)
        
        # 8. Directional absorption defense: block BUY on upper absorption, block SELL on lower absorption
        if impulse_side == 'buy' and ('absorption_upper' in reversal.signs or 'over_expanded' in reversal.signs):
            reversal_ok = False
        elif impulse_side == 'sell' and ('absorption_lower' in reversal.signs or 'over_expanded' in reversal.signs):
            reversal_ok = False
        else:
            reversal_ok = not reversal.has_reversal

        # 9. Structure Clearance: Ensure price has open space before nearest S/R
        min_structure_room = 1.50
        if impulse_side == 'buy' and structure.nearest_resistance is not None:
            structure_ok = (structure.nearest_resistance - current_price) >= min_structure_room
        elif impulse_side == 'sell' and structure.nearest_support is not None:
            structure_ok = (current_price - structure.nearest_support) >= min_structure_room
        else:
            structure_ok = True

        # 10. Explosive Kinetic Expansion Capacity (Strictly reject stagnant / ranging candles)
        speed_ok = (speed.price_velocity >= 0.12 or speed.tick_velocity >= 25.0)
        not_stagnant = (speed.avg_body_size >= 0.90 or speed.classification in ['medium', 'fast'])

        # 11. Circadian Session Gating & High-Conviction Institutional Delta Filter
        # Strict delta conviction (Delta Ratio >= 0.38 on Buy, <= -0.38 on Sell) ensures smart money aggression
        utc_hour = datetime.now(timezone.utc).hour
        is_expansion_session = (7 <= utc_hour <= 17)
        if orderflow_delta:
            d_ratio = orderflow_delta.get('delta_ratio', 0.0)
            required_delta = 0.35 if is_expansion_session else 0.45
            if impulse_side == 'buy':
                delta_ok = (d_ratio >= required_delta)
            else:
                delta_ok = (d_ratio <= -required_delta)

        # 12. Preceding Candle Absorption Barrier (Prevents buying directly into trapped overhead limit walls)
        prior_wick_ok = True
        if completed_candles and len(completed_candles) >= 1:
            prior_c = completed_candles[-1]
            p_range = max(0.01, prior_c['h'] - prior_c['l'])
            if impulse_side == 'buy':
                p_upper_wick = (prior_c['h'] - max(prior_c['o'], prior_c['c'])) / p_range
                prior_wick_ok = (p_upper_wick <= 0.35)
            else:
                p_lower_wick = (min(prior_c['o'], prior_c['c']) - prior_c['l']) / p_range
                prior_wick_ok = (p_lower_wick <= 0.35)

        # 13. 3-Candle Exhaustion / Over-Extension Guard (Prevents buying at the climax of a 3-candle run)
        exhaustion_ok = True
        if completed_candles and len(completed_candles) >= 3:
            cum_disp = abs(completed_candles[-1]['c'] - completed_candles[-3]['o'])
            if cum_disp >= 6.00:
                exhaustion_ok = False  # Fatigue detected: wait for fresh pause

        # 14. Dynamic Anti-Chop Quality Index & Velocity Override (Protects Track A, B, and C)
        if completed_candles and len(completed_candles) >= 3:
            recent_5 = completed_candles[-5:]
            tot_bodies = sum(_candle_body(c) for c in recent_5)
            tot_ranges = sum((c['h'] - c['l']) for c in recent_5)
            body_ratio = (tot_bodies / tot_ranges) if tot_ranges > 0 else 0.5
            dynamic_chop_clean = (body_ratio >= 0.40)
        else:
            dynamic_chop_clean = True

        expansion_capacity_ok = dynamic_chop_clean or (speed.price_velocity >= 0.12 or speed.tick_velocity >= 25.0)

        # Counter-Noise Excursion Gate (Protects against deep opposing wicks & adverse velocity in analysis)
        counter_noise_ok = (noise_dist <= 0.12 and noise_vel <= 0.60)

        ready = (spread_ok and direction_ok and breakout_ok and delta_ok and not_stagnant and expansion_capacity_ok and
                 is_early_ignition and opening_window_cleared and counter_noise_ok and rejection_ok and reversal_ok and
                 structure_ok and flow_ok and speed_ok and prior_wick_ok and exhaustion_ok)

        snap = AnalysisSnapshot(
            timestamp=time.time(),
            direction=direction,
            speed=speed,
            rejection=rejection,
            reversal=reversal,
            structure=structure,
            spread=round(spread, 2),
            tick_noise=round(noise_dist, 3),
            adverse_noise_dist=round(noise_dist, 3),
            adverse_noise_vel=round(noise_vel, 3),
            is_sweetspot_ignition=is_early_ignition,
            sweetspot_min=round(min_ign, 2),
            sweetspot_max=round(max_ign, 2),
            directional_displacement=round(directional_disp, 2),
            opening_window_cleared=opening_window_cleared,
            wick_established=wick_established,
            counter_noise_ok=counter_noise_ok,
            sample_size_used=sample_size,
            ready_to_simulate=ready,
            impulse_side=impulse_side,
        )
        self._prev_snapshot = snap
        return snap

    def get_last_snapshot(self) -> Optional[AnalysisSnapshot]:
        return self._prev_snapshot
