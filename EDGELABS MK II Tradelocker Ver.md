# EDGELABS MK II — Tradelocker Autonomous Scalping & Flipping Engine
### Master Technical Specification & Architecture Manual (MK II — Kinetic Orderflow Edition)

---

## 1. System Overview & Core Philosophy

**EdgeLabs MK II** is a high-frequency, asymmetric impulse scalping and account flipping system engineered specifically for **XAUUSD (Gold)** on the TradeLocker API platform. 

The core mathematical thesis of MK II is **Extreme Asymmetry ($20 : 1$ Reward-to-Risk)**:
- **Base Profit Target:** $+\$1,000.00\text{ USD}$ per winning wave.
- **Maximum Loss Allowed:** Hard-capped strictly at $\le \$50.00\text{ USD}$ per trade.
- **Asymmetric Edge:** A modest $25\% - 35\%$ win rate rapidly multiplies equity because a single $+\$1,000$ win pays for **twenty** $-\$50$ losses.

MK II completely replaces lagging retail chart patterns (such as static Double Tops) with a **5-Dimensional Pure Kinetic Micro-Physics & Orderflow Model** (Tick Acceleration, Price Velocity, Orderflow Absorption / Drag, Kinematic Expansion Phase, and Multi-Speed Monte Carlo Simulation).

---

## 2. The 5-Dimensional Kinetic Analysis Pipeline

```
                               ┌────────────────────────────────────────────────────────┐
                               │           LIVE TICK INGESTION & BUFFER (100ms)         │
                               └───────────────────────────┬────────────────────────────┘
                                                           │
        ┌──────────────────────────┬───────────────────────┴───────────────┬──────────────────────────┐
        ▼                          ▼                                       ▼                          ▼
┌──────────────────┐     ┌──────────────────┐                    ┌──────────────────┐       ┌──────────────────┐
│  1. DIRECTION    │     │ 2. KINETIC SPEED │                    │ 3. ABSORPTION    │       │ 4. STRUCTURE     │
│  • 20/100/500 M5 │     │ • Tick Velocity  │                    │ • Opposing Wick  │       │ • Swing High/Low │
│  • Short Wave    │     │   (>= 80/min)    │                    │   Drag (< 20%)   │       │ • Resistance Gap │
│  • Impulse Bias  │     │ • Price Velocity │                    │ • Over-Expansion │       │   (>= $0.50)     │
│                  │     │   (>= $0.50/min) │                    │   (<= $2.00)     │       │ • Support Gap    │
└────────┬─────────┘     └────────┬─────────┘                    └────────┬─────────┘       └────────┬─────────┘
         │                        │                                       │                          │
         └────────────────────────┴───────────────────┬───────────────────┴──────────────────────────┘
                                                      │
                                                      ▼
                                       ┌──────────────────────────────┐
                                       │   5. 3-PASS MONTE CARLO      │
                                       │   • Pass 1: Base 1.0x        │
                                       │   • Pass 2: High Speed 1.25x │
                                       │   • Pass 3: Friction 0.75x   │
                                       └──────────────┬───────────────┘
                                                      │
                                                      ▼
                                       ┌──────────────────────────────┐
                                       │  READY_TO_SIMULATE TRIGGER   │
                                       └──────────────────────────────┘
```

### Dimension 1: Directional Impulse
- **Short-Term Window (20 M5 bars / Weight: 30%):** Immediate local momentum.
- **Main Window (100 M5 bars / Weight: 60%):** Primary structural direction.
- **Background Window (500 M5 bars / Weight: 10%):** Macro trend orientation.
- **Breakout Impulse Override:** If a candle surges with high velocity, green body $\ge \$0.25$, opposing wick $< 20\%$, and expansion $\le \$2.00$, the engine immediately aligns with the active impulse.

### Dimension 2: Kinetic Thrust & Speed
- **Fast Speed:** $\ge 80\text{ ticks/min}$ AND $\ge \$0.50/\text{min}$ price velocity.
- **Medium Speed:** $\ge 50\text{ ticks/min}$ AND $\ge \$0.20/\text{min}$.
- **Slow Speed:** $< 50\text{ ticks/min}$ AND $< \$0.20/\text{min}$.
- **Dynamic TP Step:** Automatically scaled based on speed ($0.25\text{ to } 0.75\text{ USD}$).

### Dimension 3: Kinetic Drag & Orderflow Absorption (The Reversal Model)
- **Opposing Wick Drag ($< 20\%$):** Frictionless airflow. Market orders are actively clearing the book without passive limit order resistance.
- **Absorption Warning ($\ge 25\%$):** Institutional limit orders are absorbing the move, forming an opposing wick.
  - BUY is blocked on `UPPER ABSORPTION`.
  - SELL is blocked on `LOWER ABSORPTION`.
- **Kinematic Expansion Guard:** Entry must occur within the first $\$0.25 - \$1.50$ expansion from open ($o$). Extended candles ($> \$3.00$) trigger `OVER-EXPANDED` and are aborted to prevent chasing.
- **Momentum Decay:** Triggered if velocity drops $> 50\%$ mid-candle or bodies shrink consecutively.

### Dimension 4: Structure Clearance
- Price must have at least **$\$0.50\text{ (50 cents)}$ of clear air** below the nearest resistance ceiling for BUY trades, and above the nearest support floor for SELL trades.

### Dimension 5: 3-Pass Monte-Carlo Simulation
Before any trade is executed or simulated on chart:
- **Pass 1 (1.0x):** Base momentum trajectory.
- **Pass 2 (1.25x):** Acceleration & slippage stress test.
- **Pass 3 (0.75x):** Stagnation & friction stress test.
- *At least 2 of 3 passes must test positive within time-to-TP constraints.*

---

## 3. Dynamic Volatility & Speed-Scaled Sizing Protocol

1. **Live Volatility Stop Buffer:**
   - In explosive momentum bursts ($>80\text{ ticks/min}$), Stop-Loss is scaled down to **$3¢ - 5¢$ ($0.03 - 0.05$)** to maximize lot leverage.
   - In moderate/developing flow, Stop-Loss is set to **$6¢ - 7¢$ ($0.06 - 0.07$)** to sit safely behind normal tick vibration.
2. **Derived Lot Sizing with Strict $\$50.00$ Cap:**
   $$\text{Total Lots} = \left\lfloor \frac{\text{MAX\_LOSS\_ALLOWED (\$50.00)}}{\text{Dynamic Stop Buffer} \times \text{Contract Size (100)}} \right\rfloor$$
3. **Exact Dollar Risk Floor:**
   $$\text{SL Distance} = \left\lfloor \frac{\text{MAX\_LOSS\_ALLOWED (\$50.00)}}{\text{Total Lots} \times 100} \times 100 \right\rfloor \div 100$$
   - Dollar risk is strictly capped at **$\le \$50.00\text{ USD}$**.
4. **Dynamic Profit Target Move:**
   $$\text{TP Distance} = \text{round}\left( \frac{\text{BASE\_PROFIT\_TARGET (\$1,000)}}{\text{Total Lots} \times 100}, 2 \right)$$
5. **In-RAM Order Slicing ($\le 3.00\text{ lots/order}$):**
   - Total position is instantly sliced into chunks of $\le 3.00\text{ lots}$ to prevent market impact and broker rejection.

---

## 4. Single-Trade Lifecycle & Candle Lock

To eliminate whipsaw churn on oscillating candles:
1. **Strict "1 Trade Per M5 Candle" Rule:** Once a setup triggers on a candle, `last_traded_candle_ts` is locked. The bot will **never take a second trade on that same 5-minute candle**.
2. **Post-Trade Cooldown:** Mandatory $20 - 30\text{ second}$ pause after any trade closes to let orderflow settle.
3. **Canvas Box Deduplication & Outcomes:**
   - Active scanning candidate box is cleared the moment a trade closes.
   - The finalized trade box remains permanently anchored to its entry candle with a `✓ TP HIT` (green) or `✗ SL HIT` (coral) badge.

---

## 5. UI / UX Architecture & HUD Deck

The graphical interface is built with **PyQt6 + TradingView Lightweight Charts v4.2**:

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   EDGELABS MK II — XAUUSD HUD DECK                                     │
├────────────────────┬────────────────────┬────────────────────┬────────────────────┬────────────────────┤
│ 1. DIRECTION       │ 2. SPEED & STRUCT. │ 3. KINETIC DRAG    │ 4. SIZING & TARGET │ 5. TELEMETRY       │
│ • BIAS: GREEN/RED  │ • SPEED: FAST/MED  │ • BADGE: THRUST/   │ • LOTS: 12.50 L    │ • BID / ASK        │
│ • SHORT: 85%       │ • TICKS: 120/min   │   SCANNING         │ • TARGET: +$1,000  │ • SPREAD: $0.20    │
│ • MAIN:  70%       │ • RESIST: $4428.50 │ • UPPER: 8% CLEAR  │ • MOVE: +$0.80     │ • RAM LATENCY: 0ms │
│ • LONG:  60%       │ • SUPP:   $4415.00 │ • ABSORPTION: CLEAR│ • STOP: -$50 (0.04)│ • ACTIVE TRADES: 0 │
└────────────────────┴────────────────────┴────────────────────┴────────────────────┴────────────────────┘
```

---

## 6. Directory Structure & Key Files

```
edge_labs_bot/
├── core/
│   ├── analysis_engine.py      # 5-D Kinetic Direction, Speed, Absorption & Expansion Engine
│   ├── api_client.py           # TradeLocker API Client & Quote Streamer
│   ├── candle_builder.py       # M5 Candle Constructor & 60s Tick Velocity Buffer
│   └── execution_engine.py     # Dynamic Volatility Sizing, 3-Pass Simulation & Single-Trade Lock
├── ui/
│   └── chart_window.py         # PyQt6 + Lightweight Charts Canvas, HUD Deck & Box Visualizer
├── logs/
│   └── trade_journal.md        # Real-time Execution & Simulation Journal
├── utils/
│   ├── logger.py               # Colorized Multi-Channel Terminal Logger
│   └── rate_limiter.py         # Token-Bucket Adaptive API Rate Limiter
├── config.py                   # Master Config ($1,000 Target, $50 Max Loss)
├── main.py                     # High-Speed Event Loop & Qt Application Entrypoint
└── EDGELABS MK II Tradelocker Ver.md # This Master Specification Document
```

---

## 7. Operational Execution Command

```powershell
cd "C:\Users\Setons\.gemini\antigravity\scratch\edge_labs_bot"
python main.py
```
