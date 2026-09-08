"""Edge Labs — Ultra-Compact Multi-Account Live Control Center
High-density, sleek cyber layout with real-time balance metrics, editable Daily Drawdown %,
and compact inline track toggles and risk editors.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QGridLayout, QCheckBox, QDoubleSpinBox, QProgressBar,
    QGroupBox
)
from PyQt6.QtCore import Qt
from core.multi_account_manager import MultiAccountManager, AccountConfig
import config


class AccountCardWidget(QFrame):
    """Ultra-compact, sleek card displaying account telemetry, editable DD %, and inline track controls."""

    def __init__(self, acc: AccountConfig, parent=None):
        super().__init__(parent)
        self.acc = acc
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            AccountCardWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #10141f, stop:1 #090c14);
                border: 1px solid #1a2233;
                border-top: 2px solid #38bdf8;
                border-radius: 6px;
                padding: 6px;
            }
        """)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # 1. Header Bar: Account Title & Live Arm Button
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self.lbl_name = QLabel(f"<b>{self.acc.account_name}</b> <span style='color:#64748b;font-size:10px;'>({self.acc.server})</span>")
        self.lbl_name.setStyleSheet("color: #38bdf8; font-size: 12px; letter-spacing: 0.5px;")
        
        self.btn_toggle = QPushButton("🟢 ARMED" if self.acc.is_active else "🔴 DISARMED")
        self.btn_toggle.setFixedSize(85, 22)
        self.btn_toggle.setStyleSheet(
            "background-color: #065f46; color: #34d399; font-weight: bold; border-radius: 3px; font-size: 10px;"
            if self.acc.is_active else
            "background-color: #7f1d1d; color: #f87171; font-weight: bold; border-radius: 3px; font-size: 10px;"
        )
        self.btn_toggle.clicked.connect(self._on_toggle_active)
        
        header.addWidget(self.lbl_name)
        header.addStretch()
        header.addWidget(self.btn_toggle)
        layout.addLayout(header)

        # 2. Compact 4-Column Metrics Ribbon
        ribbon = QFrame()
        ribbon.setStyleSheet("background: #080b12; border: 1px solid #161d2d; border-radius: 4px; padding: 4px;")
        r_layout = QHBoxLayout(ribbon)
        r_layout.setContentsMargins(6, 4, 6, 4)
        r_layout.setSpacing(8)

        self.lbl_bal = QLabel(f"Bal: <b style='color:#fff;'>${self.acc.current_balance:,.2f}</b>")
        self.lbl_eq = QLabel(f"Eq: <b style='color:#fff;'>${self.acc.equity:,.2f}</b>")
        self.lbl_pnl = QLabel(f"PnL: <b>${self.acc.daily_pnl:+,.2f}</b>")
        self.lbl_floor = QLabel(f"Floor: <b style='color:#94a3b8;'>${self.acc.daily_loss_floor:,.2f}</b>")
        
        self.lbl_bal.setStyleSheet("color: #94a3b8; font-size: 11px;")
        self.lbl_eq.setStyleSheet("color: #94a3b8; font-size: 11px;")
        self.lbl_pnl.setStyleSheet("color: #34d399; font-size: 11px;" if self.acc.daily_pnl >= 0 else "color: #f87171; font-size: 11px;")
        self.lbl_floor.setStyleSheet("color: #94a3b8; font-size: 11px;")

        r_layout.addWidget(self.lbl_bal)
        r_layout.addWidget(self.lbl_eq)
        r_layout.addWidget(self.lbl_pnl)
        r_layout.addWidget(self.lbl_floor)
        layout.addWidget(ribbon)

        # 3. Compact Drawdown Bar & Editable DD Limit %
        dd_row = QHBoxLayout()
        dd_row.setContentsMargins(0, 0, 0, 0)
        dd_row.setSpacing(6)

        self.lbl_dd_status = QLabel("DD: 0% Used")
        self.lbl_dd_status.setStyleSheet("color: #34d399; font-size: 10px; font-weight: bold;")
        
        self.bar_dd = QProgressBar()
        self.bar_dd.setFixedHeight(6)
        self.bar_dd.setRange(0, 100)
        self.bar_dd.setValue(0)
        self.bar_dd.setStyleSheet("""
            QProgressBar {
                border: 1px solid #1e293b;
                border-radius: 3px;
                background-color: #080b12;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #22c55e;
                border-radius: 3px;
            }
        """)

        lbl_limit = QLabel("Max DD %:")
        lbl_limit.setStyleSheet("color: #94a3b8; font-size: 10px;")

        self.spin_dd_pct = QDoubleSpinBox()
        self.spin_dd_pct.setRange(0.5, 10.0)
        self.spin_dd_pct.setSingleStep(0.1)
        self.spin_dd_pct.setValue(self.acc.daily_max_loss_pct)
        self.spin_dd_pct.setSuffix("%")
        self.spin_dd_pct.setFixedSize(65, 20)
        self.spin_dd_pct.setStyleSheet("background: #121824; color: #fff; font-size: 10px; border: 1px solid #1e293b; border-radius: 3px;")
        self.spin_dd_pct.valueChanged.connect(self._on_dd_pct_changed)

        dd_row.addWidget(self.lbl_dd_status)
        dd_row.addWidget(self.bar_dd, 1)
        dd_row.addWidget(lbl_limit)
        dd_row.addWidget(self.spin_dd_pct)
        layout.addLayout(dd_row)

        # 4. Sleek Compact Track Controls
        t_box = QFrame()
        t_box.setStyleSheet("background: #0b0f17; border: 1px solid #161d2d; border-radius: 4px; padding: 4px;")
        t_layout = QVBoxLayout(t_box)
        t_layout.setContentsMargins(4, 4, 4, 4)
        t_layout.setSpacing(3)

        # Track A
        self.chk_a, self.spin_lots_a, self.spin_tgt_a = self._create_track_row(
            t_layout, "🔵 Trk A (Scalp)", "#38bdf8", self.acc.track_a_enabled, self.acc.lots_a, self.acc.target_a,
            lambda v: setattr(self.acc, 'track_a_enabled', v),
            lambda v: setattr(self.acc, 'lots_a', v),
            lambda v: setattr(self.acc, 'target_a', v),
        )

        # Track B
        self.chk_b, self.spin_lots_b, self.spin_tgt_b = self._create_track_row(
            t_layout, "🟡 Trk B (Snipe)", "#facc15", self.acc.track_b_enabled, self.acc.lots_b, self.acc.target_b,
            lambda v: setattr(self.acc, 'track_b_enabled', v),
            lambda v: setattr(self.acc, 'lots_b', v),
            lambda v: setattr(self.acc, 'target_b', v),
        )

        # Track C
        self.chk_c, self.spin_lots_c, self.spin_tgt_c = self._create_track_row(
            t_layout, "🟢 Trk C (Hedge)", "#34d399", self.acc.track_c_enabled, self.acc.lots_c, self.acc.target_c,
            lambda v: setattr(self.acc, 'track_c_enabled', v),
            lambda v: setattr(self.acc, 'lots_c', v),
            lambda v: setattr(self.acc, 'target_c', v),
        )

        layout.addWidget(t_box)

    def _create_track_row(self, parent_layout, label: str, color: str, enabled: bool, lots: float, target: float, on_toggle, on_lots, on_tgt):
        row = QHBoxLayout()
        row.setContentsMargins(2, 1, 2, 1)
        row.setSpacing(6)

        chk = QCheckBox(label)
        chk.setChecked(enabled)
        chk.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 10px;")
        chk.toggled.connect(on_toggle)

        lbl_l = QLabel("Lots:")
        lbl_l.setStyleSheet("color:#64748b; font-size:9px;")
        spin_l = QDoubleSpinBox()
        spin_l.setRange(0.01, 50.0)
        spin_l.setSingleStep(0.05)
        spin_l.setValue(lots)
        spin_l.setFixedSize(58, 18)
        spin_l.setStyleSheet("background: #121824; color: #fff; font-size: 10px; border: 1px solid #1e293b; border-radius: 2px;")
        spin_l.valueChanged.connect(on_lots)

        lbl_t = QLabel("TP:")
        lbl_t.setStyleSheet("color:#64748b; font-size:9px;")
        spin_t = QDoubleSpinBox()
        spin_t.setRange(10.0, 5000.0)
        spin_t.setSingleStep(25.0)
        spin_t.setPrefix("$")
        spin_t.setValue(target)
        spin_t.setFixedSize(65, 18)
        spin_t.setStyleSheet("background: #121824; color: #fff; font-size: 10px; border: 1px solid #1e293b; border-radius: 2px;")
        spin_t.valueChanged.connect(on_tgt)

        row.addWidget(chk)
        row.addStretch()
        row.addWidget(lbl_l)
        row.addWidget(spin_l)
        row.addWidget(lbl_t)
        row.addWidget(spin_t)
        parent_layout.addLayout(row)
        return chk, spin_l, spin_t

    def _on_toggle_active(self):
        self.acc.is_active = not self.acc.is_active
        if self.acc.is_active:
            self.btn_toggle.setText("🟢 ARMED")
            self.btn_toggle.setStyleSheet("background-color: #065f46; color: #34d399; font-weight: bold; border-radius: 3px; font-size: 10px;")
        else:
            self.btn_toggle.setText("🔴 DISARMED")
            self.btn_toggle.setStyleSheet("background-color: #7f1d1d; color: #f87171; font-weight: bold; border-radius: 3px; font-size: 10px;")

    def _on_dd_pct_changed(self, val: float):
        self.acc.daily_max_loss_pct = val
        start_b = self.acc.starting_balance if self.acc.starting_balance > 0 else self.acc.current_balance
        self.acc.daily_loss_floor = round(start_b * (1.0 - (val / 100.0)), 2)
        self.lbl_floor.setText(f"Floor: <b style='color:#94a3b8;'>${self.acc.daily_loss_floor:,.2f}</b>")

    def update_telemetry_ui(self, data: dict):
        """Updates labels and drawdown bar from background telemetry poll."""
        bal = data.get("balance", self.acc.current_balance)
        eq = data.get("equity", self.acc.equity)
        pnl = data.get("daily_pnl", self.acc.daily_pnl)
        floor = data.get("daily_loss_floor", self.acc.daily_loss_floor)
        tripped = data.get("circuit_breaker_tripped", False)
        
        self.lbl_bal.setText(f"Bal: <b style='color:#fff;'>${bal:,.2f}</b>")
        self.lbl_eq.setText(f"Eq: <b style='color:#fff;'>${eq:,.2f}</b>")
        self.lbl_pnl.setText(f"PnL: <b>${pnl:+,.2f}</b>")
        self.lbl_pnl.setStyleSheet("color: #34d399; font-size: 11px;" if pnl >= 0 else "color: #f87171; font-size: 11px;")
        self.lbl_floor.setText(f"Floor: <b style='color:#94a3b8;'>${floor:,.2f}</b>")

        start = self.acc.starting_balance if self.acc.starting_balance > 0 else bal
        max_loss_allowed = start - floor
        if max_loss_allowed > 0:
            current_loss = max(0.0, start - min(bal, eq))
            used_pct = min(100, int((current_loss / max_loss_allowed) * 100))
            self.bar_dd.setValue(used_pct)
            
            if tripped or used_pct >= 95:
                self.lbl_dd_status.setText(f"🚨 TRIPPED ({used_pct}%)")
                self.lbl_dd_status.setStyleSheet("color: #f87171; font-weight: bold; font-size: 10px;")
                self.bar_dd.setStyleSheet("QProgressBar::chunk { background-color: #ef4444; }")
                self.btn_toggle.setText("🚨 TRIPPED")
                self.btn_toggle.setStyleSheet("background-color: #7f1d1d; color: #f87171; font-weight: bold; font-size: 10px;")
            elif used_pct >= 60:
                self.lbl_dd_status.setText(f"⚠️ CAUTION ({used_pct}%)")
                self.lbl_dd_status.setStyleSheet("color: #facc15; font-size: 10px;")
                self.bar_dd.setStyleSheet("QProgressBar::chunk { background-color: #eab308; }")
            else:
                self.lbl_dd_status.setText(f"🟢 SAFE ({used_pct}%)")
                self.lbl_dd_status.setStyleSheet("color: #34d399; font-size: 10px;")
                self.bar_dd.setStyleSheet("QProgressBar::chunk { background-color: #22c55e; }")


class DashboardTab(QWidget):
    """Main Dashboard View containing all account cards and live risk controls."""

    def __init__(self, account_manager: MultiAccountManager, parent=None):
        super().__init__(parent)
        self.mgr = account_manager
        self.cards: dict[str, AccountCardWidget] = {}
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(8)

        # Top Control Banner
        top_bar = QHBoxLayout()
        title = QLabel("<h2>🛡️ Multi-Account Control Center</h2>")
        title.setStyleSheet("color: #f8fafc; font-size: 14px;")
        
        self.btn_live_mode = QPushButton("🟢 LIVE EXECUTION ENABLED" if config.LIVE_EXECUTION_ENABLED else "🔴 SIMULATION MODE ONLY")
        self.btn_live_mode.setStyleSheet(
            "background-color: #065f46; color: #34d399; font-weight: bold; font-size: 11px; padding: 6px 14px; border-radius: 4px;"
            if config.LIVE_EXECUTION_ENABLED else
            "background-color: #334155; color: #cbd5e1; font-weight: bold; font-size: 11px; padding: 6px 14px; border-radius: 4px;"
        )
        self.btn_live_mode.clicked.connect(self._toggle_live_execution)

        top_bar.addWidget(title)
        top_bar.addStretch()
        top_bar.addWidget(self.btn_live_mode)
        main_layout.addLayout(top_bar)

        # Scrollable Cards Grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        cards_container = QWidget()
        self.cards_layout = QGridLayout(cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)

        col = 0
        row = 0
        for acc in self.mgr.get_accounts_list():
            acc_id = acc.account_id
            card = AccountCardWidget(acc)
            self.cards[acc_id] = card
            self.cards_layout.addWidget(card, row, col)
            col += 1
            if col >= 2:
                col = 0
                row += 1

        scroll.setWidget(cards_container)
        main_layout.addWidget(scroll)

    def _toggle_live_execution(self):
        config.LIVE_EXECUTION_ENABLED = not config.LIVE_EXECUTION_ENABLED
        if config.LIVE_EXECUTION_ENABLED:
            self.btn_live_mode.setText("🟢 LIVE EXECUTION ENABLED")
            self.btn_live_mode.setStyleSheet("background-color: #065f46; color: #34d399; font-weight: bold; font-size: 11px; padding: 6px 14px; border-radius: 4px;")
        else:
            self.btn_live_mode.setText("🔴 SIMULATION MODE ONLY")
            self.btn_live_mode.setStyleSheet("background-color: #334155; color: #cbd5e1; font-weight: bold; font-size: 11px; padding: 6px 14px; border-radius: 4px;")

    def on_telemetry_updated(self, all_stats: dict):
        for acc_id, data in all_stats.items():
            if acc_id in self.cards:
                self.cards[acc_id].update_telemetry_ui(data)
