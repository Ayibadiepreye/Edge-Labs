"""Cloudflare Endurance Test
Sends 100 high-speed price requests over Keep-Alive connection to test for 429/1015 blocks.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.api_client import EdgeLabsClient

print("--- Testing Persistent Keep-Alive Stream under Load (100 Requests) ---")
client = EdgeLabsClient()

success_count = 0
fail_count = 0
latencies = []

t_start = time.time()
for i in range(1, 101):
    t0 = time.perf_counter()
    try:
        price = client.get_live_price()
        lat = (time.perf_counter() - t0) * 1000
        latencies.append(lat)
        success_count += 1
        if i % 20 == 0 or i == 1:
            print(f"Req #{i:3d}: OK | Bid: ${price['bid']:.2f} | Latency: {lat:.1f}ms")
    except Exception as e:
        fail_count += 1
        print(f"Req #{i:3d}: FAILED -> {e}")
    
    # Safe pacing: 120ms (~7-8 req/s, staying comfortably below 10/s)
    time.sleep(0.12)

total_duration = time.time() - t_start
print("\n=== Cloudflare Endurance Benchmark Results ===")
print(f"Total Requests Sent:    {success_count + fail_count}")
print(f"Successful Requests:    {success_count} / 100")
print(f"Blocked / 429 Errors:   {fail_count}")
print(f"Total Test Time:        {total_duration:.2f} seconds")
print(f"Effective Throughput:   {success_count / total_duration:.2f} req/sec")
print(f"Average Latency:        {sum(latencies)/len(latencies):.1f} ms")
print(f"Fastest Response:       {min(latencies):.1f} ms")
print(f"Slowest Response:       {max(latencies):.1f} ms")
if fail_count == 0:
    print("Verdict: 100% CLEAN. Keep-Alive connection is stable and accepted by Cloudflare!")
