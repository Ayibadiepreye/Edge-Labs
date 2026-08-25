"""Edge Labs — Minimal Launcher (run.py)
Stripped-down launcher: just the chart window + polling worker.
"""
import sys, os

# Fix encoding + suppress stderr noise that kills PowerShell
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# MUST suppress TradeLocker logging BEFORE importing anything that
# triggers TLAPI, otherwise its [ERROR] goes to stderr and PowerShell
# interprets it as a fatal error and kills the process.
import logging
logging.getLogger('tradelocker').setLevel(logging.CRITICAL)
logging.getLogger('tradelocker.tradelocker_api').setLevel(logging.CRITICAL)

import warnings
warnings.filterwarnings('ignore')

# CRITICAL: WebEngine must be imported BEFORE QApplication
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, QThread
import time, traceback, pandas as pd

from core.api_client import EdgeLabsClient
from core.candle_builder import CandleBuilder
from core.analysis_engine import AnalysisEngine
from ui.chart_window import MainChartWindow, BotSignals
import config

print("[1] Creating QApplication...")
app = QApplication(sys.argv)
app.setStyle("Fusion")
app.setStyleSheet("""
    QWidget { background-color: #0a0a0c; color: #ccccdf;
              font-family: Consolas, monospace; font-size: 10px; }
""")
print("    OK")

print("[2] Connecting to TradeLocker...")
try:
    client = EdgeLabsClient()
    print(f"    Connected. id={client.instrument_id}")
except Exception as e:
    print(f"    FAILED: {e}")
    traceback.print_exc()
    input("Press Enter to exit...")
    sys.exit(1)

print("[3] Getting price...")
try:
    price = client.get_live_price()
    print(f"    bid={price['bid']:.2f}  ask={price['ask']:.2f}")
except Exception as e:
    print(f"    FAILED: {e}")

print("[4] Loading candles...")
hist_df = pd.DataFrame()
for lb in ['1D', '3D', '7D']:
    hist_df = client.get_historical_candles(lookback_period=lb)
    if not hist_df.empty:
        print(f"    Got {len(hist_df)} candles ({lb})")
        break
    print(f"    {lb}: empty")
if hist_df.empty:
    print("    No candle data. Market is closed. Will show empty chart.")

print("[5] Building candle buffer...")
builder = CandleBuilder(max_buffer=config.CANDLE_BUFFER_SIZE)
if not hist_df.empty:
    builder.seed_from_history(hist_df)
print(f"    {len(builder.candles)} completed candles")

print("[6] Creating chart window...")
signals = BotSignals()
window = MainChartWindow(signals)
window.show()
print("    Window shown")

print("[7] Loading chart data (delayed 1.5s)...")
def load_chart():
    try:
        candles = builder.get_all_candles()
        if candles:
            window.load_history(candles)
            print("    Chart data loaded")
    except Exception as e:
        print(f"    Chart load error: {e}")

QTimer.singleShot(1500, load_chart)

print("[8] Starting price poll worker...")

class SimpleWorker(QThread):
    def __init__(self, cl, bl, en, sig, win):
        super().__init__()
        self.client, self.builder, self.engine = cl, bl, en
        self.signals, self.window = sig, win
        self._running = True
        self._tick_n = 0

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            try:
                price = self.client.get_live_price()
                self.builder.on_tick(price['bid'], price['ask'])
                self.signals.tick_received.emit(price)

                forming = self.builder.get_forming_candle()
                if forming:
                    self.window.update_forming(forming)

                self._tick_n += 1
                if self._tick_n % 3 == 0:
                    completed = self.builder.get_completed_candles()
                    if completed:
                        snap = self.engine.analyse(
                            completed, forming,
                            self.builder.get_tick_velocity(),
                            self.builder.get_price_velocity(),
                            price['bid'], price['spread'])
                        self.signals.snapshot_ready.emit(snap)
                        self.window.status_panel.update_stats(len(completed), 1500)
            except Exception as e:
                self.signals.error_occurred.emit(str(e)[:80])
                time.sleep(3.0)
                continue
            time.sleep(1.5)

engine = AnalysisEngine()
worker = SimpleWorker(client, builder, engine, signals, window)
worker.start()
app.aboutToQuit.connect(lambda: (worker.stop(), worker.wait(2000)))

print("[9] Bot running! Close the window to exit.")
print("    (If market is closed, chart may be empty until Monday)")
sys.exit(app.exec())
