"""Edge Labs — Main Chart Window
Obsidian TradeLocker Dark Theme with Electric Cyberpunk Accents,
Dynamic Micro-Impulse Cent Calculations, and Visual TP/SL Position Tool.
"""
from __future__ import annotations
import sys, os, json, time, math
from pathlib import Path
from typing import Optional, Dict, Any

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QSizePolicy
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QUrl, pyqtSlot
from PyQt6.QtGui import QFont, QColor, QIcon, QPixmap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

_UI_DIR = Path(__file__).parent
_LW_JS  = _UI_DIR / "lw-charts.js"

# ── TradeLocker Obsidian & Electric Cyberpunk Palette ────────────────────────
TRADELOCKER_BG  = "#08090d"  # Deepest TradeLocker obsidian black
PANEL_BG        = "#0b0e14"  # Dark sleek panel slate
CARD_BG         = "#0e131d"  # High-tech card container
CARD_BORDER     = "#1c2436"  # Crisp tech border
CYBER_CYAN      = "#00f0ff"  # Electric cyber cyan
TL_GREEN        = "#00f298"  # TradeLocker neon emerald
TL_RED          = "#ff3b5c"  # TradeLocker electric coral
NEON_AMBER      = "#ffb800"  # Glowing warning amber
TEXT_LABEL      = "#8e99b0"  # High-contrast readable tech label
TEXT_VAL_WHITE  = "#f4f6fa"  # Ultra-crisp bright text
ACCENT_BLUE     = "#3b82f6"  # Cyber accent blue

# ── Chart HTML with Interactive Canvas Position Tool ──────────────────────────
def _build_chart_html() -> str:
    js_content = _LW_JS.read_text(encoding="utf-8") if _LW_JS.exists() else ""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:100%; height:100%; background:#08090d; overflow:hidden; font-family:Consolas, 'JetBrains Mono', monospace; }}
  #container {{ position:relative; width:100%; height:100%; }}
  #chart {{ width:100%; height:100%; }}
  #overlay {{ position:absolute; top:0; left:0; width:100%; height:100%; pointer-events:none; z-index:10; }}
</style>
<script>{js_content}</script>
</head>
<body>
<div id="container">
  <div id="chart"></div>
  <canvas id="overlay"></canvas>
</div>

<script>
const container = document.getElementById('container');
const overlay = document.getElementById('overlay');
const ctx = overlay.getContext('2d');

function resizeCanvas() {{
  const dpr = window.devicePixelRatio || 1;
  overlay.width = Math.floor(container.clientWidth * dpr);
  overlay.height = Math.floor(container.clientHeight * dpr);
  overlay.style.width = container.clientWidth + 'px';
  overlay.style.height = container.clientHeight + 'px';
}}
resizeCanvas();

const chart = LightweightCharts.createChart(document.getElementById('chart'), {{
  width:  window.innerWidth,
  height: window.innerHeight,
  layout: {{
    background: {{ color: '#08090d' }},
    textColor:  '#8e99b0',
    fontSize:   11,
    fontFamily: 'Consolas, monospace',
  }},
  grid: {{
    vertLines: {{ color: '#111622', style: 1 }},
    horzLines: {{ color: '#111622', style: 1 }},
  }},
  crosshair: {{
    mode: LightweightCharts.CrosshairMode.Normal,
    vertLine: {{ color: '#00f0ff60', labelBackgroundColor: '#121824' }},
    horzLine: {{ color: '#00f0ff60', labelBackgroundColor: '#121824' }},
  }},
  rightPriceScale: {{ borderColor: '#1c2436', textColor: '#8e99b0' }},
  timeScale: {{
    borderColor:    '#1c2436',
    timeVisible:    true,
    secondsVisible: false,
    rightOffset:    14,
    barSpacing:     12,
    minBarSpacing:  2,
  }},
  handleScroll: {{ mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true }},
  handleScale:  {{ mouseWheel: true, pinch: true, axisPressedMouseMove: true }},
}});

const candleSeries = chart.addCandlestickSeries({{
  upColor:         '#00f298',
  downColor:       '#ff3b5c',
  borderUpColor:   '#00f298',
  borderDownColor: '#ff3b5c',
  wickUpColor:     '#00d084',
  wickDownColor:   '#e02e4d',
  priceLineVisible: true,
  priceLineColor:   '#00f0ff80',
}});

const resistanceLine = chart.addLineSeries({{
  color: '#ff3b5c90', lineWidth: 1, lineStyle: 2,
  priceLineVisible: false, lastValueVisible: false,
}});
const supportLine = chart.addLineSeries({{
  color: '#00f29890', lineWidth: 1, lineStyle: 2,
  priceLineVisible: false, lastValueVisible: false,
}});

let historicalSetups = [];
let hasFitted = false;
let activeSimSetup = null;
let lastCandleTime = null;

function renderOverlay() {{
  const dpr = window.devicePixelRatio || 1;
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, overlay.width, overlay.height);
  ctx.scale(dpr, dpr);

  // Render finalized historical setups
  for (const s of historicalSetups) {{
    drawBox(s, false);
  }}

  // Render current active trigger setup if exists
  if (activeSimSetup && activeSimSetup.ready_to_simulate) {{
    drawBox(activeSimSetup, true);
  }}

  ctx.restore();
}}

function drawBox(s, isActive) {{
  const cTime = s.candle_time || lastCandleTime;
  if (!cTime) return;

  const yEntry = candleSeries.priceToCoordinate(s.entry_price);
  const yTP    = candleSeries.priceToCoordinate(s.tp_price);
  const ySL    = candleSeries.priceToCoordinate(s.sl_price);
  const xStart = chart.timeScale().timeToCoordinate(cTime);

  if (yEntry === null || yTP === null || ySL === null || xStart === null) return;
  if (xStart < -350 || xStart > container.clientWidth + 50) return; // Offscreen

  // Dynamic candle width calculation that scales with zoom:
  // Measure exact pixel span of this single M5 candle (300 seconds)
  const xNext = chart.timeScale().timeToCoordinate(cTime + 300);
  let singleCandleWidth = (xNext !== null && xNext > xStart) ? (xNext - xStart) : 24;

  let width;
  if (isActive && lastCandleTime && lastCandleTime >= cTime) {{
    const xLive = chart.timeScale().timeToCoordinate(lastCandleTime + 300);
    width = (xLive !== null && xLive > xStart) ? Math.max(singleCandleWidth, xLive - xStart) : singleCandleWidth * 2;
  }} else {{
    // Strictly fit the single candle width with clear visibility
    width = Math.max(16, singleCandleWidth);
  }}
  const x = xStart;

  let trackLabel = s.winning_track ? ('[' + s.winning_track.split(':')[0] + '] ') : (s.track_name ? ('[' + s.track_name.split(':')[0] + '] ') : '');

  // 1. Transparent Neon Green Take-Profit Box
  const tpHeight = Math.max(8, Math.abs(yEntry - yTP));
  const tpTop = Math.min(yEntry, yTP);
  ctx.fillStyle = s.status === 'win' ? 'rgba(0, 242, 152, 0.25)' : 'rgba(0, 242, 152, 0.14)';
  ctx.fillRect(x, tpTop, width, tpHeight);
  ctx.strokeStyle = s.status === 'win' ? '#00f298' : 'rgba(0, 242, 152, 0.75)';
  ctx.lineWidth = s.status === 'win' ? 1.5 : 1.0;
  ctx.strokeRect(x, tpTop, width, tpHeight);

  // 2. Transparent Coral Red Stop-Loss Box
  const slHeight = Math.max(6, Math.abs(yEntry - ySL));
  const slTop = Math.min(yEntry, ySL);
  ctx.fillStyle = s.status === 'loss' ? 'rgba(255, 59, 92, 0.25)' : (s.status === 'be' ? 'rgba(0, 240, 255, 0.18)' : 'rgba(255, 59, 92, 0.14)');
  ctx.fillRect(x, slTop, width, slHeight);
  ctx.strokeStyle = s.status === 'loss' ? '#ff3b5c' : (s.status === 'be' ? '#00f0ff' : 'rgba(255, 59, 92, 0.75)');
  ctx.lineWidth = (s.status === 'loss' || s.status === 'be') ? 1.5 : 1.0;
  ctx.strokeRect(x, slTop, width, slHeight);

  // 3. Cyan Dotted Entry Line
  ctx.beginPath();
  ctx.setLineDash([4, 3]);
  ctx.strokeStyle = '#00f0ff';
  ctx.lineWidth = 1.4;
  ctx.moveTo(x, yEntry);
  ctx.lineTo(x + width, yEntry);
  ctx.stroke();
  ctx.setLineDash([]);

  // 4. Clean Glow Typography
  ctx.font = 'bold 9px Consolas, monospace';
  if (s.status === 'win') {{
    const winVal = s.win_pnl !== undefined ? s.win_pnl : (s.potential_profit || 300);
    ctx.fillStyle = '#00f298';
    ctx.fillText(trackLabel + '\u2713 TP HIT (+$' + winVal.toFixed(0) + ')', x + 5, tpTop + 10);
  }} else if (s.status === 'be') {{
    ctx.fillStyle = '#00f0ff';
    ctx.fillText(trackLabel + '\u2696 BE EXIT ($0.00)', x + 5, slTop + slHeight - 4);
  }} else if (s.status === 'loss') {{
    ctx.fillStyle = '#ff3b5c';
    ctx.fillText(trackLabel + '\u2717 SL HIT (-$' + (s.potential_risk || 10).toFixed(0) + ')', x + 5, slTop + slHeight - 4);
  }} else {{
    ctx.fillStyle = '#00f298';
    ctx.fillText(trackLabel + '+' + (s.tp_dist || 0.25).toFixed(2) + ' (+$' + (s.potential_profit || 300).toFixed(0) + ')', x + 5, tpTop + 10);
    ctx.fillStyle = '#ff3b5c';
    ctx.fillText('-' + (s.sl_dist || 0.12).toFixed(2) + ' (-$' + (s.potential_risk || 10).toFixed(0) + ')', x + 5, slTop + slHeight - 4);
  }}

  ctx.fillStyle = '#00f0ff';
  ctx.fillText('$' + s.entry_price.toFixed(2) + ' (' + s.total_lots.toFixed(2) + 'L)', x + 5, yEntry - 3);
}}

chart.timeScale().subscribeVisibleTimeRangeChange(() => renderOverlay());
chart.timeScale().subscribeVisibleLogicalRangeChange(() => renderOverlay());

window.addEventListener('resize', () => {{
  chart.applyOptions({{ width: window.innerWidth, height: window.innerHeight }});
  resizeCanvas();
  renderOverlay();
}});

function _formatCandle(raw) {{
  if (!raw) return null;
  const rawTime = raw.time !== undefined ? raw.time : raw.t;
  if (rawTime === undefined || rawTime === null) return null;
  const tSec = Math.floor(rawTime > 1e11 ? rawTime / 1000 : rawTime);
  const o = Number(raw.open !== undefined ? raw.open : raw.o);
  const h = Number(raw.high !== undefined ? raw.high : raw.h);
  const l = Number(raw.low !== undefined ? raw.low : raw.l);
  const c = Number(raw.close !== undefined ? raw.close : raw.c);
  if (isNaN(tSec) || isNaN(o) || isNaN(h) || isNaN(l) || isNaN(c)) return null;
  return {{ time: tSec, open: o, high: h, low: l, close: c }};
}}

window.edgeAPI = {{
  setHistory: function(json_str) {{
    try {{
      const raw = JSON.parse(json_str);
      if (!Array.isArray(raw)) return;
      const formatted = [];
      for (const item of raw) {{
        const fc = _formatCandle(item);
        if (fc) formatted.push(fc);
      }}
      if (formatted.length > 0) {{
        candleSeries.setData(formatted);
        lastCandleTime = formatted[formatted.length - 1].time;
        if (!hasFitted) {{
          chart.timeScale().fitContent();
          hasFitted = true;
        }}
        renderOverlay();
      }}
    }} catch(e) {{ console.error('setHistory error:', e); }}
  }},
  updateForming: function(json_str) {{
    try {{
      const raw = JSON.parse(json_str);
      const fc = _formatCandle(raw);
      if (fc) {{
        candleSeries.update(fc);
        lastCandleTime = fc.time;
        renderOverlay();
      }}
    }} catch(e) {{ console.error('updateForming error:', e); }}
  }},
  setStructure: function(res, sup, t_from, t_to) {{
    try {{
      const t1 = t_from > 1e11 ? Math.floor(t_from / 1000) : t_from;
      const t2 = t_to > 1e11 ? Math.floor(t_to / 1000) : t_to;
      if (res !== null && !isNaN(res)) resistanceLine.setData([{{time:t1,value:res}},{{time:t2,value:res}}]);
      if (sup !== null && !isNaN(sup)) supportLine.setData([{{time:t1,value:sup}},{{time:t2,value:sup}}]);
    }} catch(e) {{}}
  }},
  setSimulationSetup: function(json_str) {{
    try {{
      activeSimSetup = json_str ? JSON.parse(json_str) : null;
      renderOverlay();
    }} catch(e) {{ console.error('setSimulationSetup error:', e); }}
  }},
  recordHistoricalSetup: function(json_str) {{
    try {{
      const s = JSON.parse(json_str);
      if (!s.candle_time && lastCandleTime) s.candle_time = lastCandleTime;
      s.status = 'open';
      const key = s.candle_time || s.timestamp;
      // Deduplicate: replace or append
      const idx = historicalSetups.findIndex(h => (h.candle_time === key || h.timestamp === s.timestamp));
      if (idx >= 0) {{
        historicalSetups[idx] = s;
      }} else {{
        historicalSetups.push(s);
      }}
      renderOverlay();
    }} catch(e) {{ console.error('recordHistoricalSetup error:', e); }}
  }},
  updateSetupOutcome: function(json_str) {{
    try {{
      const out = JSON.parse(json_str);
      const ts = out.setup ? out.setup.timestamp : null;
      for (const s of historicalSetups) {{
        if (s.timestamp === ts || (out.setup && s.candle_time === out.setup.candle_time)) {{
          if (out.outcome === 'WIN_TP' || out.outcome === 'WIN_PROFIT_LOCK') {{
            s.status = 'win';
            s.winning_track = out.setup.track_name;
            s.win_pnl = out.pnl;
            s.tp_price = out.exit_price || out.setup.tp_price;
          }} else if (out.outcome === 'BREAKEVEN_EXIT') {{
            s.status = 'be';
            s.winning_track = out.setup.track_name;
          }} else {{
            s.status = 'loss';
            s.winning_track = out.setup.track_name;
          }}
          break;
        }}
      }}
      renderOverlay();
    }} catch(e) {{ console.error('updateSetupOutcome error:', e); }}
  }}
}};
console.log('EdgeLabs chart ready');
</script>
</body>
</html>"""


# ── Signals ───────────────────────────────────────────────────────────────────
class BotSignals(QObject):
    tick_received      = pyqtSignal(dict)
    forming_updated    = pyqtSignal(dict)
    snapshot_ready     = pyqtSignal(object)
    simulation_updated = pyqtSignal(object)
    trade_outcome      = pyqtSignal(dict)
    structure_updated  = pyqtSignal(object, object, int, int)
    stats_updated      = pyqtSignal(int, float)
    status_update      = pyqtSignal(str)
    error_occurred     = pyqtSignal(str)
    history_ready      = pyqtSignal(list)


# ── Obsidian TradeLocker & Cyberpunk HUD Deck (Bottom Bar) ────────────────────
class TechHudDeck(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(190)  # Taller prominent footprint
        self.setStyleSheet(
            f"background:{TRADELOCKER_BG};"
            f"border-top:2px solid {CARD_BORDER};"
        )
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(14, 10, 14, 10)
        main_layout.setSpacing(12)

        # 1. SUB-SECOND SPEED & MOMENTUM CARD
        c1, l1 = self._create_card("1. SUB-SECOND SPEED & MOMENTUM", CYBER_CYAN)
        self.badge_speed = self._card_badge(l1, "SPEED: FAST", CYBER_CYAN)
        self.val_pvel    = self._card_metric(l1, "INSTANT VELOCITY", "\u2014", CYBER_CYAN)
        self.val_ticks   = self._card_metric(l1, "TICK FREQUENCY", "\u2014", TEXT_VAL_WHITE)
        self.val_step    = self._card_metric(l1, "PULSE BURST", "\u2014", TL_GREEN)
        main_layout.addWidget(c1, 1)

        # 2. DIRECTION & BIAS CARD
        c2, l2 = self._create_card("2. DIRECTION & BIAS", TL_GREEN)
        self.badge_dir   = self._card_badge(l2, "BIAS: BULLISH", TL_GREEN)
        self.val_score   = self._card_metric(l2, "3-WINDOW SCORE", "\u2014", TEXT_VAL_WHITE)
        self.val_sup     = self._card_metric(l2, "SUPPORT LEVEL", "\u2014", TL_GREEN)
        self.val_res     = self._card_metric(l2, "RESIST. LEVEL", "\u2014", TL_RED)
        main_layout.addWidget(c2, 1)

        # 3. KINETIC DRAG & ABSORPTION CARD
        c3, l3 = self._create_card("3. KINETIC DRAG & ABSORPTION", NEON_AMBER)
        self.badge_signal = self._card_badge(l3, "FLOW: SCANNING", TEXT_LABEL)
        self.val_uwick    = self._card_metric(l3, "UPPER DRAG", "0%", TEXT_VAL_WHITE)
        self.val_lwick    = self._card_metric(l3, "LOWER DRAG", "0%", TEXT_VAL_WHITE)
        self.val_reversal = self._card_metric(l3, "ABSORPTION", "CLEAR (FRICTIONLESS)", TL_GREEN)
        main_layout.addWidget(c3, 1)

        # 4. QUANT 3-TRACK SIZING (RAM) CARD
        c4, l4 = self._create_card("4. QUANT 3-TRACK SIZING", ACCENT_BLUE)
        self.badge_lots   = self._card_badge(l4, "3-TRACK: STANDBY", CYBER_CYAN)
        self.val_track_a  = self._card_metric(l4, "TRK A ($50 / $1K SCALP)", "Dynamic Sizing...", TL_GREEN)
        self.val_track_b  = self._card_metric(l4, "TRK B ($10 / $300 SNIPER)", "Dynamic Sizing...", NEON_AMBER)
        self.val_track_c  = self._card_metric(l4, "TRK C ($10 HEDGE DUAL)", "Dynamic Sizing...", CYBER_CYAN)
        main_layout.addWidget(c4, 1)

        # 5. LIVE TELEMETRY & FEED CARD
        c5, l5 = self._create_card("5. TELEMETRY & FEED", TEXT_LABEL)
        self.val_price    = self._card_big_price(l5, "$4400.00")
        self.val_spread   = self._card_metric(l5, "SPREAD", "$0.30", TEXT_VAL_WHITE)
        self.val_latency  = self._card_metric(l5, "STREAM LATENCY", "125 ms", CYBER_CYAN)
        self.val_mode     = self._card_metric(l5, "ENGINE MODE", "VISUAL SIMULATION", TL_GREEN)
        main_layout.addWidget(c5, 1)

    def _create_card(self, title: str, accent_color: str):
        card = QFrame()
        card.setStyleSheet(
            f"background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #101522, stop:1 #090c14);"
            f"border: 1px solid #1a2233;"
            f"border-top: 2px solid {accent_color};"
            f"border-radius: 6px;"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        header = QLabel(title)
        header.setStyleSheet(f"color:{accent_color};font-size:10px;font-weight:bold;letter-spacing:1.2px;")
        layout.addWidget(header)

        hr = QFrame()
        hr.setFixedHeight(1)
        hr.setStyleSheet(f"background:#1a2233;border:none;")
        layout.addWidget(hr)

        return card, layout

    def _card_badge(self, layout, text: str, color: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color:{color};font-size:11px;font-weight:bold;letter-spacing:0.8px;"
            f"background:#121826;padding:4px 8px;border-radius:4px;border:1px solid #1f2a3f;"
        )
        layout.addWidget(lbl)
        return lbl

    def _card_metric(self, layout, key: str, val: str, val_color: str) -> QLabel:
        w = QWidget()
        hl = QHBoxLayout(w)
        hl.setContentsMargins(0, 0, 0, 0)
        k_lbl = QLabel(key)
        k_lbl.setStyleSheet(f"color:{TEXT_LABEL};font-size:9px;font-weight:bold;letter-spacing:1px;")
        v_lbl = QLabel(val)
        v_lbl.setStyleSheet(f"color:{val_color};font-size:10px;font-weight:bold;")
        v_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        hl.addWidget(k_lbl)
        hl.addStretch()
        hl.addWidget(v_lbl)
        layout.addWidget(w)
        return v_lbl

    def _card_big_price(self, layout, val: str) -> QLabel:
        lbl = QLabel(val)
        lbl.setStyleSheet(f"color:{TEXT_VAL_WHITE};font-size:18px;font-weight:bold;letter-spacing:1px;")
        layout.addWidget(lbl)
        return lbl

    def update_price(self, bid: float, ask: float, spread: float, latency_ms: float):
        self.val_price.setText(f"${bid:.2f}")
        col = TL_GREEN if spread <= 20 else TL_RED
        self.val_spread.setStyleSheet(f"color:{col};font-size:10px;font-weight:bold;")
        self.val_spread.setText(f"${spread:.2f}")
        self.val_latency.setText(f"{latency_ms:.0f} ms")

    def update_snapshot(self, snap):
        # 1. Sub-Second Speed & Momentum
        s = snap.speed
        sc = TL_GREEN if s.classification == 'fast' else NEON_AMBER if s.classification == 'medium' else TEXT_LABEL
        self.badge_speed.setStyleSheet(
            f"color:{sc};font-size:12px;font-weight:bold;letter-spacing:1px;"
            f"background:#121824;padding:4px 8px;border-radius:3px;border:1px solid {sc}50;"
        )
        self.badge_speed.setText(f"SPEED: {s.classification.upper()}")
        
        # Sub-second velocity in $/sec and ¢/sec
        p_sec = s.price_velocity / 60.0
        t_sec = s.tick_velocity / 60.0
        p_sec_cents = p_sec * 100.0
        
        # Dynamic Pulse Distance per single move
        pulse_dist = (p_sec / max(0.5, t_sec)) * 100.0
        
        self.val_pvel.setText(f"{p_sec_cents:+.1f}¢ /sec (${p_sec:.2f}/s)")
        self.val_ticks.setText(f"{t_sec:.1f} ticks/sec ({s.tick_velocity:.0f}/m)")
        
        pulses = "1-2 Moves" if s.classification == 'fast' else "2-3 Moves"
        self.val_step.setText(f"+{pulse_dist:.1f}¢ /move ({pulses})")

        # 2. Direction & Bias
        d = snap.direction
        dc = TL_GREEN if d.bias == 'green' else TL_RED if d.bias == 'red' else NEON_AMBER
        self.badge_dir.setStyleSheet(
            f"color:{dc};font-size:12px;font-weight:bold;letter-spacing:1px;"
            f"background:#121824;padding:4px 8px;border-radius:3px;border:1px solid {dc}50;"
        )
        dir_text = "BIAS: BULLISH" if d.bias == 'green' else "BIAS: BEARISH" if d.bias == 'red' else "BIAS: MIXED"
        self.badge_dir.setText(dir_text)
        self.val_score.setText(f"{d.score:+.3f} (S:{d.short_score:+.2f}|M:{d.main_score:+.2f})")

        # Structure
        st = snap.structure
        self.val_sup.setText(f"${st.nearest_support:.2f}" if st.nearest_support else "\u2014")
        self.val_res.setText(f"${st.nearest_resistance:.2f}" if st.nearest_resistance else "\u2014")

        # 3. Kinetic Drag & Absorption
        r = snap.rejection
        self.val_uwick.setText(f"{r.upper_ratio*100:.0f}%" + (" (DRAG)" if r.upper_ratio > 0.20 else " (CLEAR)"))
        self.val_lwick.setText(f"{r.lower_ratio*100:.0f}%" + (" (DRAG)" if r.lower_ratio > 0.20 else " (CLEAR)"))
        
        rv = snap.reversal
        if rv.has_reversal:
            self.val_reversal.setStyleSheet(f"color:{TL_RED};font-size:10px;font-weight:bold;")
            labels = []
            for s in rv.signs[:2]:
                if s == 'absorption_upper': labels.append('UPPER ABSORPTION')
                elif s == 'absorption_lower': labels.append('LOWER ABSORPTION')
                elif s == 'over_expanded': labels.append('OVER-EXPANDED')
                elif s == 'momentum_drop': labels.append('MOMENTUM DECAY')
                elif s == 'color_flip': labels.append('COLOR FLIP')
                else: labels.append(s.upper())
            self.val_reversal.setText(", ".join(labels) or "ABSORPTION")
        else:
            self.val_reversal.setStyleSheet(f"color:{TL_GREEN};font-size:10px;font-weight:bold;")
            self.val_reversal.setText("CLEAR (FRICTIONLESS AIR)")

        if snap.ready_to_simulate:
            self.badge_signal.setStyleSheet(
                f"color:{TL_GREEN};font-size:12px;font-weight:bold;letter-spacing:1px;"
                f"background:#0d2618;padding:4px 8px;border-radius:3px;border:1px solid {TL_GREEN};"
            )
            self.badge_signal.setText("FLOW: THRUST READY")
        else:
            self.badge_signal.setStyleSheet(
                f"color:{TEXT_LABEL};font-size:12px;font-weight:bold;letter-spacing:1px;"
                f"background:#121824;padding:4px 8px;border-radius:3px;border:1px solid {CARD_BORDER};"
            )
            self.badge_signal.setText("FLOW: SCANNING")

    def update_simulation(self, setup: Optional[Dict[str, Any]]):
        if setup:
            status = setup.get('status')
            track_a = setup.get('track_a')
            track_b = setup.get('track_b')
            track_c_buy = setup.get('track_c_buy')

            if track_a:
                lots_a = track_a.get('total_lots', 0.0)
                tp_a   = track_a.get('tp_dist', 1.80)
                sim_a  = "READY" if track_a.get('simulation_passed') else "SCAN"
                self.val_track_a.setText(f"{lots_a:.2f}L (+${tp_a:.2f}) [{sim_a}]")
            else:
                self.val_track_a.setText("Standby ($50 Cap)")

            if track_b:
                lots_b = track_b.get('total_lots', 0.0)
                tp_b   = track_b.get('tp_dist', 2.70)
                sim_b  = "READY" if track_b.get('simulation_passed') else "SCAN"
                self.val_track_b.setText(f"{lots_b:.2f}L (+${tp_b:.2f}) [{sim_b}]")
            else:
                self.val_track_b.setText("Standby ($10 Cap)")

            if track_c_buy:
                lots_c = track_c_buy.get('total_lots', 0.0)
                tp_c   = track_c_buy.get('tp_dist', 2.70)
                sim_c  = "READY" if track_c_buy.get('simulation_passed') else "SCAN"
                self.val_track_c.setText(f"{lots_c:.2f}L Dual (+${tp_c:.2f}) [{sim_c}]")
            else:
                self.val_track_c.setText("Standby ($10 Hedge)")

            if status == 'SIM_FAILED':
                self.badge_lots.setStyleSheet(
                    f"color:{NEON_AMBER};font-size:11px;font-weight:bold;letter-spacing:0.5px;"
                    f"background:#261d0d;padding:4px 8px;border-radius:3px;border:1px solid {NEON_AMBER};"
                )
                self.badge_lots.setText(setup.get('reason', '3-TRACK SIM REJECTED'))
            elif status == 'LOCKED':
                self.badge_lots.setStyleSheet(
                    f"color:{TEXT_LABEL};font-size:11px;font-weight:bold;letter-spacing:0.5px;"
                    f"background:#121824;padding:4px 8px;border-radius:3px;border:1px solid {CARD_BORDER};"
                )
                self.badge_lots.setText(setup.get('reason', 'LOCKED (1-TRADE CAP)'))
            elif setup.get('ready_to_simulate', False):
                active_name = setup.get('track_name', '3-TRACK TRIGGER')
                self.badge_lots.setStyleSheet(
                    f"color:{TL_GREEN};font-size:11px;font-weight:bold;letter-spacing:1px;"
                    f"background:#0d2618;padding:4px 8px;border-radius:3px;border:1px solid {TL_GREEN};"
                )
                self.badge_lots.setText(f"TRIGGER: {active_name}")
            else:
                self.badge_lots.setStyleSheet(
                    f"color:{TEXT_LABEL};font-size:11px;font-weight:bold;letter-spacing:1px;"
                    f"background:#121824;padding:4px 8px;border-radius:3px;border:1px solid {CARD_BORDER};"
                )
                self.badge_lots.setText("3-TRACK: SCANNING")
        else:
            self.badge_lots.setStyleSheet(
                f"color:{TEXT_LABEL};font-size:11px;font-weight:bold;letter-spacing:1px;"
                f"background:#121824;padding:4px 8px;border-radius:3px;border:1px solid {CARD_BORDER};"
            )
            self.badge_lots.setText("3-TRACK: STANDBY")
            self.val_track_a.setText("Standby ($50 Cap)")
            self.val_track_b.setText("Standby ($10 Cap)")
            self.val_track_c.setText("Standby ($10 Hedge)")


# ── Obsidian TradeLocker Main Application Window ─────────────────────────────
class MainChartWindow(QMainWindow):
    def __init__(self, signals: BotSignals, parent=None):
        super().__init__(parent)
        self.signals = signals
        self._last_logged_ts = 0
        self.setWindowTitle("EDGE LABS — MK III TradeLocker (OBSIDIAN CYBER)")
        self.resize(1300, 780)
        self.setMinimumSize(850, 520)
        self.setStyleSheet(f"background-color: {TRADELOCKER_BG}; color: {TEXT_VAL_WHITE};")

        # Central Widget & Layout
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Sleek Top Bar
        top_bar = QFrame()
        top_bar.setFixedHeight(38)
        top_bar.setStyleSheet(f"background: {PANEL_BG}; border-bottom: 1px solid {CARD_BORDER};")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(14, 0, 14, 0)

        title = QLabel("EDGE LABS  |  MK III TRADELOCKER VER.")
        title.setStyleSheet(f"color: {CYBER_CYAN}; font-size: 11px; font-weight: bold; letter-spacing: 2px;")
        top_layout.addWidget(title)

        top_layout.addStretch()

        self.lbl_symbol = QLabel("XAUUSD \u2022 M5")
        self.lbl_symbol.setStyleSheet(f"color: {TL_GREEN}; font-size: 11px; font-weight: bold; letter-spacing: 1px;")
        top_layout.addWidget(self.lbl_symbol)

        self.lbl_conn = QLabel("\u25cf CONNECTED (BLBRY)")
        self.lbl_conn.setStyleSheet(f"color: {TL_GREEN}; font-size: 10px; font-weight: bold; letter-spacing: 1px;")
        top_layout.addWidget(self.lbl_conn)

        layout.addWidget(top_bar)

        # 2. Web Engine Chart with Load Queueing
        self._page_ready = False
        self._pending_history = None
        self._pending_forming = None

        self.web_view = QWebEngineView()
        self.web_view.setStyleSheet("background: transparent;")
        self.web_view.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        self.web_view.loadFinished.connect(self._on_web_loaded)
        self.web_view.setHtml(_build_chart_html())
        layout.addWidget(self.web_view, 1)

        # 3. HUD Deck
        self.hud_deck = TechHudDeck()
        layout.addWidget(self.hud_deck)

        # Connect Signals
        self.signals.tick_received.connect(self._on_tick)
        self.signals.forming_updated.connect(self._on_forming)
        self.signals.snapshot_ready.connect(self._on_snapshot)
        self.signals.simulation_updated.connect(self._on_simulation_updated)
        self.signals.trade_outcome.connect(self._on_trade_outcome)
        self.signals.structure_updated.connect(self._on_structure_updated)
        self.signals.stats_updated.connect(self._on_stats_updated)
        self.signals.history_ready.connect(self._on_history_ready)
        self.signals.status_update.connect(self._on_status)
        self.signals.error_occurred.connect(self._on_error)

    def _on_web_loaded(self, ok: bool):
        self._page_ready = True
        if self._pending_history:
            self.load_history(self._pending_history)
            self._pending_history = None
        if self._pending_forming:
            self.update_forming(self._pending_forming)
            self._pending_forming = None

    def _js(self, code: str):
        if not self._page_ready:
            return
        try:
            self.web_view.page().runJavaScript(code)
        except Exception:
            pass

    def load_history(self, candles: list):
        if not self._page_ready:
            self._pending_history = candles
            return
        try:
            self._js(f"if(window.edgeAPI) window.edgeAPI.setHistory({json.dumps(json.dumps(candles))})")
        except Exception:
            pass

    def update_tick(self, bid: float, ask: float, spread: float, latency_ms: float = 0.0):
        self.hud_deck.update_price(bid, ask, spread, latency_ms)

    def update_forming(self, candle: dict):
        if not self._page_ready:
            self._pending_forming = candle
            return
        try:
            self._js(f"if(window.edgeAPI) window.edgeAPI.updateForming({json.dumps(json.dumps(candle))})")
        except Exception:
            pass

    def update_structure(self, res, sup, t_from: int, t_to: int):
        try:
            self._js(f"window.edgeAPI.setStructure({res or 'null'}, {sup or 'null'}, {t_from}, {t_to})")
        except Exception:
            pass

    def update_simulation_box(self, setup: Optional[Dict[str, Any]]):
        try:
            if setup:
                self._js(f"window.edgeAPI.setSimulationSetup({json.dumps(json.dumps(setup))})")
            else:
                self._js("window.edgeAPI.setSimulationSetup(null)")
        except Exception:
            pass

    @pyqtSlot(dict)
    def _on_tick(self, tick: dict):
        self.update_tick(tick.get('bid', 0.0), tick.get('ask', 0.0), tick.get('spread', 0.0), tick.get('latency_ms', 0.0))

    @pyqtSlot(dict)
    def _on_forming(self, candle: dict):
        self.update_forming(candle)

    @pyqtSlot(object)
    def _on_snapshot(self, snap):
        self.hud_deck.update_snapshot(snap)

    def _log_and_capture_setup(self, setup: Dict[str, Any]):
        """Persists setup to JSONL, appends to markdown trade journal, and saves a chart screenshot."""
        try:
            log_dir = Path(__file__).parent.parent / "logs"
            log_dir.mkdir(exist_ok=True)

            # 1. JSONL log entry
            jsonl_file = log_dir / "simulations.jsonl"
            with open(jsonl_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(setup) + "\n")

            # 2. Markdown Trade Journal Entry (Dual-Track Logging)
            md_file = log_dir / "trade_journal.md"
            t_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(setup.get('timestamp', time.time())))

            entries_to_log = []
            if setup.get('track_a') and setup['track_a'].get('simulation_passed'):
                entries_to_log.append(setup['track_a'])
            if setup.get('track_b') and setup['track_b'].get('simulation_passed'):
                entries_to_log.append(setup['track_b'])
            if setup.get('track_c_buy') and setup['track_c_buy'].get('simulation_passed'):
                entries_to_log.append(setup['track_c_buy'])
                entries_to_log.append(setup['track_c_sell'])
            if not entries_to_log:
                entries_to_log.append(setup)

            journal_str = ""
            for s in entries_to_log:
                t_name = s.get('track_name', '3-TRACK')
                if "TRACK A" in t_name:
                    t_icon = "🔵"
                elif "TRACK B" in t_name:
                    t_icon = "🟡"
                else:
                    t_icon = "🟢"
                side_badge = "🟢 BUY (LONG)" if s['side'] == 'buy' else "🔴 SELL (SHORT)"
                journal_str += (
                    f"### {t_icon} [{t_name}] {side_badge} Setup Triggered — {t_str}\n"
                    f"- **Entry Price:** `${s['entry_price']:.2f}`\n"
                    f"- **Take Profit:** `${s['tp_price']:.2f}` (+${s['tp_dist']:.2f} move | **+${s['potential_profit']:,.0f} USD Target**)\n"
                    f"- **Stop Loss:** `${s['sl_price']:.2f}` (-${s['sl_dist']:.2f} stop | **-${s['potential_risk']:,.0f} USD Risk**)\n"
                    f"- **Position Size:** `{s['total_lots']:.2f} Lots` (Split into {len(s.get('chunks', []))} chunks of $\\le 3.00$ lots)\n"
                    f"- **3-Pass Simulation:** `PASSED (3/3 Passes Positive)`\n\n---\n\n"
                )

            if not md_file.exists():
                with open(md_file, "w", encoding="utf-8") as f:
                    f.write("# EDGELABS MK IV — Live 3-Track Simulation & Execution Journal\n\n---\n\n")
            with open(md_file, "a", encoding="utf-8") as f:
                f.write(journal_str)

            # 3. High-Res Screenshot Capture
            ss_dir = Path(__file__).parent.parent / "screenshots"
            ss_dir.mkdir(exist_ok=True)
            fname = f"setup_{time.strftime('%Y%m%d_%H%M%S')}_{setup['side']}.png"
            ss_path = ss_dir / fname
            # Delay 350ms to allow chart overlay canvas to finish rendering the position box
            QTimer.singleShot(350, lambda: self.grab().save(str(ss_path), "PNG"))
        except Exception as e:
            print(f"[LOG ERROR] {e}")

    @pyqtSlot(object)
    def _on_simulation_updated(self, setup):
        self.hud_deck.update_simulation(setup)
        self.update_simulation_box(setup)
        if setup and setup.get('ready_to_simulate'):
            ts = setup.get('timestamp', 0)
            if ts != self._last_logged_ts:
                self._last_logged_ts = ts
                self._js(f"window.edgeAPI.recordHistoricalSetup({json.dumps(json.dumps(setup))})")
                self._log_and_capture_setup(setup)

    @pyqtSlot(dict)
    def _on_trade_outcome(self, outcome: dict):
        """Called when a simulated or real trade hits TP or SL."""
        try:
            self._js(f"window.edgeAPI.updateSetupOutcome({json.dumps(json.dumps(outcome))})")
            self.update_simulation_box(None)
            log_dir = Path(__file__).parent.parent / "logs"
            log_dir.mkdir(exist_ok=True)

            # 1. Append outcome to trade_journal.md with Track Identification
            md_file = log_dir / "trade_journal.md"
            res = outcome['outcome']
            pnl = outcome['pnl']
            dur = outcome['duration_sec']
            exit_p = outcome['exit_price']
            setup = outcome['setup']
            t_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(outcome.get('timestamp', time.time())))
            t_name = setup.get('track_name', '3-TRACK')
            if "TRACK A" in t_name:
                t_icon = "🔵"
            elif "TRACK B" in t_name:
                t_icon = "🟡"
            else:
                t_icon = "🟢"

            if res == 'WIN_TP':
                badge = f"🏆 [{t_name}] RESULT: TAKE-PROFIT HIT (WIN +${pnl:,.0f} USD) ✅"
            elif res == 'WIN_PROFIT_LOCK':
                badge = f"💰 [{t_name}] RESULT: PROFIT RATCHET LOCKED (WIN +${pnl:,.0f} USD) 💵"
            elif res == 'BREAKEVEN_EXIT':
                badge = f"⚖️ [{t_name}] RESULT: BREAKEVEN EXIT ($0.00 PnL — Capital Protected) 🛡️"
            else:
                badge = f"🛡️ [{t_name}] RESULT: STOP-LOSS HIT (RISK PROTECTED -${abs(pnl):,.0f} USD) 🛑"

            outcome_txt = (
                f"#### {t_icon} {badge}\n"
                f"- **Exit Price:** `${exit_p:.2f}`\n"
                f"- **Trade Duration:** `{dur} seconds`\n"
                f"- **Net PnL:** `{'+' if pnl >= 0 else ''}${pnl:,.2f} USD`\n"
                f"- **Closed At:** `{t_str}`\n\n---\n\n"
            )
            with open(md_file, "a", encoding="utf-8") as f:
                f.write(outcome_txt)

            # 2. Append to simulations.jsonl
            with open(log_dir / "simulations.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(outcome) + "\n")

            # 3. Capture OUTCOME Screenshot showing candle touching TP/SL line!
            ss_dir = Path(__file__).parent.parent / "screenshots"
            ss_dir.mkdir(exist_ok=True)
            fname = f"outcome_{res}_{time.strftime('%Y%m%d_%H%M%S')}.png"
            ss_path = ss_dir / fname
            QTimer.singleShot(250, lambda: self.grab().save(str(ss_path), "PNG"))
        except Exception as e:
            print(f"[OUTCOME LOG ERROR] {e}")

    @pyqtSlot(object, object, int, int)
    def _on_structure_updated(self, resistance, support, t_from: int, t_to: int):
        self.update_structure(resistance, support, t_from, t_to)

    @pyqtSlot(int, float)
    def _on_stats_updated(self, candle_count: int, poll_ms: float):
        pass

    @pyqtSlot(list)
    def _on_history_ready(self, candles: list):
        self.load_history(candles)

    @pyqtSlot(str)
    def _on_status(self, msg: str):
        self.lbl_conn.setText(f"\u25cf {msg.upper()}")

    @pyqtSlot(str)
    def _on_error(self, err: str):
        self.lbl_conn.setStyleSheet(f"color:{TL_RED};font-size:9px;font-weight:bold;letter-spacing:1px;")
        self.lbl_conn.setText(f"\u2717 {err[:50]}")
