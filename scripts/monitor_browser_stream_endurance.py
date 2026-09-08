"""Edge Labs — Standalone Browser Streamer Endurance & Diagnostic Monitor
Mirrors the exact production BrowserPriceStreamer architecture to benchmark connection stability,
track uptime, monitor latency and tick throughput, and perform deep root-cause diagnostics
if ticks stall for >5 minutes or if the browser disconnects/throttles.

Usage:
    python scripts/monitor_browser_stream_endurance.py
"""

from __future__ import annotations
import os
import sys
import time
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

# Force UTF-8 on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    os.system('chcp 65001 > nul 2>&1')

# Ensure root directory is on Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Create logs & screenshots directories if they don't exist
os.makedirs("logs", exist_ok=True)
os.makedirs("screenshots", exist_ok=True)

# Configure Dedicated Logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/streamer_endurance_events.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("EnduranceMonitor")


class BrowserStreamEnduranceMonitor:
    """Endurance and stability diagnostic runner for TradeLocker browser datafeed."""

    def __init__(self, max_runtime_sec: Optional[float] = None, stall_threshold_sec: float = 300.0):
        load_dotenv()
        self.env = os.environ.get('TL_ENVIRONMENT', 'https://demo.tradelocker.com').rstrip('/')
        self.user = os.environ.get('TL_USERNAME', 'bonnieprincewill6@gmail.com')
        self.pw = os.environ.get('TL_PASSWORD', "bgxv'u4XJa6_")
        self.server = os.environ.get('TL_SERVER', 'BLBRY')

        self.max_runtime_sec = max_runtime_sec
        self.stall_threshold_sec = stall_threshold_sec  # 5 minutes (300 seconds)

        # Telemetry State
        self.start_time: float = 0.0
        self.connected_time: float = 0.0
        self.total_ticks: int = 0
        self.last_tick_time: float = 0.0
        self.last_bar_ts: int = 0
        self.last_bar_advance_time: float = 0.0
        self.last_price: float = 0.0
        self.last_spread: float = 0.0

        # Performance & Health Metrics
        self.latencies_ms: List[float] = []
        self.throttle_events: List[Dict[str, Any]] = []
        self.stall_warnings: List[Dict[str, Any]] = []
        self.diagnostic_results: Optional[Dict[str, Any]] = None
        self.termination_reason: str = "RUNNING"
        self.is_connected: bool = False

    def format_duration(self, seconds: float) -> str:
        """Formats seconds into HH:MM:SS."""
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hrs:02d}h {mins:02d}m {secs:02d}s"

    async def run(self):
        """Main asynchronous runner for browser streaming endurance test."""
        from playwright.async_api import async_playwright

        self.start_time = time.time()
        logger.info("=" * 80)
        logger.info("🚀 EDGE LABS — BROWSER STREAMER ENDURANCE & DIAGNOSTIC MONITOR")
        logger.info(f"Target Environment : {self.env}")
        logger.info(f"Account User       : {self.user}")
        logger.info(f"Broker Server      : {self.server}")
        logger.info(f"Stall Timeout Gate : {self.stall_threshold_sec}s (5 minutes)")
        logger.info("=" * 80)

        try:
            async with async_playwright() as p:
                logger.info("🌐 Launching Chromium browser with Anti-Throttling & Anti-Detection flags...")
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-renderer-backgrounding',
                        '--disable-background-timer-throttling',
                        '--disable-backgrounding-occluded-windows',
                        '--disable-features=CalculateNativeWinOcclusion'
                    ]
                )

                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                    viewport={'width': 1920, 'height': 1080}
                )
                page = await context.new_page()

                logger.info(f"🔗 Navigating to {self.env}...")
                await page.goto(self.env, wait_until='domcontentloaded', timeout=30000)

                # 1. Dismiss Cookie Consent
                for sel in ['button:has-text("Allow All")', 'button:has-text("Allow Mandatory")', 'button:has-text("Accept")']:
                    try:
                        b = page.locator(sel).first
                        if await b.is_visible(timeout=1500):
                            await b.click(force=True)
                            logger.info("🍪 Cookie banner accepted.")
                            break
                    except Exception:
                        pass

                # 2. Select Broker / Prop Tab
                logger.info("📋 Selecting 'Broker / Prop' login tab...")
                bp = page.locator('text="Broker / Prop"').first
                await bp.click(force=True)
                await page.wait_for_timeout(1000)

                # 3. Enter Credentials
                logger.info(f"🔑 Entering credentials for {self.user} on server {self.server}...")
                await page.fill('#email', self.user)
                await page.fill('#password', self.pw)
                await page.fill('#server', self.server)

                # 4. Direct DOM Submit
                logger.info("🚀 Submitting login credentials via DOM...")
                await page.evaluate("() => { const f = document.getElementById('kc-form-login') || document.querySelector('form'); if(f) f.submit(); }")

                logger.info("⏳ Waiting for TradeLocker TradingView WebGL workspace initialization (8s)...")
                await page.wait_for_timeout(8000)

                # 5. Lock chart to 1-second resolution
                logger.info("⚡ Locking TradingView chart resolution to 1-second (1s)...")
                try:
                    await page.mouse.click(600, 400)
                    await page.keyboard.type("1s")
                    await page.wait_for_timeout(500)
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(4000)
                except Exception as chart_err:
                    logger.warning(f"⚠️ Chart resolution lock warning: {chart_err}")

                self.is_connected = True
                self.connected_time = time.time()
                logger.info(f"✅ Browser Price Streamer Connected! URL: {page.url}")
                logger.info("📊 Commencing High-Frequency In-Memory Quote Polling (30ms cycle)...")

                last_status_print = time.time()
                last_warning_time = 0.0

                # Streaming Loop
                while True:
                    loop_start = time.perf_counter()
                    now = time.time()

                    # Check max runtime if specified
                    if self.max_runtime_sec and (now - self.start_time) >= self.max_runtime_sec:
                        self.termination_reason = "MAX_RUNTIME_REACHED"
                        logger.info(f"⏱️ Maximum designated runtime ({self.max_runtime_sec}s) reached.")
                        break

                    # Memory Quote Evaluation
                    try:
                        t0 = time.perf_counter()
                        data = await page.evaluate("""async () => {
                            try {
                                if (window.tvWidget && window.tvWidget.activeChart) {
                                    const chart = window.tvWidget.activeChart();
                                    const raw = await chart.exportData({ includeTime: true, includeSeries: true });
                                    if (raw && raw.data && raw.data.length > 0) {
                                        const last = raw.data[raw.data.length - 1];
                                        const c = parseFloat(last[4]);
                                        const b_ts = parseInt(last[0]);
                                        if (c > 1000.0) {
                                            return {
                                                success: true,
                                                price: c,
                                                high: parseFloat(last[2]),
                                                low: parseFloat(last[3]),
                                                vol: parseFloat(last[5] || 1.0),
                                                bar_ts: b_ts,
                                                spread: 0.08
                                            };
                                        }
                                    }
                                }
                                return { success: false, reason: 'NO_CHART_DATA' };
                            } catch(e) {
                                return { success: false, err: e.message };
                            }
                        }""")
                        eval_latency = round((time.perf_counter() - t0) * 1000.0, 3)
                        self.latencies_ms.append(eval_latency)
                        if len(self.latencies_ms) > 1000:
                            self.latencies_ms.pop(0)

                        # Check for Chromium JS Throttling (latency > 300ms)
                        if eval_latency > 300.0:
                            throttle_entry = {
                                "timestamp": now,
                                "latency_ms": eval_latency,
                                "uptime_sec": round(now - self.start_time, 1)
                            }
                            self.throttle_events.append(throttle_entry)
                            logger.warning(f"⚠️ [THROTTLE DETECTED] Page evaluation latency spiked to {eval_latency:.2f}ms (Uptime: {self.format_duration(now - self.start_time)})")

                    except Exception as eval_ex:
                        logger.error(f"❌ Error evaluating in-memory chart quotes: {eval_ex}")
                        data = {"success": False, "err": str(eval_ex)}

                    # Process Quote Data
                    if data.get('success'):
                        mid_p = float(data['price'])
                        spread = float(data.get('spread', 0.08))
                        bar_ts = int(data.get('bar_ts', 0))

                        self.total_ticks += 1
                        self.last_tick_time = now
                        self.last_price = mid_p
                        self.last_spread = spread

                        # Track Bar Timestamp Advance
                        if bar_ts > self.last_bar_ts:
                            self.last_bar_ts = bar_ts
                            self.last_bar_advance_time = now
                        elif self.last_bar_advance_time == 0.0:
                            self.last_bar_advance_time = now

                    # Check Stall Condition
                    stall_duration = (now - self.last_bar_advance_time) if self.last_bar_advance_time > 0 else (now - self.connected_time)

                    if stall_duration >= 5.0 and (now - last_warning_time) >= 15.0:
                        last_warning_time = now
                        warn_entry = {
                            "timestamp": now,
                            "stall_duration_sec": round(stall_duration, 1),
                            "bar_ts": self.last_bar_ts,
                            "uptime_sec": round(now - self.start_time, 1)
                        }
                        self.stall_warnings.append(warn_entry)
                        logger.warning(
                            f"⚠️ [DATA STALL] No new bar advance for {stall_duration:.1f}s | "
                            f"Last Bar TS: {self.last_bar_ts} | "
                            f"Last Price: ${self.last_price:.2f} | "
                            f"Uptime: {self.format_duration(now - self.start_time)}"
                        )

                    # Trigger Deep Diagnostics if Stalled > 5 Minutes (300s)
                    if stall_duration >= self.stall_threshold_sec:
                        logger.critical(
                            f"🚨 [5-MINUTE STALL TRIGGERED] Datafeed has been motionless for {stall_duration:.1f}s (>{self.stall_threshold_sec}s). "
                            f"Initiating Comprehensive Root-Cause Diagnostics..."
                        )
                        self.termination_reason = "TICK_STALL_EXCEEDED_5_MINUTES"
                        self.diagnostic_results = await self._run_deep_diagnostics(page)
                        break

                    # Periodic Telemetry Status Line (every 10s)
                    if now - last_status_print >= 10.0:
                        last_status_print = now
                        active_uptime = now - self.start_time
                        streaming_duration = max(0.01, now - self.connected_time)
                        avg_tps = self.total_ticks / streaming_duration
                        avg_lat = (sum(self.latencies_ms[-50:]) / len(self.latencies_ms[-50:])) if self.latencies_ms else 0.0

                        logger.info(
                            f"🟢 [UPTIME: {self.format_duration(active_uptime)}] | "
                            f"Ticks: {self.total_ticks:,} ({avg_tps:.1f} ticks/s) | "
                            f"Latency: {avg_lat:.2f}ms | "
                            f"Gold: ${self.last_price:.2f} (Spread: {self.last_spread:.2f}) | "
                            f"Stall Time: {stall_duration:.1f}s"
                        )

                    # Sleep 30ms for standard streaming frequency
                    await asyncio.sleep(0.03)

                # Close Browser
                try:
                    await browser.close()
                except Exception:
                    pass

        except Exception as fatal_e:
            self.termination_reason = f"FATAL_DISCONNECT: {type(fatal_e).__name__} - {fatal_e}"
            logger.exception(f"💥 Fatal browser disconnect encountered: {fatal_e}")

        finally:
            self._generate_diagnostic_report()

    async def _run_deep_diagnostics(self, page) -> Dict[str, Any]:
        """Performs deep inspection of browser DOM, network status, Cloudflare challenge, and TradingView state."""
        diag: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "current_url": page.url,
            "page_title": "",
            "is_online": True,
            "cloudflare_detected": False,
            "auth_redirect_detected": False,
            "tradingview_widget_mounted": False,
            "error_modals_detected": [],
            "root_cause_analysis": "",
            "screenshot_path": "",
            "html_dump_path": ""
        }

        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_file = f"screenshots/streamer_stall_diagnostic_{ts_str}.png"
        html_file = f"logs/streamer_stall_dump_{ts_str}.html"

        try:
            # 1. Capture Full Screenshot
            await page.screenshot(path=screenshot_file, full_page=True)
            diag["screenshot_path"] = os.path.abspath(screenshot_file)
            logger.info(f"📸 Diagnostic screenshot captured: {screenshot_file}")
        except Exception as e:
            logger.warning(f"Could not take screenshot: {e}")

        try:
            # 2. Dump HTML snippet
            content = await page.content()
            with open(html_file, "w", encoding="utf-8") as f:
                f.write(content)
            diag["html_dump_path"] = os.path.abspath(html_file)
            logger.info(f"💾 Page HTML dumped: {html_file}")
        except Exception as e:
            logger.warning(f"Could not dump HTML: {e}")

        try:
            diag["page_title"] = await page.title()
        except Exception:
            pass

        # 3. Cloudflare & Captcha Inspection
        try:
            cf_challenge = await page.evaluate("""() => {
                const cf = document.querySelector('#challenge-running, #challenge-form, .cf-turnstile, .cf-challenge, iframe[src*="cloudflare"]');
                const textHasCf = document.body && (document.body.innerText.includes('Verify you are human') || document.body.innerText.includes('Just a moment...'));
                return !!cf || textHasCf;
            }""")
            diag["cloudflare_detected"] = bool(cf_challenge)
        except Exception:
            pass

        # 4. Auth / Session Inspection
        if "login" in page.url.lower() or "auth" in page.url.lower() or "kc-form" in page.url.lower():
            diag["auth_redirect_detected"] = True

        # 5. TradingView State Inspection
        try:
            tv_state = await page.evaluate("""() => {
                const hasTv = !!(window.tvWidget && window.tvWidget.activeChart);
                const isOnline = navigator.onLine;
                const modals = Array.from(document.querySelectorAll('.modal, .toast, [role="alert"], [class*="error"], [class*="disconnected"]'))
                    .map(m => m.innerText.trim())
                    .filter(t => t.length > 0);
                return { hasTv, isOnline, modals };
            }""")
            diag["tradingview_widget_mounted"] = tv_state.get("hasTv", False)
            diag["is_online"] = tv_state.get("isOnline", True)
            diag["error_modals_detected"] = tv_state.get("modals", [])
        except Exception as e:
            diag["error_modals_detected"].append(f"Inspection error: {e}")

        # 6. Deduce Root Cause
        now_dt = datetime.now(timezone.utc)
        weekday = now_dt.weekday() # 4 = Friday, 5 = Saturday, 6 = Sunday
        hour_utc = now_dt.hour

        # Check if Weekend market closure (Gold closes Fri 21:00 UTC to Sun 21:00 UTC)
        is_weekend_closed = (weekday == 5) or (weekday == 4 and hour_utc >= 21) or (weekday == 6 and hour_utc < 21)

        if diag["cloudflare_detected"]:
            diag["root_cause_analysis"] = "CLOUDFLARE_CHALLENGE_BLOCKED: Cloudflare Turnstile or anti-bot verification page was triggered."
        elif diag["auth_redirect_detected"]:
            diag["root_cause_analysis"] = "SESSION_EXPIRED: User was redirected back to the login/auth page due to session timeout."
        elif not diag["is_online"]:
            diag["root_cause_analysis"] = "LOCAL_NETWORK_OFFLINE: Browser detected that local network internet connection is disconnected."
        elif is_weekend_closed and diag["tradingview_widget_mounted"]:
            diag["root_cause_analysis"] = "MARKET_CLOSED_WEEKEND: Spot Gold (XAUUSD) market is currently closed for the weekend. Chart and DOM are healthy and mounted, but broker price feed is dormant until market open (Sunday 5:00 PM EST / 21:00 UTC)."
        elif not diag["tradingview_widget_mounted"]:
            diag["root_cause_analysis"] = "TRADINGVIEW_UNMOUNTED: TradingView WebGL canvas is unmounted or crashed."
        else:
            diag["root_cause_analysis"] = "BROKER_FEED_DORMANT: Browser and WebSocket session are active, but TradeLocker broker quote stream has sent no new bar updates."

        logger.info(f"🔎 Root Cause Analysis: {diag['root_cause_analysis']}")
        return diag

    def _generate_diagnostic_report(self):
        """Compiles full performance telemetry and diagnostic analysis into JSON and Markdown reports."""
        end_time = time.time()
        total_uptime_sec = max(0.01, end_time - self.start_time)
        streaming_uptime_sec = max(0.01, end_time - self.connected_time) if self.connected_time > 0 else 0.0

        avg_tps = self.total_ticks / streaming_uptime_sec if streaming_uptime_sec > 0 else 0.0
        avg_latency = (sum(self.latencies_ms) / len(self.latencies_ms)) if self.latencies_ms else 0.0
        p95_latency = sorted(self.latencies_ms)[int(len(self.latencies_ms) * 0.95)] if self.latencies_ms else 0.0

        report_data = {
            "session_summary": {
                "start_time_utc": datetime.fromtimestamp(self.start_time, timezone.utc).isoformat(),
                "end_time_utc": datetime.fromtimestamp(end_time, timezone.utc).isoformat(),
                "total_uptime_formatted": self.format_duration(total_uptime_sec),
                "total_uptime_seconds": round(total_uptime_sec, 2),
                "streaming_uptime_formatted": self.format_duration(streaming_uptime_sec),
                "streaming_uptime_seconds": round(streaming_uptime_sec, 2),
                "termination_reason": self.termination_reason
            },
            "quote_throughput": {
                "total_ticks_received": self.total_ticks,
                "average_ticks_per_second": round(avg_tps, 2),
                "last_price": self.last_price,
                "last_spread": self.last_spread,
                "last_bar_timestamp": self.last_bar_ts
            },
            "latency_and_performance": {
                "average_memory_eval_latency_ms": round(avg_latency, 3),
                "p95_memory_eval_latency_ms": round(p95_latency, 3),
                "throttle_spike_count": len(self.throttle_events),
                "throttle_events": self.throttle_events[-10:]
            },
            "stall_telemetry": {
                "stall_warning_count": len(self.stall_warnings),
                "stall_warnings": self.stall_warnings[-10:]
            },
            "deep_diagnostics": self.diagnostic_results
        }

        # 1. Save JSON Report
        json_path = "logs/streamer_endurance_report.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)
        logger.info(f"📄 JSON Diagnostic Report saved: {json_path}")

        # 2. Save Markdown Report
        md_path = "logs/streamer_endurance_report.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# Edge Labs — Browser Streamer Endurance & Diagnostic Audit\n\n")
            f.write(f"**Generated:** {datetime.now(timezone.utc).isoformat()} UTC\n\n")
            f.write(f"## 1. Session Summary\n\n")
            f.write(f"- **Total Active Uptime:** `{self.format_duration(total_uptime_sec)}` ({total_uptime_sec:.1f}s)\n")
            f.write(f"- **Streaming Uptime:** `{self.format_duration(streaming_uptime_sec)}`\n")
            f.write(f"- **Termination Status:** `{self.termination_reason}`\n")
            f.write(f"- **Total Ticks Processed:** `{self.total_ticks:,}`\n")
            f.write(f"- **Average Throughput:** `{avg_tps:.2f} ticks/second`\n")
            f.write(f"- **Avg In-Memory Latency:** `{avg_latency:.2f} ms` (P95: `{p95_latency:.2f} ms`)\n\n")

            if self.diagnostic_results:
                f.write(f"## 2. Deep Diagnostic Findings\n\n")
                f.write(f"- **Primary Root Cause:** `{self.diagnostic_results.get('root_cause_analysis', 'N/A')}`\n")
                f.write(f"- **Page URL at Termination:** `{self.diagnostic_results.get('current_url', 'N/A')}`\n")
                f.write(f"- **Cloudflare Challenge Detected:** `{self.diagnostic_results.get('cloudflare_detected', False)}`\n")
                f.write(f"- **Auth Redirect Detected:** `{self.diagnostic_results.get('auth_redirect_detected', False)}`\n")
                f.write(f"- **TradingView Canvas Active:** `{self.diagnostic_results.get('tradingview_widget_mounted', False)}`\n")
                if self.diagnostic_results.get("screenshot_path"):
                    ss_link = self.diagnostic_results['screenshot_path'].replace("\\", "/")
                    f.write(f"- **Diagnostic Screenshot:** [`{self.diagnostic_results['screenshot_path']}`](file:///{ss_link})\n")
                if self.diagnostic_results.get("html_dump_path"):
                    html_link = self.diagnostic_results['html_dump_path'].replace("\\", "/")
                    f.write(f"- **HTML Snapshot:** [`{self.diagnostic_results['html_dump_path']}`](file:///{html_link})\n\n")

            f.write(f"## 3. Throttle & Stall Telemetry\n\n")
            f.write(f"- **Total Throttle Spikes (>300ms):** `{len(self.throttle_events)}`\n")
            f.write(f"- **Total Stall Warnings:** `{len(self.stall_warnings)}`\n")
        logger.info(f"📊 Markdown Audit Report saved: {md_path}")

        # Final Terminal Summary
        print("\n" + "=" * 80)
        print("🎯 BROWSER STREAMER ENDURANCE TEST AUDIT SUMMARY")
        print("=" * 80)
        print(f"⏱️ Total Uptime       : {self.format_duration(total_uptime_sec)}")
        print(f"⚡ Total Ticks        : {self.total_ticks:,} ({avg_tps:.1f} ticks/s)")
        print(f"🚀 Average Latency    : {avg_latency:.2f}ms (P95: {p95_latency:.2f}ms)")
        print(f"⚠️ Throttle Spikes    : {len(self.throttle_events)}")
        print(f"🛑 Termination Status : {self.termination_reason}")
        if self.diagnostic_results:
            print(f"🔎 Root Cause         : {self.diagnostic_results.get('root_cause_analysis')}")
        print("=" * 80 + "\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Edge Labs Browser Streamer Endurance & Diagnostic Monitor")
    parser.add_argument("--max-runtime", type=float, default=None, help="Maximum run duration in seconds (optional, e.g. 600 for 10 min)")
    parser.add_argument("--stall-timeout", type=float, default=300.0, help="Stall timeout threshold in seconds before deep diagnostics (default: 300s / 5min)")
    args = parser.parse_args()

    monitor = BrowserStreamEnduranceMonitor(
        max_runtime_sec=args.max_runtime,
        stall_threshold_sec=args.stall_timeout
    )
    asyncio.run(monitor.run())


if __name__ == "__main__":
    main()
