"""Test what get_historical_candles returns on a weekend."""
import sys, os, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from core.api_client import EdgeLabsClient

client = EdgeLabsClient()
print("Connected. id=", client.instrument_id)

for lb in ['1D', '3D', '7D']:
    try:
        df = client.get_historical_candles(lookback_period=lb)
        is_empty = df.empty if hasattr(df, 'empty') else 'N/A'
        print(f"{lb}: type={type(df).__name__}, empty={is_empty}, len={len(df)}")
        if hasattr(df, 'empty') and not df.empty:
            print(f"  columns: {list(df.columns)}")
            print(f"  last row: {df.iloc[-1].to_dict()}")
            break
    except Exception as e:
        print(f"{lb}: ERROR: {e}")
        traceback.print_exc()

print("\nDone.")
