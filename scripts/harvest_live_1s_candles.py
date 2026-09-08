import asyncio
import os
import sys
import time
from datetime import datetime, timezone
import pandas as pd
from dotenv import load_dotenv
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

BOT_DIR = r"C:\Users\Setons\.gemini\antigravity\scratch\edge_labs_bot"
DATA_DIR = os.path.join(BOT_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

load_dotenv(os.path.join(BOT_DIR, '.env'))

ENV = os.environ.get('TL_ENVIRONMENT', 'https://demo.tradelocker.com').rstrip('/')
USER = os.environ.get('TL_USERNAME', 'bonnieprincewill6@gmail.com')
PW = os.environ.get('TL_PASSWORD', "bgxv'u4XJa6_")
SERVER = os.environ.get('TL_SERVER', 'BLBRY')

today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
CSV_PATH = os.path.join(DATA_DIR, f"live_1s_feed_{today_str}.csv")
LATEST_CSV_PATH = os.path.join(DATA_DIR, "cache_1s_live.csv")

seen_timestamps = set()

if os.path.exists(CSV_PATH):
    try:
        with open(CSV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                p = line.strip().split(",")
                if p and p[0] not in ['t', '0', 'timestamp']:
                    try:
                        seen_timestamps.add(int(float(p[0])))
                    except Exception: pass
        print(f"[HARVESTER] Pre-seeded {len(seen_timestamps):,} existing bars from {os.path.basename(CSV_PATH)}")
    except Exception as e:
        print(f"[HARVESTER WARNING] Could not parse existing CSV: {e}")

async def run_harvester():
    print("==========================================================================================================")
    print("📥 EDGE LABS — CONTINUOUS LIVE 1-SECOND BROKER CANDLE HARVESTER (PRIMARY ACCOUNT 1)")
    print(f"   • Destination CSV: {CSV_PATH}")
    print(f"   • Account/Server:  {USER} ({SERVER})")
    print(f"   • Resolution:      1-Second (1S) Genuine Broker OHLCV Feed")
    print("==========================================================================================================\n")

    while True:
        try:
            async with async_playwright() as p:
                print("[HARVESTER] Launching Chromium browser engine...")
                browser = await p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
                )
                context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
                page = await context.new_page()

                print(f"[HARVESTER] Navigating to TradeLocker ({ENV})...")
                await page.goto(ENV, wait_until='domcontentloaded', timeout=20000)

                # Cookie banner
                for sel in ['button:has-text("Allow All")', 'button:has-text("Allow Mandatory")', 'button:has-text("Accept")']:
                    try:
                        b = page.locator(sel).first
                        if await b.is_visible(timeout=1000):
                            await b.click(force=True)
                            break
                    except Exception: pass

                # Select "Broker / Prop"
                print("[HARVESTER] Selecting Broker / Prop tab...")
                bp = page.locator('text="Broker / Prop"').first
                await bp.click(force=True)
                await page.wait_for_timeout(800)

                # Fill credentials
                print(f"[HARVESTER] Entering credentials for Primary Account 1 ({USER} | {SERVER})...")
                await page.fill('#email', USER)
                await page.fill('#password', PW)
                await page.fill('#server', SERVER)

                # Direct DOM Submit
                print("[HARVESTER] Submitting login via DOM form submit...")
                await page.evaluate("() => { const f = document.getElementById('kc-form-login') || document.querySelector('form'); if(f) f.submit(); }")

                await page.wait_for_timeout(8000)

                # Switch chart to 1s
                print("[HARVESTER] Locking chart to 1-second resolution...")
                await page.mouse.click(600, 400)
                await page.keyboard.type("1s")
                await page.wait_for_timeout(400)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(4000)

                print("✅ [HARVESTER] 1-Second Chart locked! Beginning continuous live harvesting loop...\n")

                last_report_time = time.time()
                collected_this_session = 0

                while True:
                    res = await page.evaluate("""async () => {
                        try {
                            if (window.tvWidget && window.tvWidget.activeChart) {
                                const chart = window.tvWidget.activeChart();
                                const raw = await chart.exportData({ includeTime: true, includeSeries: true });
                                return { success: true, data: raw.data };
                            }
                            return { success: false };
                        } catch(e) {
                            return { success: false, err: e.message };
                        }
                    }""")

                    if res.get('success') and res.get('data'):
                        rows = res['data']
                        new_bars = []

                        for r in rows:
                            if len(r) >= 5:
                                ts = int(float(r[0]))
                                if ts not in seen_timestamps:
                                    seen_timestamps.add(ts)
                                    dt_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                                    o = float(r[1])
                                    h = float(r[2])
                                    l = float(r[3])
                                    c = float(r[4])
                                    v = float(r[5]) if len(r) > 5 else 1.0
                                    new_bars.append({
                                        't': ts,
                                        'o': o,
                                        'h': h,
                                        'l': l,
                                        'c': c,
                                        'v': v,
                                        'datetime_utc': dt_str
                                    })

                        if new_bars:
                            collected_this_session += len(new_bars)
                            write_header = not os.path.exists(CSV_PATH)
                            df_new = pd.DataFrame(new_bars)
                            
                            with open(CSV_PATH, 'a', encoding='utf-8') as f:
                                df_new.to_csv(f, header=write_header, index=False)

                            with open(LATEST_CSV_PATH, 'a', encoding='utf-8') as f:
                                df_new.to_csv(f, header=not os.path.exists(LATEST_CSV_PATH), index=False)

                    if time.time() - last_report_time >= 15.0:
                        last_report_time = time.time()
                        now_utc = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
                        print(f"[{now_utc}] 📊 [HARVESTER] Total Bars: {len(seen_timestamps):,} | Session New: +{collected_this_session:,} bars")

                    await asyncio.sleep(1.0)

        except Exception as e:
            print(f"[HARVESTER ERROR] Streamer hitch: {e}. Reconnecting in 3 seconds...")
            await asyncio.sleep(3.0)

if __name__ == '__main__':
    asyncio.run(run_harvester())
