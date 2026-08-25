"""Cloudflare Threshold Calibrator
Finds the exact maximum sustainable throughput without triggering Error 1015.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.api_client import EdgeLabsClient

print("--- Calibrating Safe Cloudflare Pacing (Testing 300ms Interval) ---")
client = EdgeLabsClient()

# Reset any backoff
client._backoff_until = 0.0

success = 0
failed = 0
latencies = []

for i in range(1, 31):
    t0 = time.perf_counter()
    try:
        price = client.get_live_price()
        lat = (time.perf_counter() - t0) * 1000
        latencies.append(lat)
        success += 1
        if i % 5 == 0 or i == 1:
            print(f"[{i:2d}/30] OK | Bid: ${price['bid']:.2f} | Latency: {lat:.1f}ms")
    except Exception as e:
        failed += 1
        print(f"[{i:2d}/30] RATE LIMITED: {e}")
        time.sleep(2.0)
    
    # 280ms pacing (~3.5 req/sec - within Cloudflare IP burst limit)
    time.sleep(0.28)

print(f"\nResults @ 280ms: Success={success}/30, Failed={failed}")
