import sys, time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\Users\Setons\.gemini\antigravity\scratch\edge_labs_bot')
from core.api_client import EdgeLabsClient

client = EdgeLabsClient()

print("=== LIVE XAUUSD (GOLD) SPREAD AUDIT ===")
for i in range(5):
    price = client.get_live_price()
    b = price['bid']
    a = price['ask']
    s = price['spread']
    s_cents = round(s * 100, 1) if s < 1.0 else round(s, 1)
    status = "EXCELLENT (<= 8¢)" if s <= 0.08 else ("MODERATE (8¢-12¢)" if s <= 0.12 else "WIDE (> 12¢)")
    t_str = time.strftime('%H:%M:%S')
    print(f"[{t_str}] Gold Bid: ${b:.2f} | Gold Ask: ${a:.2f} | Spread: ${s:.2f} ({s_cents:.1f}¢) -> {status}")
    time.sleep(1.0)
