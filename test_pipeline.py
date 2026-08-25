"""Integration test — full data pipeline without GUI."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.api_client      import EdgeLabsClient
from core.candle_builder  import CandleBuilder
from core.analysis_engine import AnalysisEngine
import config

print("=== Edge Labs Pipeline Test ===\n")

print("[1] Connecting to TradeLocker...")
client = EdgeLabsClient()
print(f"    instrument_id={client.instrument_id}  quotes_limit={client.quotes_limit}")

print("[2] Live price (multi-concurrent)...")
price = client.get_live_price_multi()
print(f"    bid={price['bid']:.2f}  ask={price['ask']:.2f}  spread={price['spread']:.2f}")

print("[3] Today's M5 candles (1D)...")
t0 = time.time()
hist = client.get_historical_candles(lookback_period='1D')
print(f"    {len(hist)} candles  ({time.time()-t0:.1f}s)")
if not hist.empty:
    last = hist.iloc[-1]
    print(f"    last: o={last['o']:.2f}  h={last['h']:.2f}  l={last['l']:.2f}  c={last['c']:.2f}  v={last['v']}")

print("[4] Forming candle...")
forming = client.get_forming_candle()
print(f"    {forming}")

print("[5] Seeding CandleBuilder...")
builder = CandleBuilder(max_buffer=config.CANDLE_BUFFER_SIZE)
builder.seed_from_history(hist)
if forming:
    builder.forming_candle = {
        't': int(forming.get('t', CandleBuilder.get_m5_boundary(time.time()))),
        'o': float(forming.get('o', price['bid'])),
        'h': float(forming.get('h', price['bid'])),
        'l': float(forming.get('l', price['bid'])),
        'c': float(forming.get('c', price['bid'])),
        'v': int(forming.get('v', 1)),
    }
print(f"    {len(builder.candles)} completed + forming={builder.forming_candle is not None}")

print("[6] Feeding 3 live ticks...")
for i in range(3):
    p = client.get_live_price_multi()
    builder.on_tick(p['bid'], p['ask'])
    print(f"    tick {i+1}: bid={p['bid']:.2f}")
print(f"    tick_vel={builder.get_tick_velocity():.1f}/min  price_vel={builder.get_price_velocity():.4f}/min")

print("[7] Running full analysis...")
engine   = AnalysisEngine()
completed = builder.get_completed_candles()
snap = engine.analyse(
    completed_candles=completed,
    forming_candle=builder.get_forming_candle(),
    tick_velocity=builder.get_tick_velocity(),
    price_velocity=builder.get_price_velocity(),
    current_price=price['bid'],
    spread=price['spread'],
)
print(f"    direction={snap.direction.bias}  score={snap.direction.score:+.3f}")
print(f"    speed={snap.speed.classification}  tick/min={snap.speed.tick_velocity:.0f}")
print(f"    rejection={snap.rejection.level}  side={snap.rejection.side}")
print(f"    reversals={snap.reversal.signs}")
print(f"    resistance={snap.structure.nearest_resistance}  support={snap.structure.nearest_support}")
print(f"    ready_to_simulate={snap.ready_to_simulate}")

print("\n=== ALL SYSTEMS GO ===")
