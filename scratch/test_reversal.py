import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.api_client import EdgeLabsClient
from core.analysis_engine import analyse_reversals, _is_green, _candle_body

try:
    client = EdgeLabsClient()
    hist = client.get_historical_candles('1D')
    forming = client.get_forming_candle()
    candles = hist.to_dict('records')

    res = analyse_reversals(candles, forming, prev_speed='medium', current_speed='fast')
    print("Reversal Signs:", res.signs)

    window = candles[-20:]
    if forming:
        window.append(forming)
    curr = window[-1]
    print(f"Current Forming Candle: O={curr['o']:.2f}, H={curr['h']:.2f}, L={curr['l']:.2f}, C={curr['c']:.2f}")

    for i in range(len(window) - 3):
        c = window[i]
        diff = abs(curr['h'] - c['h'])
        if diff <= 0.80:
            mid_lows = [w['l'] for w in window[i+1:-1]]
            dip = (c['h'] - min(mid_lows)) if mid_lows else 0
            print(f"Candle [{i-len(window)}] High={c['h']:.2f} | Diff from curr High: ${diff:.2f} | Dip between: ${dip:.2f}")
except Exception as e:
    print(f"Error: {e}")
