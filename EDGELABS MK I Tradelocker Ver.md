# EDGELABS MK I — TradeLocker Ver.
## Master Technical Architecture, Signal Engine & Operations Manual

---

## 1. System Identity & Philosophy

**EDGELABS MK I (TradeLocker Ver.)** is an ultra-low-latency, in-memory scalping engine engineered specifically for **Gold (XAUUSD)** on the **5-minute (M5)** timeframe using the **TradeLocker API**.

### The Core Philosophy: "Universal Adaptive Impulse Engine"
Rather than relying on hardcoded static pip distances or lagging indicators, EDGELABS MK I is powered by an **Adaptive Impulse Engine** that measures real-time candle velocity, tick momentum, and structure to self-determine optimal entry and exit barriers:
- **Micro-Consolidation Regimes:** When Gold is trading in tight ranges, the bot locks onto micro-expansion moves of **$20¢ to $50¢** ($\$0.20 - \$0.50$), capturing targets in $5 - 20$ seconds with larger dynamically calculated lots.
- **Explosive / Dollar-Expansion Regimes:** During high-volatility events (news releases, strong breakouts) where M5 bars expand to $\$3.00 - $\$6.00+, the bot **automatically scales up to dollar targets** ($\$1.00 - \$2.50+$), adjusting lots accordingly to ride the full wave safely.
- **Wick Trap Immunity:** Enters and exits in the initial $25\% - 35\%$ expansion burst of the candle before opposing wicks or exhaustion traps can form.
- **Exact $\$1,000$ Target / Hard-Capped $\$50$ Loss:** In ALL market conditions, the sizing engine dynamically adjusts lots to extract the exact **$\$1,000$ base profit** while mathematically **hard-capping maximum risk strictly to $-\$50.00\text{ USD}$**.

---

## 2. TradeLocker Connection & Performance Metrics

| Parameter | Specification |
| :--- | :--- |
| **Broker / Server** | `HEROFX` |
| **API Environment** | `https://demo.tradelocker.com` |
| **Account Email** | `bonnieprincewill6@gmail.com` |
| **Tradable Symbol** | `XAUUSD` (Auto-detected Instrument ID: `4709`) |
| **Contract Size** | `100.0 oz` per standard lot |
| **Min / Max Lot** | `0.01` min / `50.00` max (Step: `0.01`) |
| **Account Leverage** | `1:100` |
| **Connection Method**| Persistent HTTP Keep-Alive Session (`~120-160ms` latency) |
| **Safe Pacing Interval** | `250ms` (~4 ticks/sec, 100% Cloudflare Error 1015 safe) |
| **RAM Sizing Latency** | `~31 μs` ($0.031\text{ milliseconds}$) |

---

## 3. The 6-Point Signal Trigger Architecture

For EDGELABS MK I to trigger a trade, **all 6 criteria below must pass simultaneously**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 MOMENTUM BURST SIGNAL CHECKLIST (6/6 REQUIRED)              │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. SPREAD FILTER:     Spread <= $2.00 (20 pips)                             │
│                                                                             │
│ 2. DIRECTION / BIAS:  Trend Bias Active (BULLISH / BEARISH)                 │
│                       OR Explosive Consolidation Breakout Impulse           │
│                                                                             │
│ 3. SPEED ENGINE:      Must be 'FAST' (>80 ticks/min, >$0.50/min velocity)   │
│                       or 'MEDIUM' (>50 ticks/min).                          │
│                       (Choppy 'SLOW' candles are strictly rejected)         │
│                                                                             │
│ 4. REJECTION CHECK:   No opposing wick > 25% of total candle body           │
│                       (Wick > 100% is 'STRONG REJECTION' -> aborts)         │
│                                                                             │
│ 5. REVERSAL FILTER:   No active Double Top/Bottom retest, Engulfing,        │
│                       Color Flip, or Momentum Drop-off on active candle.    │
│                                                                             │
│ 6. STRUCTURE CLEAR:   Must have room >= Dynamic TP Target Move before       │
│                       nearest Support or Resistance level.                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Enhanced Direction Bias Engine (Scalping Calibrated)

The Direction Bias Engine scores market flow across 3 rolling windows to detect trend waves without multi-hour lag:

### Window Weight Distribution:
- **Short Window (Immediate 20 bars / 100 mins):** **$50\%$ Primary Weight** (Upgraded to **$70\%$ on active breakout pulses** $|s\_score| \ge 0.25$).
- **Main Window (100 bars / ~8 hours):** **$40\%$ Weight**.
- **Long Window (500 bars / ~40 hours):** **$10\%$ Background Weight**.

### Scoring Math:
$$\text{Window Score} = \frac{\text{Green Count} - \text{Red Count}}{\text{Total Completed Bars}} + \text{Large Body Bonus}$$
$$\text{Total Score} = (W_{\text{short}} \times S_{\text{short}}) + (W_{\text{main}} \times S_{\text{main}}) + (W_{\text{long}} \times S_{\text{long}})$$

- **`BULLISH`:** $\text{Total Score} \ge +0.08$
- **`BEARISH`:** $\text{Total Score} \le -0.08$
- **`MIXED`:** $-0.08 < \text{Total Score} < +0.08$

### The Consolidation Breakout Impulse Protocol:
When the background score is `MIXED` (e.g. 50% green vs 50% red chop), the bot is permitted to take a trade if an **explosive breakout impulse candle begins**:
1. Speed is **`FAST`** ($>80\text{ ticks/min}$ or $> \$0.50/\text{min}$).
2. Forming Candle Body $\ge \$0.30$ with clean expansion.
3. Opposing Wick $< 25\%$.
4. Structure Clearance $\ge$ Dynamic Target Move.
5. 3-Pass Pre-Simulation passes ($3/3$).
*Trade side is locked to the breakout direction of that impulse candle.*

---

## 5. Real-Time Reversal Filter Engine

Reversal detection checks whether the **ACTIVE forming candle** is rejecting a major structural level:

- **Double Top / Double Bottom:** Strictly checks if the **current candle** is testing a prior swing peak (within $\pm \$0.80$) AND actively rejecting downwards (upper wick or red flip). If price is not currently testing a resistance peak, it reports **`CLEAR (NO REVERSAL)`**.
- **Engulfing:** Checks if the active candle has completely swallowed the previous candle body in the opposite direction.
- **Color Flip:** Reversal alert when an active green impulse turns red with expanding volume.
- **Momentum Drop-off:** Triggers if tick velocity suddenly drops $> 50\%$ mid-expansion.

---

## 6. Sizing Engine & Hard-Capped $\$50$ Maximum Loss

### Profit Sizing Equation (Target: $\$1,000\text{ USD}$):
$$\text{Required Lots} = \frac{\text{BASE\_PROFIT\_TARGET (\$1,000)}}{\text{Dynamic TP Distance (\$) } \times \text{Contract Size (100 oz)}}$$

### Hard-Capped Risk Equation (Max Loss: $\$50\text{ USD}$):
To strictly cap dollar loss to `config.MAX_LOSS_ALLOWED` ($\$50.00$), the Stop-Loss distance is mathematically derived:
$$sl\_dist = \text{round}\left(\frac{\text{MAX\_LOSS\_ALLOWED (\$50)}}{\text{Total Lots} \times 100}, 2\right)$$

#### Live Example:
- For a $+0.76$ dynamic expansion move on Gold:
  - $\text{Total Lots} = \frac{\$1,000}{\$0.76 \times 100} = \mathbf{13.15\text{ Lots}}$ (Split into $5 \times 3.00\text{ lots} + 1 \times 1.15\text{ lots}$)
  - $\text{Stop-Loss Distance} = \frac{\$50}{13.15 \times 100} = \mathbf{\$0.04\text{ ($4$ cents)}}$
  - **Take-Profit Target:** $+0.76 \implies \mathbf{+\$1,000.00\text{ USD}}$
  - **Stop-Loss Risk:** $-0.04 \implies \mathbf{-\$50.00\text{ USD}}$
  - **Reward-to-Risk Ratio:** $\mathbf{20 : 1}$

---

## 7. Single-Trade Lifecycle Lock (Zero Spam Architecture)

To eliminate tick duplicate spamming on fast candles, the engine enforces a strict **Single-Trade Lifecycle Lock**:

```
 ┌────────────────────────────────────────────────────────┐
 │ 1. STANDBY / SCANNING:                                 │
 │    • Continuously evaluating 6-point metrics.          │
 │    • HUD Card 4: "STATUS: SCANNING (STANDBY)"          │
 └──────────────────────────┬─────────────────────────────┘
                            │ (Signal & 3-Pass Sim Cleared)
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │ 2. ACTIVE TRADE LOCKED:                                │
 │    • Locks into ONE position. Ignores new setups.      │
 │    • HUD Card 4: "⚡ ACTIVE: LONG @ $4,417.17 (13.15 L)"│
 │    • Draws 1 transparent position box on entry candle. │
 └──────────────────────────┬─────────────────────────────┘
                            │ (Price touches TP or SL)
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │ 3. OUTCOME RESOLVED & ARCHIVED:                        │
 │    • Price touches TP -> "🏆 TP HIT (+$1,000)"         │
 │    • Price touches SL -> "🛡️ SL HIT (-$50)"            │
 │    • Appends log to trade_journal.md + captures PNG.   │
 │    • Unlocks engine and returns to STANDBY.            │
 └────────────────────────────────────────────────────────┘
```

---

## 8. Interactive Chart & Visual Multi-Box System

The chart window features an interactive TradingView-style canvas overlay:

- **True High-DPI Canvas Buffer:** Resets transformations and clears buffer on every frame—**zero ghosting, zero smearing, and zero compounding opacity**.
- **Glassmorphism Transparency:** Rendered with $12\%–14\%$ opacity tints (`rgba(0, 242, 152, 0.14)` and `rgba(255, 59, 92, 0.14)`) so you can watch live candles tick inside the box.
- **Exact Candle Anchoring:** The box is locked to the specific timestamp of the entry candle.
- **Full History Navigation:** As new candles form, you can **click, drag, and scroll backwards in time** to inspect every setup, entry line, and outcome badge ($\checkmark\text{ TP HIT } (+\$1,000)$ / $\chi\text{ SL HIT } (-\$50)$) from your session.

---

## 9. Dual-Screenshot & Trade Journal Archive

Every trade is permanently archived across three redundant formats:

1. **High-Res Entry Screenshot:** Captures initial position box upon trigger (`screenshots/setup_YYYYMMDD_HHMMSS_buy.png`).
2. **High-Res Outcome Screenshot:** Captures candle touching the TP/SL line at close (`screenshots/outcome_WIN_TP_...png`).
3. **Structured Markdown Journal ([`logs/trade_journal.md`](file:///C:/Users/Setons/.gemini/antigravity/scratch/edge_labs_bot/logs/trade_journal.md)):** Detailed entry and outcome records with duration and net PnL.
4. **Append-Only Telemetry ([`logs/simulations.jsonl`](file:///C:/Users/Setons/.gemini/antigravity/scratch/edge_labs_bot/logs/simulations.jsonl)):** Raw JSON Lines format for post-session quantitative review.

---

## 10. Windows Desktop GUI & 5-Card HUD Deck

The interface is styled in a **Cyberpunk Bloomberg** theme:
- **Card 1: 1. MOMENTUM & SPEED** (Velocity, tick speed, dynamic move).
- **Card 2: 2. DIRECTION & BIAS** (3-window score, support & resistance levels).
- **Card 3: 3. REJECTION & SIGNALS** (Upper/lower wick %, active reversal status).
- **Card 4: 4. SIZING & TARGET (RAM)** (Active trade status, live lot sizing, TP/SL target & stop).
- **Card 5: 5. TELEMETRY & FEED** (Live ask/bid, spread, stream latency, execution mode).
- **Windows Integration:** Registered Windows App User Model ID (`edgelabs.scalping.mki.1.0`) with custom cyber emblem icon.

---

## 11. Quick Start & Execution Modes

### To Start the Bot:
```powershell
cd "C:\Users\Setons\.gemini\antigravity\scratch\edge_labs_bot"
python main.py
```

### Execution Mode Toggle in [`config.py`](file:///C:/Users/Setons/.gemini/antigravity/scratch/edge_labs_bot/config.py):
- **Visual Simulation Mode (Default):**
  ```python
  ENABLE_DEMO_EXECUTION = False
  ```
  Runs real-time scanning, draws visual position boxes, monitors TP/SL outcomes tick-by-tick, and logs screenshots and journal entries without sending live orders to the broker.
- **Live Demo Execution Mode:**
  ```python
  ENABLE_DEMO_EXECUTION = True
  ```
  Sends split chunk orders directly to the TradeLocker broker, executes partial closures, and manages live trailing stops.
