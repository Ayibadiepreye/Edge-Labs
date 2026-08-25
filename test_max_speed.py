"""Test Full 10 Req/Sec Direct Stream
Benchmarks pure /trade/quotes Keep-Alive streaming at maximum speed (~9 req/s).
"""
import sys, os, time, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.api_client import EdgeLabsClient

print("--- Testing Full 9-10 Req/Sec Pure Keep-Alive Stream (50 Requests) ---")
client = EdgeLabsClient()

token = client.tl.get_access_token()
route_id = client.tl.get_info_route_id(client.instrument_id)
acc_num = getattr(client.tl, 'acc_num', getattr(client.tl, 'account_id', 1))

headers = {
    'Authorization': f'Bearer {token}',
    'Accept': 'application/json',
    'accNum': str(acc_num),
    'User-Agent': 'TradeLocker Python SDK'
}
url = f'{client.tl.get_base_url()}/trade/quotes'
params = {
    'tradableInstrumentId': client.instrument_id,
    'routeId': route_id
}

session = requests.Session()

# Warmup
r0 = session.get(url, headers=headers, params=params)
print("Warmup:", r0.json().get('s'))

success = 0
failed = 0
latencies = []
t_start = time.time()

for i in range(1, 51):
    t0 = time.perf_counter()
    try:
        r = session.get(url, headers=headers, params=params, timeout=1.5)
        lat = (time.perf_counter() - t0) * 1000
        if r.status_code == 200:
            d = r.json().get('d', {})
            latencies.append(lat)
            success += 1
            if i % 10 == 0 or i == 1:
                print(f"[{i:2d}/50] OK | Bid: ${d.get('bp'):.2f} | Latency: {lat:.1f}ms")
        else:
            failed += 1
            print(f"[{i:2d}/50] HTTP {r.status_code}: {r.text[:80]}")
    except Exception as e:
        failed += 1
        print(f"[{i:2d}/50] Exception: {e}")
    
    # 110ms pacing (~9 requests/second)
    time.sleep(0.11)

duration = time.time() - t_start
print("\n=== Pure Stream Benchmark Results ===")
print(f"Total Sent:       {success + failed}")
print(f"Successful:       {success} / 50")
print(f"Failed / Blocked: {failed}")
print(f"Total Time:       {duration:.2f} s")
print(f"Effective Rate:   {success / duration:.2f} req/sec")
print(f"Average Latency:  {sum(latencies)/len(latencies):.1f} ms")
print(f"Fastest Latency:  {min(latencies):.1f} ms")
