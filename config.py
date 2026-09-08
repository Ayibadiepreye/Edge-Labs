"""Edge Labs — XAUUSD Scalping Bot Configuration
All editable parameters per Section 11 of the spec.
"""

# === TRADING TARGETS ===
BASE_PROFIT_TARGET = 1000  # USD target per trade
MAX_LOSS_ALLOWED = 10      # USD max loss per trade (Hard-capped <= $10)
MAX_DAILY_EXECUTIONS = 2   # Hard cap on daily trades

# === INSTRUMENT ===
SYMBOL_NAMES = ["XAUUSD", "XAU/USD", "GOLD", "XAUUSDm", "Gold"]  # Auto-detect list
TIMEFRAME = "5m"           # M5 candles
CANDLE_BUFFER_SIZE = 500   # Rolling buffer max candles

# === SPREAD ===
SPREAD_MAX = 20            # Max spread in pips (approx $2.00 for Gold)

# === SPEED CLASSIFICATION ===
FAST_SPEED_BODY = 2.00     # USD per 5 min candle body
MEDIUM_SPEED_BODY = 1.00   
SLOW_SPEED_BODY = 0.50     
FAST_SPEED_TICKS = 100     # Ticks per minute
MEDIUM_SPEED_TICKS = 50    
SLOW_SPEED_TICKS = 20      
FAST_SPEED_PRICE_VEL = 0.50   # $/min
MEDIUM_SPEED_PRICE_VEL = 0.20
SLOW_SPEED_PRICE_VEL = 0.10

# === DIRECTION WEIGHTS ===
DIRECTION_WINDOW_SHORT = 20    # Immediate window candle count
DIRECTION_WINDOW_MAIN = 100    # Primary window
DIRECTION_WINDOW_LONG = 500    # Background window
DIRECTION_WEIGHT_SHORT = 0.30
DIRECTION_WEIGHT_MAIN = 0.60
DIRECTION_WEIGHT_LONG = 0.10
LARGE_BODY_MULTIPLIER = 1.5    # Body > 1.5x avg gets bonus
LARGE_BODY_BONUS = 0.5

# === REJECTION ===
REJECTION_MODERATE_WICK = 0.3  # Wick/body ratio for moderate
REJECTION_STRONG_WICK = 1.0    # Wick/body ratio for strong
REJECTION_LOT_REDUCTION = 0.70 # Lot multiplier for moderate rejection

# === SIMULATION ===
SIMULATION_COUNT = 3
SIMULATION_SPEED_VARIANT_HIGH = 1.25
SIMULATION_SPEED_VARIANT_LOW = 0.75

# === POSITION MANAGEMENT ===
BE_TRIGGER_BUFFER = 1.0        # Multiplier of SL distance before breakeven
PARTIAL_CLOSE_AT = 0.50        # Fraction of TP distance for partial close

# === ORDER CHUNKING ===
CHUNK_MAX_LOTS = 3

# === POLLING ===
POLL_INTERVAL_MS = 250         # High-speed sub-second polling (~4 ticks/sec)
QUOTES_RATE_LIMIT = 10         # From API config: 10 req/sec
HISTORY_RATE_LIMIT = 3         # From API config: 3 req/sec

# === TP/SL DISTANCES BY SPEED (Dynamic Cents Scalping) ===
# Gold micro-bursts move 20¢ to 60¢ in seconds
TP_DISTANCE = {'fast': (0.20, 0.45), 'medium': (0.35, 0.65), 'slow': (0.50, 0.90)}
SL_DISTANCE = {'fast': (0.10, 0.20), 'medium': (0.15, 0.25), 'slow': (0.20, 0.35)}

# === EXECUTION TOGGLE & MODE ===
LIVE_EXECUTION_ENABLED = False  # Set True to execute live orders on TradeLocker across active accounts
EXECUTION_PROFILE = "PROPFIRM_5K"  # Options: "PROPFIRM_5K", "PERSONAL_FULL", "CUSTOM"

# === DEFAULT PROPFIRM 5K SCALING PRESETS (1:10 Gold Leverage Margin Safe) ===
DEFAULT_TRACK_A_PROFIT_TARGET = 20.0   # USD target (+20:1 RR on 0.10 Lot)
DEFAULT_TRACK_A_RISK_LIMIT = 1.0       # USD max loss per trade (-$1.00 stop)
DEFAULT_TRACK_A_LOTS = 0.10

DEFAULT_TRACK_B_PROFIT_TARGET = 10.0   # USD target (+30:1 RR on 0.03 Lots)
DEFAULT_TRACK_B_RISK_LIMIT = 0.36      # USD max loss per trade (-$0.36 stop)
DEFAULT_TRACK_B_LOTS = 0.03

DEFAULT_TRACK_C_PROFIT_TARGET = 10.0   # USD target (+30:1 RR on 0.03 Lots)
DEFAULT_TRACK_C_RISK_LIMIT = 0.36      # USD max loss per trade (-$0.36 stop)
DEFAULT_TRACK_C_LOTS = 0.03

# === DAILY DRAWDOWN CIRCUIT BREAKER ===
DEFAULT_DAILY_MAX_LOSS_PCT = 0.4188     # Halts trading when daily loss touches $20.00 (0.4188% on $4775.66 balance)
TELEMETRY_POLL_INTERVAL_SEC = 300      # 5 minutes background telemetry interval (anti-Cloudflare jittered)
WEB_SERVER_PORT = 8899                 # Mobile PWA Control Center Port (Tailscale & Local Web)

# === UI ===
CHART_CANDLES_VISIBLE = 100    # How many candles visible on chart at once
UI_UPDATE_INTERVAL_MS = 100    # UI refresh rate

