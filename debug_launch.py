"""Debug launcher — catches and logs every error."""
import sys, os, traceback

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash.log")

def log(msg):
    print(msg)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

# Clear old log
open(LOG, "w").close()

try:
    log("[1] Importing PyQt6...")
    from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel
    from PyQt6.QtCore import Qt, QTimer
    log("    OK")

    log("[2] Creating QApplication...")
    app = QApplication(sys.argv)
    log("    OK")

    log("[3] Creating a basic window...")
    win = QMainWindow()
    win.setWindowTitle("Edge Labs Debug")
    win.resize(800, 400)
    lbl = QLabel("If you see this, PyQt6 works fine.")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet("color:white; background:#0a0a0c; font-size:20px;")
    win.setCentralWidget(lbl)
    log("    OK")

    log("[4] Importing WebEngine...")
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    log("    OK")

    log("[5] Creating WebEngineView...")
    web = QWebEngineView()
    web.setHtml("<h1 style='color:cyan;background:#0a0a0c;padding:40px'>WebEngine OK</h1>")
    log("    OK")

    log("[6] Importing bot modules...")
    from core.api_client import EdgeLabsClient
    from core.candle_builder import CandleBuilder
    from core.analysis_engine import AnalysisEngine
    from ui.chart_window import MainChartWindow, BotSignals
    import config
    log("    OK")

    log("[7] Testing EdgeLabsClient...")
    client = EdgeLabsClient()
    log(f"    Connected. instrument_id={client.instrument_id}")

    log("[8] Getting price...")
    price = client.get_live_price()
    log(f"    bid={price['bid']:.2f}  ask={price['ask']:.2f}")

    log("[9] Getting history (1D)...")
    hist = client.get_historical_candles(lookback_period='1D')
    log(f"    {len(hist)} candles")

    log("[10] Building candles...")
    builder = CandleBuilder(max_buffer=config.CANDLE_BUFFER_SIZE)
    builder.seed_from_history(hist)
    log(f"    {len(builder.candles)} completed candles")

    log("[11] Creating BotSignals...")
    signals = BotSignals()
    log("    OK")

    log("[12] Creating MainChartWindow...")
    window = MainChartWindow(signals)
    log("    OK")

    log("[13] Showing window...")
    window.show()
    log("    OK - window should be visible now")

    log("[14] Loading chart history...")
    candles = builder.get_all_candles()
    QTimer.singleShot(1500, lambda: window.load_history(candles))
    log(f"    Scheduled {len(candles)} candles to load in 1.5s")

    log("[15] Starting event loop...")
    log("    If it crashes after this, the error is in the Qt event loop.")
    log("    Window should stay open. Close it manually to exit.")

    sys.exit(app.exec())

except Exception as e:
    log(f"\n!!! CRASH !!!")
    log(f"Error type: {type(e).__name__}")
    log(f"Error msg:  {e}")
    log(f"\nFull traceback:")
    log(traceback.format_exc())
    log(f"\nSaved to: {LOG}")
    input("Press Enter to exit...")
