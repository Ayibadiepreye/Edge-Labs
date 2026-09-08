# Edge Labs — Browser Streamer Endurance & Diagnostic Audit

**Generated:** 2026-09-06T19:23:38.129658+00:00 UTC

## 1. Session Summary

- **Total Active Uptime:** `00h 00m 28s` (28.6s)
- **Streaming Uptime:** `00h 00m 08s`
- **Termination Status:** `TICK_STALL_EXCEEDED_5_MINUTES`
- **Total Ticks Processed:** `271`
- **Average Throughput:** `32.36 ticks/second`
- **Avg In-Memory Latency:** `4.17 ms` (P95: `7.00 ms`)

## 2. Deep Diagnostic Findings

- **Primary Root Cause:** `MARKET_CLOSED_WEEKEND: Spot Gold (XAUUSD) market is currently closed for the weekend. Chart and DOM are healthy and mounted, but broker price feed is dormant until market open (Sunday 5:00 PM EST / 21:00 UTC).`
- **Page URL at Termination:** `https://demo.tradelocker.com/en/trade?instrument=4749`
- **Cloudflare Challenge Detected:** `False`
- **Auth Redirect Detected:** `False`
- **TradingView Canvas Active:** `True`
- **Diagnostic Screenshot:** [`C:\Users\Setons\.gemini\antigravity\scratch\edge_labs_bot\screenshots\streamer_stall_diagnostic_20260906_192337.png`](file:///C:/Users/Setons/.gemini/antigravity/scratch/edge_labs_bot/screenshots/streamer_stall_diagnostic_20260906_192337.png)
- **HTML Snapshot:** [`C:\Users\Setons\.gemini\antigravity\scratch\edge_labs_bot\logs\streamer_stall_dump_20260906_192337.html`](file:///C:/Users/Setons/.gemini/antigravity/scratch/edge_labs_bot/logs/streamer_stall_dump_20260906_192337.html)

## 3. Throttle & Stall Telemetry

- **Total Throttle Spikes (>300ms):** `0`
- **Total Stall Warnings:** `1`
