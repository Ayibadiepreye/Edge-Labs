"""Edge Labs — Mobile PWA Control Center & Telemetry Web Server
Provides a zero-dependency, ultra-fast, mobile-responsive PWA web application
allowing full bot control (Live Toggle, Account Switches, Track Sizing, DD %, and TP Targets)
accessible securely via local network or Tailscale tunnel.
"""
import os
import json
import time
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Optional
import config
from core.multi_account_manager import MultiAccountManager

logger = logging.getLogger("system")

# Suppress TradeLocker typing warnings
logging.getLogger('tradelocker').setLevel(logging.CRITICAL + 10)
logging.getLogger('tradelocker.tradelocker_api').setLevel(logging.CRITICAL + 10)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="apple-mobile-web-app-title" content="EdgeLabs Control">
  <meta name="theme-color" content="#08090d">
  <title>Edge Labs — Mobile Control Center</title>
  <link rel="manifest" href="/manifest.json">
  <style>
    * { margin:0; padding:0; box-sizing:border-box; -webkit-tap-highlight-color: transparent; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background: #08090d;
      color: #f1f5f9;
      min-height: 100vh;
      padding: 12px;
      padding-bottom: 70px;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 10px;
      border-bottom: 1px solid #1e293b;
      margin-bottom: 12px;
    }
    .title {
      font-size: 16px;
      font-weight: 800;
      color: #00f0ff;
      letter-spacing: 1px;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .status-badge {
      font-size: 10px;
      font-weight: 700;
      padding: 3px 6px;
      border-radius: 10px;
      background: #064e3b;
      color: #34d399;
      border: 1px solid #059669;
    }
    .master-btn {
      width: 100%;
      padding: 12px;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 800;
      letter-spacing: 0.5px;
      cursor: pointer;
      border: none;
      margin-bottom: 14px;
      transition: transform 0.1s, opacity 0.2s;
    }
    .master-btn:active { transform: scale(0.98); }
    .live-active {
      background: linear-gradient(135deg, #059669, #10b981);
      color: #ffffff;
      box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3);
    }
    .live-inactive {
      background: linear-gradient(135deg, #334155, #475569);
      color: #cbd5e1;
    }
    .card {
      background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #10141f, stop:1 #090c14);
      border: 1px solid #1c2436;
      border-top: 2px solid #38bdf8;
      border-radius: 10px;
      padding: 12px;
      margin-bottom: 12px;
    }
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }
    .acc-name {
      font-size: 13px;
      font-weight: 700;
      color: #38bdf8;
    }
    .acc-toggle {
      padding: 4px 8px;
      border-radius: 4px;
      font-size: 10px;
      font-weight: 700;
      border: none;
      cursor: pointer;
    }
    .btn-armed { background: #065f46; color: #34d399; }
    .btn-disarmed { background: #7f1d1d; color: #f87171; }
    
    .metric-ribbon {
      display: flex;
      justify-content: space-between;
      background: #080b12;
      border: 1px solid #161d2d;
      border-radius: 6px;
      padding: 6px 8px;
      margin-bottom: 8px;
    }
    .ribbon-item { display: flex; flex-direction: column; }
    .metric-label { font-size: 8px; color: #64748b; font-weight: 600; text-transform: uppercase; }
    .metric-value { font-size: 11px; font-weight: 700; color: #f8fafc; }
    .pnl-pos { color: #34d399 !important; }
    .pnl-neg { color: #f87171 !important; }
    
    .dd-row {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 10px;
      font-size: 10px;
    }
    .dd-bar-container {
      flex: 1;
      background: #080b12;
      border: 1px solid #1e293b;
      border-radius: 3px;
      height: 6px;
      overflow: hidden;
    }
    .dd-bar {
      height: 100%;
      background: #22c55e;
      border-radius: 3px;
      transition: width 0.3s ease;
    }
    .dd-input {
      background: #121824;
      border: 1px solid #1e293b;
      color: #fff;
      padding: 2px 4px;
      border-radius: 4px;
      width: 52px;
      text-align: center;
      font-size: 10px;
      font-weight: 700;
    }
    
    .tracks-container {
      background: #0b0f17;
      border: 1px solid #161d2d;
      border-radius: 6px;
      padding: 6px;
    }
    .track-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 4px 0;
      border-top: 1px solid #141b29;
    }
    .track-row:first-child { border-top: none; }
    .track-title { font-size: 10px; font-weight: 700; display: flex; align-items: center; gap: 4px; }
    .inputs-group { display: flex; align-items: center; gap: 4px; font-size: 9px; color: #64748b; }
    .track-input {
      background: #121824;
      border: 1px solid #1e293b;
      color: #fff;
      padding: 2px 4px;
      border-radius: 3px;
      width: 48px;
      text-align: center;
      font-weight: 700;
      font-size: 10px;
    }
    
    .footer-bar {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      background: rgba(8, 9, 13, 0.95);
      backdrop-filter: blur(10px);
      border-top: 1px solid #1e293b;
      padding: 8px 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      z-index: 100;
    }
    .last-sync { font-size: 9px; color: #64748b; }
    .btn-refresh {
      background: #1e293b;
      border: 1px solid #334155;
      color: #00f0ff;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 10px;
      font-weight: 700;
      cursor: pointer;
    }
  </style>
</head>
<body>
  <div class="header">
    <div class="title">⚡ EDGE LABS <span style="font-size:10px;color:#64748b;font-weight:500;">MK IV</span></div>
    <div class="status-badge" id="botStatus">● LIVE STREAMING</div>
  </div>

  <button id="btnMasterLive" class="master-btn live-inactive" onclick="toggleMasterLive()">
    🔴 SIMULATION MODE ONLY
  </button>

  <div id="accountsContainer">
    <div style="text-align:center;color:#64748b;padding:30px 0;font-size:12px;">Loading Telemetry Stream...</div>
  </div>

  <div class="footer-bar">
    <div class="last-sync" id="lastSyncText">Syncing...</div>
    <button class="btn-refresh" onclick="fetchTelemetry()">⚡ REFRESH</button>
  </div>

  <script>
    let appState = null;

    async function fetchTelemetry() {
      try {
        const res = await fetch('/api/telemetry');
        const data = await res.json();
        appState = data;
        renderUI(data);
      } catch (err) {
        document.getElementById('botStatus').textContent = '⚠️ RECONNECTING';
        document.getElementById('botStatus').style.background = '#7f1d1d';
        document.getElementById('botStatus').style.color = '#f87171';
      }
    }

    function renderUI(data) {
      document.getElementById('botStatus').textContent = '● LIVE STREAMING';
      document.getElementById('botStatus').style.background = '#064e3b';
      document.getElementById('botStatus').style.color = '#34d399';
      document.getElementById('lastSyncText').textContent = 'Updated: ' + new Date().toLocaleTimeString();

      const btnMaster = document.getElementById('btnMasterLive');
      if (data.live_execution_enabled) {
        btnMaster.className = 'master-btn live-active';
        btnMaster.innerHTML = '🟢 LIVE EXECUTION ACTIVE';
      } else {
        btnMaster.className = 'master-btn live-inactive';
        btnMaster.innerHTML = '🔴 SIMULATION MODE ONLY';
      }

      const container = document.getElementById('accountsContainer');
      let html = '';

      for (const [accId, acc] of Object.entries(data.accounts)) {
        const pnlClass = acc.daily_pnl >= 0 ? 'pnl-pos' : 'pnl-neg';
        const isArmed = acc.is_active;
        const armClass = isArmed ? 'btn-armed' : 'btn-disarmed';
        const armText = isArmed ? '🟢 ARMED' : '🔴 DISARMED';

        const maxLossAllowed = (acc.starting_balance - acc.daily_loss_floor) || 1;
        const curLoss = Math.max(0, acc.starting_balance - Math.min(acc.balance, acc.equity));
        const ddUsedPct = Math.min(100, Math.round((curLoss / maxLossAllowed) * 100));

        html += `
          <div class="card">
            <div class="card-header">
              <div class="acc-name">${acc.account_name} <span style="font-size:10px;color:#64748b;">(${acc.server})</span></div>
              <button class="acc-toggle ${armClass}" onclick="toggleAccount('${accId}')">${armText}</button>
            </div>

            <div class="metric-ribbon">
              <div class="ribbon-item">
                <span class="metric-label">Bal</span>
                <span class="metric-value">$${Number(acc.balance).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})}</span>
              </div>
              <div class="ribbon-item">
                <span class="metric-label">Eq</span>
                <span class="metric-value">$${Number(acc.equity).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})}</span>
              </div>
              <div class="ribbon-item">
                <span class="metric-label">PnL</span>
                <span class="metric-value ${pnlClass}">$${acc.daily_pnl >= 0 ? '+' : ''}${Number(acc.daily_pnl).toFixed(2)}</span>
              </div>
              <div class="ribbon-item">
                <span class="metric-label">Floor</span>
                <span class="metric-value" style="color:#94a3b8;">$${Number(acc.daily_loss_floor).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})}</span>
              </div>
            </div>

            <div class="dd-row">
              <span style="color:${ddUsedPct >= 90 ? '#f87171' : '#34d399'};font-weight:700;">DD: ${ddUsedPct}%</span>
              <div class="dd-bar-container">
                <div class="dd-bar" style="width:${ddUsedPct}%;background:${ddUsedPct >= 90 ? '#ef4444' : (ddUsedPct >= 60 ? '#eab308' : '#22c55e')};"></div>
              </div>
              <span style="color:#94a3b8;">Max:</span>
              <input class="dd-input" type="number" step="0.1" min="0.5" max="10.0" value="${acc.daily_max_loss_pct}" onchange="updateDDPct('${accId}', this.value)">%
            </div>

            <div class="tracks-container">
              <div class="track-row">
                <span class="track-title" style="color:#38bdf8;">🔵 Trk A (Scalp)</span>
                <div class="inputs-group">
                  <span>L:</span><input class="track-input" type="number" step="0.05" min="0.01" value="${acc.lots_a}" onchange="updateTrackParam('${accId}', 'A', 'lots', this.value)">
                  <span>TP:</span><input class="track-input" type="number" step="25" min="10" value="${acc.target_a}" onchange="updateTrackParam('${accId}', 'A', 'target', this.value)">
                </div>
              </div>
              <div class="track-row">
                <span class="track-title" style="color:#facc15;">🟡 Trk B (Snipe)</span>
                <div class="inputs-group">
                  <span>L:</span><input class="track-input" type="number" step="0.05" min="0.01" value="${acc.lots_b}" onchange="updateTrackParam('${accId}', 'B', 'lots', this.value)">
                  <span>TP:</span><input class="track-input" type="number" step="25" min="10" value="${acc.target_b}" onchange="updateTrackParam('${accId}', 'B', 'target', this.value)">
                </div>
              </div>
              <div class="track-row">
                <span class="track-title" style="color:#34d399;">🟢 Trk C (Hedge)</span>
                <div class="inputs-group">
                  <span>L:</span><input class="track-input" type="number" step="0.05" min="0.01" value="${acc.lots_c}" onchange="updateTrackParam('${accId}', 'C', 'lots', this.value)">
                  <span>TP:</span><input class="track-input" type="number" step="25" min="10" value="${acc.target_c}" onchange="updateTrackParam('${accId}', 'C', 'target', this.value)">
                </div>
              </div>
            </div>
          </div>
        `;
      }
      container.innerHTML = html;
    }

    async function toggleMasterLive() {
      await fetch('/api/toggle_live', { method: 'POST' });
      fetchTelemetry();
    }

    async function toggleAccount(accId) {
      await fetch('/api/toggle_account', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: accId })
      });
      fetchTelemetry();
    }

    async function updateDDPct(accId, pct) {
      await fetch('/api/update_dd_pct', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: accId, dd_pct: parseFloat(pct) })
      });
      fetchTelemetry();
    }

    async function updateTrackParam(accId, track, param, val) {
      await fetch('/api/update_track', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: accId, track: track, [param]: parseFloat(val) })
      });
    }

    setInterval(fetchTelemetry, 3000);
    fetchTelemetry();

    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/service-worker.js').catch(()=>{});
    }
  </script>
</body>
</html>
"""

MANIFEST_JSON = json.dumps({
    "name": "Edge Labs Control Center",
    "short_name": "EdgeLabs",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#08090d",
    "theme_color": "#08090d",
    "icons": [
        {
            "src": "https://img.icons8.com/fluency/192/bot.png",
            "sizes": "192x192",
            "type": "image/png"
        },
        {
            "src": "https://img.icons8.com/fluency/512/bot.png",
            "sizes": "512x512",
            "type": "image/png"
        }
    ]
})

SERVICE_WORKER_JS = """
const CACHE_NAME = 'edgelabs-cache-v1';
self.addEventListener('install', (e) => { self.skipWaiting(); });
self.addEventListener('activate', (e) => { e.waitUntil(clients.claim()); });
self.addEventListener('fetch', (e) => {
  if (e.request.url.includes('/api/')) {
    return;
  }
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
"""


class ThreadingServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class RequestHandler(BaseHTTPRequestHandler):
    account_manager: Optional[MultiAccountManager] = None

    def log_message(self, format, *args):
        pass

    def _send_response(self, content_type: str, content: str, status: int = 200):
        data = content.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self._send_response('text/plain', '')

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self._send_response('text/html', HTML_TEMPLATE)
        elif self.path == '/manifest.json':
            self._send_response('application/json', MANIFEST_JSON)
        elif self.path == '/service-worker.js':
            self._send_response('application/javascript', SERVICE_WORKER_JS)
        elif self.path == '/api/telemetry':
            mgr = RequestHandler.account_manager
            acc_data = {}
            if mgr:
                for acc in mgr.get_accounts_list():
                    acc_id = acc.account_id
                    acc_data[acc_id] = {
                        "account_name": acc.account_name,
                        "server": acc.server,
                        "balance": acc.current_balance,
                        "equity": acc.equity,
                        "daily_pnl": acc.daily_pnl,
                        "daily_loss_floor": acc.daily_loss_floor,
                        "daily_max_loss_pct": acc.daily_max_loss_pct,
                        "is_active": acc.is_active,
                        "lots_a": acc.lots_a,
                        "target_a": acc.target_a,
                        "lots_b": acc.lots_b,
                        "target_b": acc.target_b,
                        "lots_c": acc.lots_c,
                        "target_c": acc.target_c,
                        "starting_balance": acc.starting_balance,
                    }
            payload = {
                "live_execution_enabled": config.LIVE_EXECUTION_ENABLED,
                "accounts": acc_data,
                "timestamp": time.time()
            }
            self._send_response('application/json', json.dumps(payload))
        else:
            self._send_response('text/plain', 'Not Found', 404)

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else '{}'
        try:
            data = json.loads(body)
        except Exception:
            data = {}

        mgr = RequestHandler.account_manager

        if self.path == '/api/toggle_live':
            config.LIVE_EXECUTION_ENABLED = not config.LIVE_EXECUTION_ENABLED
            logger.info(f"[WEB REMOTE] Live Execution toggled: {config.LIVE_EXECUTION_ENABLED}")
            self._send_response('application/json', json.dumps({"status": "ok", "live_execution_enabled": config.LIVE_EXECUTION_ENABLED}))

        elif self.path == '/api/toggle_account':
            acc_id = data.get('account_id')
            acc = mgr.get_account(acc_id) if mgr else None
            if acc:
                acc.is_active = not acc.is_active
                logger.info(f"[WEB REMOTE] Account {acc.account_name} toggled: {acc.is_active}")
                self._send_response('application/json', json.dumps({"status": "ok", "is_active": acc.is_active}))
            else:
                self._send_response('application/json', json.dumps({"status": "error"}), 400)

        elif self.path == '/api/update_dd_pct':
            acc_id = data.get('account_id')
            pct = float(data.get('dd_pct', 3.8))
            acc = mgr.get_account(acc_id) if mgr else None
            if acc and pct > 0:
                acc.daily_max_loss_pct = pct
                start_b = acc.starting_balance if acc.starting_balance > 0 else acc.current_balance
                acc.daily_loss_floor = round(start_b * (1.0 - (pct / 100.0)), 2)
                logger.info(f"[WEB REMOTE] Updated {acc.account_name} DD Limit to {pct}% (Floor: ${acc.daily_loss_floor:,.2f})")
                self._send_response('application/json', json.dumps({"status": "ok"}))
            else:
                self._send_response('application/json', json.dumps({"status": "error"}), 400)

        elif self.path == '/api/update_track':
            acc_id = data.get('account_id')
            track = data.get('track')
            lots = float(data.get('lots', 0.0))
            tgt = float(data.get('target', 0.0))
            acc = mgr.get_account(acc_id) if mgr else None
            if acc:
                if lots > 0:
                    if track == 'A': acc.lots_a = lots
                    elif track == 'B': acc.lots_b = lots
                    elif track == 'C': acc.lots_c = lots
                if tgt > 0:
                    if track == 'A': acc.target_a = tgt
                    elif track == 'B': acc.target_b = tgt
                    elif track == 'C': acc.target_c = tgt
                self._send_response('application/json', json.dumps({"status": "ok"}))
            else:
                self._send_response('application/json', json.dumps({"status": "error"}), 400)
        else:
            self._send_response('text/plain', 'Not Found', 404)


class MobileWebServer:
    """Zero-dependency background web server for Tailscale & mobile PWA control."""

    def __init__(self, account_manager: MultiAccountManager, port: int = config.WEB_SERVER_PORT):
        self.account_manager = account_manager
        self.port = port
        RequestHandler.account_manager = account_manager
        self.server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        try:
            self.server = ThreadingServer(('0.0.0.0', self.port), RequestHandler)
            self._thread = threading.Thread(target=self.server.serve_forever, name="MobileWebServerThread", daemon=True)
            self._thread.start()
            logger.info(f"📱 Mobile PWA Control Center Online at http://0.0.0.0:{self.port}")
        except Exception as e:
            logger.warning(f"Could not start Mobile Web Server on port {self.port}: {e}")

    def stop(self):
        if self.server:
            self.server.shutdown()
