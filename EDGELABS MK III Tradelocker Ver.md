# EDGELABS MK III — Dual-Track Kinetic Execution Specification
### EDGELABS MK III — Dual-Track Kinetic Execution Specification
**Version:** `v3.0 Dual-Track (MK III)`  
**Instrument:** `XAUUSD (Gold CFD)`  
**Architecture:** `Simultaneous Dual-Track Multi-Mode Execution (Track A: $10 Surge Sniper + Track B: $50 Kinetic Scalper)`

---

## 1. Overview & Dual-Track Philosophy

EdgeLabs MK III operates two concurrent algorithmic tracks in parallel RAM to test and exploit the two distinct market regimes of Gold:

1. **TRACK A: "$10 SURGE SNIPER" ($1:100 Asymmetric Trend Wave)**
   - **Max Dollar Risk:** Hard-capped strictly at **`$10.00 USD`**.
   - **Profit Target:** **`+$1,000.00 USD`**.
   - **Target Movement:** **`+$2.50 to +$5.00+`** (Major directional momentum wave).
   - **Strategy:** Enters only during high-conviction macro-trend alignment (20/100/500 M5 score $> 0.65$) with pristine $<5\%$ wick drag, allowing the stop to sit at structural lows while keeping risk under $\$10$.

2. **TRACK B: "$50 KINETIC SCALPER" ($1:20 Rapid Sub-Minute Edge)**
   - **Max Dollar Risk:** Hard-capped strictly at **`$50.00 USD`**.
   - **Profit Target:** **`+$1,000.00 USD`**.
   - **Target Movement:** **`+$1.20 to +$2.20`** (Rapid micro-burst closed in $< 60$ seconds).
   - **Strategy:** Accommodates broker spread ($40¢ - 50¢$) with a $65¢ - 80¢$ dynamic stop breathing room, banking fast $+1,000$ payouts on sub-minute impulses.

---

## 2. The 5-Dimensional Sub-Second Analysis Pipeline

```
                               ┌────────────────────────────────────────────────────────┐
                               │       LIVE TICK INGESTION & ROLLING MICRO-BUFFER       │
                               └───────────────────────────┬────────────────────────────┘
                                                           │
        ┌──────────────────────────┬───────────────────────┴───────────────┬──────────────────────────┐
        ▼                          ▼                                       ▼                          ▼
┌──────────────────┐     ┌──────────────────┐                    ┌──────────────────┐       ┌──────────────────┐
│  1. DIRECTION    │     │ 2. INSTANT SPEED │                    │ 3. ABSORPTION    │       │ 4. STREAM FLOW   │
│  • 20/100/500 M5 │     │ • Sub-Second     │                    │ • Opposing Wick  │       │ • 3-Consecutive  │
│  • Breakout      │     │   Velocity       │                    │   Drag (< 15%)   │       │   Tick Direction │
│    Impulse       │     │   ($/sec)        │                    │ • Over-Expansion │       │ • Spread Lock    │
│    Override      │     │ • Ticks / Sec    │                    │   (<= $2.00)     │       │   (<= $0.20)     │
└────────┬─────────┘     └────────┬─────────┘                    └────────┬─────────┘       └────────┬─────────┘
         │                        │                                       │                          │
         └────────────────────────┴───────────────────┬───────────────────┴──────────────────────────┘
                                                      │
                                                      ▼
                                       ┌──────────────────────────────┐
                                       │   5. 3-PASS MONTE CARLO      │
                                       │   • Pass 1: Base 1.0x        │
                                       │   • Pass 2: High Surge 1.25x │
                                       │   • Pass 3: Stagnation 0.75x │
                                       └──────────────┬───────────────┘
                                                      │
                                                      ▼
                                       ┌──────────────────────────────┐
                                       │  READY_TO_SIMULATE TRIGGER   │
                                       └──────────────────────────────┘
```

### Dimension 1: Directional Impulse & Breakout Override
- **3-Window Background Bias:** 20 M5 bars (30%), 100 M5 bars (60%), and 500 M5 bars (10%).
- **Instant Breakout Override:** If a counter-trend candle bursts with high sub-second speed, green/red body $\ge \$0.20$, and opposing wick $< 15\%$, the engine immediately overrides macro bias and trades the live momentum.

### Dimension 2: Sub-Second Instant Velocity & Dynamic Pulse Scaling
- Measures speed over a tight **$3 - 5\text{ second}$ rolling window** in **$\$ / \text{second}$** and **$\text{ticks / second}$**.
- **Ultra-Fast Impulse ($v \ge \$1.00/\text{min}$):** 1 to 2 rapid pulses $\rightarrow \text{TP} = \$0.25 - \$0.40$ ($1 - 3\text{ seconds}$).
- **Standard Momentum ($v \ge \$0.40/\text{min}$):** 2 to 3 pulses $\rightarrow \text{TP} = \$0.40 - \$0.65$ ($3 - 8\text{ seconds}$).
- **Developing Flow ($v < \$0.40/\text{min}$):** 3 to 4 pulses $\rightarrow \text{TP} = \$0.65 - \$0.95$ ($8 - 20\text{ seconds}$).

### Dimension 3: Kinetic Drag & Orderflow Absorption
- **Opposing Wick Drag ($< 15\%$):** Frictionless airflow.
- **Absorption Defense:** Blocks BUY on `UPPER ABSORPTION` and SELL on `LOWER ABSORPTION`.
- **Expansion Guard:** Forbids entries if candle has already expanded $>\$2.00$ from open.

### Dimension 4: Consecutive 3-Tick Stream Flow & Spread Lock
- Requires **3 consecutive ticks strictly in the trade direction** with $\Delta P \ge 5¢$ displacement before entry.
- Completely locks trading if live spread widens past $\$0.20$ (protecting against overnight chop).

### Dimension 5: 3-Pass Monte-Carlo Simulation
- Evaluates **Live Spread Friction ($0.20$)**, **Opposing Wick Drag**, and **1.5x Noise Jitter**.
- At least 2 of 3 passes must verify that price reaches Take-Profit without touching the Stop-Loss boundary.

---

## 3. Dynamic Lot Sizing, Order Slicing & $\$20$ Risk Cap

1. **Exact Sizing Formula for $+\$1,000$ Target:**
   $$\text{Total Lots} = \left\lfloor \frac{\text{BASE\_PROFIT\_TARGET (\$1,000)}}{\text{TP Distance} \times \text{Contract Size (100)}} \right\rfloor$$
2. **Strict $\$20.00$ Dollar Loss Floor:**
   $$\text{SL Distance} = \left\lfloor \frac{\text{MAX\_LOSS\_ALLOWED (\$20.00)}}{\text{Total Lots} \times 100} \times 100 \right\rfloor \div 100$$
   - Dollar risk is strictly capped at **$\le \$20.00\text{ USD}$** (e.g. $\$17.50 - \$19.98$).
3. **In-RAM Order Slicing ($\le 3.00\text{ lots/order}$):**
   - Total position is instantly sliced into chunks of $\le 3.00\text{ lots}$ in RAM before submission to prevent broker rejection and slippage.

---

## 4. Single-Trade Lifecycle & Candle Lock

To eliminate whipsaw churn on oscillating candles:
1. **Strict "1 Trade Per M5 Candle" Rule:** Once a setup triggers on a candle, `last_traded_candle_ts` is locked. The bot will **never take a second trade on that same 5-minute candle**.
2. **Post-Trade Cooldown:** Mandatory $20 - 30\text{ second}$ pause after any trade closes.
3. **Canvas Box Deduplication & Outcomes:**
   - Active scanning candidate box is cleared the moment a trade closes.
   - The finalized trade box remains permanently anchored to its entry candle with a `✓ TP HIT` (green) or `✗ SL HIT` (coral) badge.

---

## 5. UI / UX Architecture & HUD Deck

The graphical interface is built with **PyQt6 + TradingView Lightweight Charts v4.2**:

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   EDGELABS MK III — XAUUSD HUD DECK                                    │
├────────────────────┬────────────────────┬────────────────────┬────────────────────┬────────────────────┤
│ 1. DIRECTION       │ 2. SPEED & STRUCT. │ 3. KINETIC DRAG    │ 4. SIZING & TARGET │ 5. TELEMETRY       │
│ • BIAS: GREEN/RED  │ • SPEED: FAST/MED  │ • BADGE: THRUST/   │ • LOTS: 25.00 L    │ • BID / ASK        │
│ • SHORT: 85%       │ • TICKS: 120/min   │   SCANNING         │ • TARGET: +$1,000  │ • SPREAD: $0.20    │
│ • MAIN:  70%       │ • RESIST: $4428.50 │ • UPPER: 6% CLEAR  │ • MOVE: +$0.40     │ • RAM LATENCY: 0ms │
│ • LONG:  60%       │ • SUPP:   $4415.00 │ • ABSORPTION: CLEAR│ • STOP: -$20 (MAX) │ • ACTIVE TRADES: 0 │
└────────────────────┴────────────────────┴────────────────────┴────────────────────┴────────────────────┘
```

---

## 6. Directory Structure & Key Files

```
edge_labs_bot/
├── core/
│   ├── analysis_engine.py      # 5-D Kinetic Direction, Speed, Flow Stream & Absorption Engine
│   ├── api_client.py           # TradeLocker API Client & Quote Streamer
│   ├── candle_builder.py       # M5 Candle Constructor & Sub-Second Instant Velocity Buffer
│   └── execution_engine.py     # Micro-Burst Dynamic Pulse Sizing, 3-Pass Sim & $20 Risk Cap
├── ui/
│   └── chart_window.py         # PyQt6 + Lightweight Charts Canvas, HUD Deck & Box Visualizer
├── logs/
│   └── trade_journal.md        # Real-time Execution & Simulation Journal (MK III)
├── utils/
│   ├── logger.py               # Colorized Multi-Channel Terminal Logger
│   └── rate_limiter.py         # Token-Bucket Adaptive API Rate Limiter
├── config.py                   # Master Config ($1,000 Target, $20 Max Loss)
├── main.py                     # High-Speed Event Loop & Qt Application Entrypoint
└── EDGELABS MK III Tradelocker Ver.md # This Master Specification Document
```

---

## 7. Operational Execution Command

```powershell
cd "C:\Users\Setons\.gemini\antigravity\scratch\edge_labs_bot"
python main.py
```
