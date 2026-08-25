"""Edge Labs — Main Entry Point
High-speed M5 Scalping Engine with Solid Nanotech Assembly Splash,
Bottom Cyberpunk HUD Telemetry Deck, and Sub-150ms Keep-Alive streaming.
"""
from __future__ import annotations
import sys, os, time, math, logging, warnings, random

# Force UTF-8 and suppress Chromium/D3D11 HDR warnings on Windows
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-logging --log-level=3 --disable-direct-composition --disable-gpu-rasterization"
os.environ["PYTHONWARNINGS"] = "ignore"

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    os.system('chcp 65001 > nul 2>&1')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Suppress TradeLocker internal DataFrame typing prints
tl_log = logging.getLogger('tradelocker')
tl_log.setLevel(logging.CRITICAL + 10)
tl_log.propagate = False
tl_api_log = logging.getLogger('tradelocker.tradelocker_api')
tl_api_log.setLevel(logging.CRITICAL + 10)
tl_api_log.propagate = False
logging.getLogger().setLevel(logging.WARNING)
warnings.filterwarnings('ignore')

# Set Windows App ID for taskbar icon
if sys.platform == 'win32':
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("edgelabs.scalping.mkiii.3.0")
    except Exception:
        pass

import numpy as np
import pandas as pd

# CRITICAL: QtWebEngineWidgets MUST be imported before QApplication is created.
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QSplashScreen, QProgressBar
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, pyqtSlot, QObject
from PyQt6.QtGui import QColor, QPainter, QFont, QIcon

from core.api_client     import EdgeLabsClient
from core.candle_builder import CandleBuilder
from core.analysis_engine import AnalysisEngine
from core.execution_engine import ExecutionEngine
from ui.chart_window     import MainChartWindow, BotSignals
import config


# ══════════════════════════════════════════════════════════════════════════════
# GUI SPLASH SCREEN — Silver Nanotech Sand-Grain Monolith Assembly
# ══════════════════════════════════════════════════════════════════════════════

# High-Density 9x9 solid matrix font for ultra-crisp ALL-CAPS "E D G E L A B S"
HD_FONT = {
    'E': [
        "#########",
        "#########",
        "###......",
        "###......",
        "########.",
        "###......",
        "###......",
        "#########",
        "#########",
    ],
    'D': [
        "########.",
        "#########.",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "#########.",
        "########.",
    ],
    'G': [
        ".########",
        "##########",
        "###....###",
        "###.......",
        "###...####",
        "###....###",
        "###....###",
        "##########",
        ".########.",
    ],
    'L': [
        "###......",
        "###......",
        "###......",
        "###......",
        "###......",
        "###......",
        "###......",
        "#########",
        "#########",
    ],
    'A': [
        "..#####..",
        ".#######.",
        "###...###",
        "###...###",
        "#########",
        "#########",
        "###...###",
        "###...###",
        "###...###",
    ],
    'B': [
        "########.",
        "#########.",
        "###....###",
        "#########.",
        "#########.",
        "###....###",
        "###....###",
        "#########.",
        "########.",
    ],
    'S': [
        ".########",
        "##########",
        "###....###",
        "###.......",
        ".########.",
        "......###.",
        "###....###",
        "##########",
        ".########.",
    ],
}

FLASK_HD = [
    ".....#######.....",
    "......#####......",
    "......#####......",
    ".....#######.....",
    "....#########....",
    "...###########...",
    "..#############..",
    ".###############.",
    "#################",
]

DARK_BG   = "#07090e"
SILVER_HI = "#ffffff"
SILVER_MD = "#e2e8f0"
SILVER_DK = "#94a3b8"
CYAN_GLOW = "#00d4ff"
EMERALD   = "#00e676"


class SplashScreen(QWidget):
    """Silver nanotech sand particle assembly splash screen with Erlenmeyer flask and floor reflection."""

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint |
                          Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(f"background:{DARK_BG};")
        self.resize(980, 520)
        self._center()

        self._frame        = 0
        self._phase        = 0  # 0: Spawning Sand, 1: Swarming Assembly, 2: Solidified + Reflected
        self._particles: list[dict] = []
        self._status_lines: list[tuple[str, str, str]] = []
        self._progress     = 0
        self._max_prog     = 1
        self._solid_alpha  = 0.0
        self._y_start      = 105

        self._font_title   = QFont("Segoe UI", 12, QFont.Weight.Bold)
        self._font_sub     = QFont("Consolas", 8, QFont.Weight.Bold)
        self._font_status  = QFont("Consolas", 8)

        self._build_nanotech_sand()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(20)

    def _center(self):
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width()  - self.width())  // 2,
            (screen.height() - self.height()) // 2
        )

    def _build_nanotech_sand(self):
        """Generates dense sub-pixel anchor coordinates for [Flask] + EDGELABS in all caps."""
        grid_x = 5
        grid_y = 7
        x_start = 55
        y_start = self._y_start

        targets = []

        # 1. High-Density Beaker / Flask in Silver Chrome with Emerald Accents
        for r_idx, row in enumerate(FLASK_HD):
            for c_idx, val in enumerate(row):
                if val == '#':
                    for sub_x in range(2):
                        for sub_y in range(2):
                            tx = x_start + (c_idx * grid_x) + (sub_x * 2)
                            ty = y_start + (r_idx * grid_y) + (sub_y * 3)
                            col = SILVER_HI if r_idx < 4 else SILVER_MD
                            targets.append((tx, ty, col))

        cur_x = x_start + (len(FLASK_HD[0]) + 3) * grid_x

        # 2. High-Density Joined ALL-CAPS "EDGELABS" Wordmark in Solid Metallic Silver
        word = "EDGELABS"
        for i, char in enumerate(word):
            matrix = HD_FONT.get(char, HD_FONT['E'])
            char_col = SILVER_HI if i < 4 else SILVER_MD  # All solid metallic silver
            for r_idx, row in enumerate(matrix):
                for c_idx, val in enumerate(row):
                    if val == '#':
                        for sub_x in range(2):
                            for sub_y in range(2):
                                tx = cur_x + (c_idx * grid_x) + (sub_x * 2)
                                ty = y_start + (r_idx * grid_y) + (sub_y * 3)
                                targets.append((tx, ty, char_col))
            cur_x += (len(matrix[0]) + 2) * grid_x

        # 3. Spawn Nanobots scattered on bottom floor like silver sand grains
        rng = random.Random(42)
        self._particles = []
        for tx, ty, col in targets:
            # Start scattered on bottom floor
            sx = rng.uniform(30, self.width() - 30)
            sy = rng.uniform(self.height() - 75, self.height() - 15)
            speed = rng.uniform(0.05, 0.12)
            wobble = rng.uniform(0, math.pi * 2)
            sand_shade = rng.choice([SILVER_HI, SILVER_MD, SILVER_DK, "#b0b8c4"])
            radius = rng.uniform(1.2, 2.4)
            self._particles.append({
                'x': sx, 'y': sy,
                'tx': tx, 'ty': ty,
                'vx': 0.0, 'vy': 0.0,
                'col': col,
                'sand_col': sand_shade,
                'speed': speed,
                'wobble': wobble,
                'r': radius,
            })

    def _tick(self):
        self._frame += 1

        if self._phase == 0 and self._frame > 4:
            self._phase = 1

        if self._phase == 1:
            all_assembled = True
            for p in self._particles:
                dx = p['tx'] - p['x']
                dy = p['ty'] - p['y']
                dist = math.sqrt(dx*dx + dy*dy)
                if dist > 1.0:
                    all_assembled = False
                    # Organic cybernetic upward streaming
                    p['wobble'] += 0.12
                    wobble_x = math.sin(p['wobble']) * 0.4
                    p['x'] += (dx * p['speed']) + wobble_x
                    p['y'] += (dy * p['speed'])
                else:
                    p['x'] = p['tx']
                    p['y'] = p['ty']

            if all_assembled:
                self._phase = 2
                self._frame = 0

        if self._phase == 2:
            if self._solid_alpha < 1.0:
                self._solid_alpha = min(1.0, self._solid_alpha + 0.04)

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(DARK_BG))

        # ── Ambient Studio Grid & Floor Line ──────────────────────────────────
        floor_y = self.height() - 85
        painter.setPen(QColor("#111827"))
        painter.drawLine(0, floor_y, self.width(), floor_y)

        # ── Upper Monolith Header Badge ───────────────────────────────────────
        painter.setFont(self._font_sub)
        painter.setPen(QColor("#00d4ff"))
        painter.drawText(55, 55, "\u25c8 QUANTITATIVE ORDERFLOW MICROSTRUCTURE CORE  \u00b7  MK IV")

        # ── Render Silver Sand Nanobots & Solid Fused Metallic Logo ───────────
        for p in self._particles:
            x, y, tx, ty = p['x'], p['y'], p['tx'], p['ty']
            dx = abs(x - tx)
            dy = abs(y - ty)
            dist = math.sqrt(dx*dx + dy*dy)

            if self._phase == 2:
                # Solid Fused Metallic Silver with specular shine
                col = QColor(p['col'])
                painter.setBrush(col)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(int(x), int(y), int(p['r']), int(p['r']))
            else:
                # Silver Nanotech Sand Grain in flight
                if dist < 8:
                    col = QColor(p['col'])
                else:
                    col = QColor(p['sand_col'])
                painter.setBrush(col)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(int(x), int(y), int(p['r']), int(p['r']))

        # ── Clean Ambient Floor Reflection ────────────────────────────────────
        if self._phase == 2 and self._solid_alpha > 0.1:
            refl_center_y = self._y_start + (len(FLASK_HD) * 7) + 25
            for p in self._particles[::3]:  # Sub-sample for soft ambient reflection
                tx, ty = p['tx'], p['ty']
                dy = ty - self._y_start
                ry = refl_center_y + dy * 0.45
                if ry < floor_y + 40:
                    alpha = int(40 * self._solid_alpha * (1.0 - (ry - refl_center_y)/50.0))
                    if alpha > 0:
                        c = QColor(p['col'])
                        c.setAlpha(alpha)
                        painter.setBrush(c)
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.drawEllipse(int(tx), int(ry), int(p['r'] * 1.5), int(p['r'] * 0.8))

        # ── Subtitle & Version Monolith ───────────────────────────────────────
        if self._phase >= 1:
            painter.setFont(self._font_sub)
            painter.setPen(QColor("#7e8b9f"))
            painter.drawText(55, 235,
                "XAUUSD SUB-SECOND SCALPER  \u00b7  TRIPLE-TRACK HEDGE  \u00b7  120MS KEEP-ALIVE STREAM  \u00b7  v4.0")

        # ── Live Status Feed with Sleek Neon Badges ───────────────────────────
        painter.setFont(self._font_status)
        y = 275
        for tag, text, color in self._status_lines:
            # Render Tag Pill
            painter.setPen(QColor(color))
            painter.drawText(55, y, f"[{tag}]")
            painter.setPen(QColor("#c4cdd5"))
            painter.drawText(175, y, text)
            y += 20

        # ── Modern Minimalist Progress Meter ──────────────────────────────────
        if self._max_prog > 1:
            pct  = max(0.0, min(1.0, self._progress / self._max_prog))
            bx, by, bw, bh = 55, self.height() - 48, self.width() - 110, 4
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#131a28"))
            painter.drawRoundedRect(bx, by, bw, bh, 2, 2)
            painter.setBrush(QColor(CYAN_GLOW))
            painter.drawRoundedRect(bx, by, int(bw * pct), bh, 2, 2)

            painter.setFont(self._font_status)
            painter.setPen(QColor("#667085"))
            painter.drawText(55, self.height() - 25,
                f"STREAMING M5 HISTORICAL REPOSITORY: {self._progress} / {self._max_prog} CANDLES ({int(pct*100)}%)")

        painter.end()

    def add_status(self, text: str, ok: bool = True):
        tag = "SYNCHRONIZED" if ok else "INITIALIZING"
        color = EMERALD if ok else "#ff3355"
        self._status_lines.append((tag, text, color))
        if len(self._status_lines) > 5:
            self._status_lines.pop(0)
        self.update()

    def set_progress(self, n: int, total: int):
        self._progress = n
        self._max_prog = total
        self.update()


# ══════════════════════════════════════════════════════════════════════════════
# Boot Worker
# ══════════════════════════════════════════════════════════════════════════════

class BootWorker(QThread):
    status      = pyqtSignal(str, bool)
    progress    = pyqtSignal(int, int)
    finished_ok = pyqtSignal(object, object, object, object)
    failed      = pyqtSignal(str)

    def run(self):
        try:
            self.status.emit("[*] Initializing High-Speed TradeLocker Keep-Alive Stream...", True)
            client = EdgeLabsClient()
            self.status.emit(
                f"[+] Connected to TradeLocker  |  XAUUSD ID={client.instrument_id} (Contract: {client.contract_size} oz)", True)

            self.status.emit("[*] Fetching initial live quote...", True)
            price = client.get_live_price()
            self.status.emit(
                f"[+] Live Quote  Bid: ${price['bid']:.2f}  "
                f"Ask: ${price['ask']:.2f}  Spread: ${price['spread']:.2f}", True)

            self.status.emit("[*] Streaming 24-hour M5 candle history...", True)
            hist_df = client.get_historical_candles(lookback_period='1D')
            if hist_df.empty or len(hist_df) < 50:
                hist_df = client.get_historical_candles(lookback_period='3D')

            self.status.emit(
                f"[+] {len(hist_df)} M5 candles loaded into RAM (24h repository)", True)

            total = max(len(hist_df), 1)
            for i in range(1, total + 1):
                self.progress.emit(i, total)

            forming = client.get_forming_candle()
            if forming:
                self.status.emit(
                    f"[+] Live forming candle synced (Open: ${forming.get('o',0):.2f})", True)
            else:
                self.status.emit("[+] Forming candle initialised from live tick feed", True)

            builder = CandleBuilder(max_buffer=config.CANDLE_BUFFER_SIZE)
            if not hist_df.empty:
                builder.seed_from_history(hist_df)
            if forming:
                builder.forming_candle = {
                    't': int(forming.get('t', CandleBuilder.get_m5_boundary(time.time()))),
                    'o': float(forming.get('o', price['bid'])),
                    'h': float(forming.get('h', price['bid'])),
                    'l': float(forming.get('l', price['bid'])),
                    'c': float(forming.get('c', price['bid'])),
                    'v': int(forming.get('v', 1)),
                }

            engine = AnalysisEngine()
            exec_engine = ExecutionEngine(client, demo_mode=True)
            self.status.emit("[+] 5-D Analysis & Microsecond Execution Engines Online", True)

            time.sleep(0.4)
            self.finished_ok.emit(client, builder, engine, exec_engine)

        except Exception as e:
            self.failed.emit(str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Bot Worker — High-Frequency Sub-150ms Streamer
# ══════════════════════════════════════════════════════════════════════════════

class BotWorker(QThread):
    def __init__(self, client: EdgeLabsClient, builder: CandleBuilder,
                 engine: AnalysisEngine, exec_engine: ExecutionEngine,
                 signals: BotSignals):
        super().__init__()
        self.client      = client
        self.builder     = builder
        self.engine      = engine
        self.exec_engine = exec_engine
        self.signals     = signals
        self._running    = True
        self._tick_n     = 0

        # Auto-commit full candle history to chart UI whenever an M5 candle closes
        self.builder.on_candle_close(lambda c: self.signals.history_ready.emit(self.builder.get_all_candles()))

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            t0 = time.time()
            try:
                price = self.client.get_live_price()
                bid    = price['bid']
                ask    = price['ask']
                spread = price['spread']

                # 1. Update Candle Builder & Emit Tick
                self.builder.on_tick(bid, ask)
                self.signals.tick_received.emit(price)

                # 2. Update Forming Candle
                forming = self.builder.get_forming_candle()
                if forming:
                    self.signals.forming_updated.emit(forming)

                # 3. Position Management (Live & Simulation)
                self.exec_engine.manage_open_positions(bid)
                outcomes = self.exec_engine.update_simulated_positions(bid)
                for out in outcomes:
                    self.signals.trade_outcome.emit(out)

                self._tick_n += 1
                # Periodic timeline sync every 300 ticks (~75s) to guarantee continuous chart rendering
                if self._tick_n % 300 == 0:
                    self.signals.history_ready.emit(self.builder.get_all_candles())
                if self._tick_n % 2 == 0:
                    completed = self.builder.get_completed_candles()
                    if completed:
                        instant_pvel = self.builder.get_instant_price_velocity(5.0)
                        instant_tvel = self.builder.get_instant_tick_velocity(5.0)
                        eff_pvel = max(self.builder.get_price_velocity(), abs(instant_pvel * 60.0))
                        eff_tvel = max(self.builder.get_tick_velocity(), instant_tvel * 60.0)

                        snap = self.engine.analyse(
                            completed_candles=completed,
                            forming_candle=forming,
                            tick_velocity=eff_tvel,
                            price_velocity=eff_pvel,
                            current_price=bid,
                            spread=spread,
                            recent_ticks=self.builder.get_recent_tick_flow(5),
                            orderflow_delta=self.builder.get_cumulative_tick_delta(10.0),
                        )
                        self.signals.snapshot_ready.emit(snap)

                        if self.exec_engine.has_active_trade:
                            # Forward active position to UI
                            active_sim = self.exec_engine.active_simulations[0]['setup']
                            self.signals.simulation_updated.emit(active_sim)
                        else:
                            c_time = int(forming['t'] // 1000) if forming else int(completed[-1]['t'] // 1000)
                            setup = self.exec_engine.calculate_trade_setup(snap, bid, candle_time=c_time)
                            self.signals.simulation_updated.emit(setup)

                            if setup and setup.get('ready_to_simulate', False):
                                self.exec_engine.register_simulation(setup)
                                if config.ENABLE_DEMO_EXECUTION:
                                    self.exec_engine.execute_setup(setup)

                        tf = int(completed[0]['t'] // 1000)
                        tt = int(completed[-1]['t'] // 1000) + 7200
                        self.signals.structure_updated.emit(
                            snap.structure.nearest_resistance,
                            snap.structure.nearest_support,
                            tf, tt)

            except Exception as e:
                self.signals.error_occurred.emit(str(e)[:80])
                time.sleep(2.5)  # Safe backoff on rate limit or network hitch
                continue

            elapsed = time.time() - t0
            # Calibrated 250ms pacing (~3.5-4 ticks/sec, 100% safe from Cloudflare Error 1015)
            sleep_s = max(0.10, (config.POLL_INTERVAL_MS / 1000.0) - elapsed)
            time.sleep(sleep_s)


# ══════════════════════════════════════════════════════════════════════════════
# App Controller
# ══════════════════════════════════════════════════════════════════════════════

class AppController(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app        = app
        self.splash     = SplashScreen()
        self.splash.show()
        app.processEvents()

        self.signals    = BotSignals()
        self.window     = None
        self.bot_worker = None

        self.boot = BootWorker()
        self.boot.status.connect(self._on_boot_status)
        self.boot.progress.connect(self._on_boot_progress)
        self.boot.finished_ok.connect(self._on_boot_done)
        self.boot.failed.connect(self._on_boot_failed)
        self.boot.start()

    def _on_boot_status(self, msg: str, ok: bool):
        self.splash.add_status(msg, ok)

    def _on_boot_progress(self, n: int, total: int):
        self.splash.set_progress(n, total)

    def _on_boot_done(self, client, builder, engine, exec_engine):
        self.window = MainChartWindow(self.signals)
        self.window.show()

        all_candles = builder.get_all_candles()
        completed   = [c for c in all_candles if c is not builder.forming_candle]
        if completed:
            self.signals.history_ready.emit(completed)

        QTimer.singleShot(600, self.splash.close)

        self.bot_worker = BotWorker(client, builder, engine, exec_engine, self.signals)
        self.bot_worker.start()

        self.app.aboutToQuit.connect(self._shutdown)

    def _on_boot_failed(self, err: str):
        self.splash.add_status(f"[!] FATAL: {err}", False)
        self.splash.add_status("    Check credentials or network connection.", False)

    def _shutdown(self):
        if self.bot_worker:
            self.bot_worker.stop()
            self.bot_worker.wait(2000)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    icon_path = os.path.join(os.path.dirname(__file__), "ui", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    app.setStyle("Fusion")
    app.setStyleSheet("""
        QWidget {
            background-color: #08080a;
            color: #e0e0f0;
            font-family: Consolas, monospace;
            font-size: 10px;
        }
        QScrollBar        { background:#0d0d12; }
        QScrollBar::handle{ background:#1e1e2c; border-radius:3px; }
    """)

    controller = AppController(app)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
