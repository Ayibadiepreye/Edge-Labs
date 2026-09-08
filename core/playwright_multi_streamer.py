"""Edge Labs — Playwright Multi-Timeframe Chart Streamer
Maintains live, unthrottled 1S, 1M, and 5M chart data directly from TradeLocker's TradingView charting engine.
Builds and maintains all 3 timeframes directly from the browser stream to completely bypass Cloudflare rate limits.
REST API is reserved exclusively for order execution.
"""

import asyncio
import os
import sys
import json
import time
import logging
import threading
import pandas as pd
from typing import Optional, Callable, Dict, List, Any
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from core.multi_tf_analysis_engine import MultiTFTradeCoordinator
from core.virtual_broker import VirtualBrokerAccount

logger = logging.getLogger("chart_streamer")


class PlaywrightChartStreamer:
    """Streams live chart data across multiple timeframes directly from TradeLocker browser memory."""

    def __init__(self, coordinator: MultiTFTradeCoordinator):
        self.coordinator = coordinator
        self.is_running = False
        self.m5_candles: List[Dict[str, Any]] = []
        self.m1_candles: List[Dict[str, Any]] = []
        self.recent_1s_bars: List[Dict[str, Any]] = []
        self.forming_m1: Optional[Dict[str, Any]] = None
        self.forming_m5: Optional[Dict[str, Any]] = None
        self.latest_bid: float = 0.0
        self.latest_ask: float = 0.0
        self._thread: Optional[threading.Thread] = None

    def start_live_stream(self):
        """Launches the background Playwright browser chart streamer."""
        if self.is_running:
            return
        self.is_running = True
        self._thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self._thread.start()
        logger.info("🚀 [PLAYWRIGHT STREAMER] Live Chromium chart streamer launched in background (Bypassing Cloudflare).")

    def _run_async_loop(self):
        """Runs the asyncio event loop for Playwright."""
        asyncio.run(self._browser_stream_loop())

    async def _browser_stream_loop(self):
        """Connects to TradeLocker and reads window.tvWidget.activeChart().exportData() continuously."""
        from playwright.async_api import async_playwright
        load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

        env = os.environ.get('TL_ENVIRONMENT', 'https://demo.tradelocker.com')
        user = os.environ.get('TL_USERNAME', 'bonnieprincewill6@gmail.com')
        pw = os.environ.get('TL_PASSWORD', "bgxv'u4XJa6_")
        server = os.environ.get('TL_SERVER', 'BLBRY')

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
                )
                context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
                page = await context.new_page()

                logger.info(f"Connecting to TradeLocker Web Streamer ({env})...")
                await page.goto(env, wait_until='networkidle', timeout=45000)

                # Cookie & login handling
                try:
                    btn = page.locator('button:has-text("Allow All"), button:has-text("Allow Mandatory")').first
                    if await btn.is_visible(timeout=3000): await btn.click(force=True)
                except Exception: pass

                try:
                    b_tab = page.locator('button:has-text("Broker / Prop")').first
                    if await b_tab.is_visible(timeout=3000): await b_tab.click(force=True)
                except Exception: pass

                await page.locator('#email').fill(user, force=True)
                await page.locator('#password').fill(pw, force=True)

                server_input = page.locator('input[placeholder*="server" i], input[aria-label*="server" i]').first
                if await server_input.is_visible(timeout=2000):
                    await server_input.fill(server, force=True)
                    await page.keyboard.press("Enter")

                await page.locator('button[type="submit"]:has-text("Log in"), button:has-text("Log in")').first.click(force=True)
                await page.wait_for_timeout(10000)

                # Switch chart to 1s resolution
                await page.mouse.click(500, 400)
                await page.keyboard.type("1s")
                await page.wait_for_timeout(500)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(5000)

                logger.info("✅ [PLAYWRIGHT STREAMER] 1S/1M/5M live browser stream established!")

                last_processed_ts = 0

                while self.is_running:
                    # Direct TradingView in-memory chart export hook
                    export_data = await page.evaluate("""async () => {
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

                    if export_data.get('success') and export_data.get('data'):
                        rows = export_data['data']
                        if rows:
                            latest_row = rows[-1]
                            ts = int(float(latest_row[0]))
                            if ts != last_processed_ts:
                                last_processed_ts = ts
                                bar_1s = {
                                    't': ts,
                                    'o': float(latest_row[1]),
                                    'h': float(latest_row[2]),
                                    'l': float(latest_row[3]),
                                    'c': float(latest_row[4]),
                                    'v': float(latest_row[5]) if len(latest_row) > 5 else 1.0
                                }
                                # Ingest 1S bar and update M1/M5 live aggregation
                                self.on_new_1s_bar(bar_1s)

                    await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"[PLAYWRIGHT STREAMER ERROR] {e}")

    def on_new_1s_bar(self, bar_1s: Dict[str, Any]):
        """Builds M1 and M5 candles dynamically from the live 1-second stream."""
        ts = bar_1s['t']
        price = bar_1s['c']

        # 1. Update 1S Rolling Buffer
        self.recent_1s_bars.append(bar_1s)
        if len(self.recent_1s_bars) > 120:
            self.recent_1s_bars.pop(0)

        # 2. Maintain Forming M1 Candle
        m1_boundary = (ts // 60) * 60
        if not self.forming_m1 or self.forming_m1['t'] != m1_boundary:
            if self.forming_m1:
                self.m1_candles.append(self.forming_m1)
                if len(self.m1_candles) > 500: self.m1_candles.pop(0)
            self.forming_m1 = {
                't': m1_boundary,
                'o': bar_1s['o'],
                'h': bar_1s['h'],
                'l': bar_1s['l'],
                'c': bar_1s['c'],
                'v': bar_1s['v']
            }
        else:
            self.forming_m1['h'] = max(self.forming_m1['h'], bar_1s['h'])
            self.forming_m1['l'] = min(self.forming_m1['l'], bar_1s['l'])
            self.forming_m1['c'] = bar_1s['c']
            self.forming_m1['v'] += bar_1s['v']

        # 3. Maintain Forming M5 Candle
        m5_boundary = (ts // 300) * 300
        if not self.forming_m5 or self.forming_m5['t'] != m5_boundary:
            if self.forming_m5:
                self.m5_candles.append(self.forming_m5)
                if len(self.m5_candles) > 500: self.m5_candles.pop(0)
            self.forming_m5 = {
                't': m5_boundary,
                'o': bar_1s['o'],
                'h': bar_1s['h'],
                'l': bar_1s['l'],
                'c': bar_1s['c'],
                'v': bar_1s['v']
            }
        else:
            self.forming_m5['h'] = max(self.forming_m5['h'], bar_1s['h'])
            self.forming_m5['l'] = min(self.forming_m5['l'], bar_1s['l'])
            self.forming_m5['c'] = bar_1s['c']
            self.forming_m5['v'] += bar_1s['v']

        # 4. Feed Tick to Multi-TF Coordinator
        elapsed_sec_in_m1 = ts - m1_boundary
        bid = price
        ask = round(price + 0.09, 2)

        self.coordinator.on_tick(
            bid=bid,
            ask=ask,
            m5_candles=self.m5_candles,
            m1_candle=self.forming_m1,
            current_sec=bar_1s,
            elapsed_sec_in_m1=elapsed_sec_in_m1,
            current_m5_ts=m5_boundary,
            preferred_track='A'
        )

    def load_historical_seeds(self, m5_df: pd.DataFrame, m1_df: pd.DataFrame, s1_df: Optional[pd.DataFrame] = None):
        """Pre-seeds the streamer with historical completed candles."""
        self.m5_candles = m5_df.to_dict('records')
        self.m1_candles = m1_df.to_dict('records')
        if s1_df is not None:
            self.recent_1s_bars = s1_df.tail(120).to_dict('records')
        logger.info(f"Seeded {len(self.m5_candles)} M5 candles, {len(self.m1_candles)} M1 candles, and {len(self.recent_1s_bars)} 1S bars.")
