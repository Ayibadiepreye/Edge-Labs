import re
from pathlib import Path

journal_path = Path("logs/trade_journal.md")
content = journal_path.read_text(encoding="utf-8")
blocks = [b.strip() for b in content.split("---") if b.strip()]

entries = []

for b in blocks:
    if "Setup Triggered" in b:
        t_m = re.search(r"Setup Triggered — ([^\n\r]+)", b)
        side_m = "BUY" if "BUY" in b else "SELL"
        entry_m = re.search(r"Entry Price:\*\* `\$([0-9\.]+)`", b)
        tp_m = re.search(r"Take Profit:\*\* `\$([0-9\.]+)`", b)
        sl_m = re.search(r"Stop Loss:\*\* `\$([0-9\.]+)`", b)
        lots_m = re.search(r"Position Size:\*\* `([0-9\.]+) Lots`", b)
        entries.append({
            "type": "SETUP",
            "time": t_m.group(1) if t_m else "?",
            "side": side_m,
            "entry": float(entry_m.group(1)) if entry_m else 0,
            "tp": float(tp_m.group(1)) if tp_m else 0,
            "sl": float(sl_m.group(1)) if sl_m else 0,
            "lots": float(lots_m.group(1)) if lots_m else 0,
        })
    elif "RESULT:" in b:
        is_win = "TAKE-PROFIT" in b
        exit_m = re.search(r"Exit Price:\*\* `\$([0-9\.]+)`", b)
        dur_m = re.search(r"Trade Duration:\*\* `([0-9\.]+) seconds`", b)
        pnl_m = re.search(r"Net PnL:\*\* `([^`]+)`", b)
        time_m = re.search(r"Closed At:\*\* `([^`]+)`", b)
        entries.append({
            "type": "WIN" if is_win else "LOSS",
            "time": time_m.group(1) if time_m else "?",
            "exit": float(exit_m.group(1)) if exit_m else 0,
            "dur": float(dur_m.group(1)) if dur_m else 0,
            "pnl": pnl_m.group(1) if pnl_m else "",
        })

wins = [e for e in entries if e["type"] == "WIN"]
losses = [e for e in entries if e["type"] == "LOSS"]

print(f"TOTAL LOGGED WINS:   {len(wins)}")
print(f"TOTAL LOGGED LOSSES: {len(losses)}")
print("\n--- FIRST 10 WINS ---")
for i, w in enumerate(wins[:10]):
    print(f"WIN #{i+1:02d} | Closed: {w['time']} | Exit Price: ${w['exit']:.2f} | Duration: {w['dur']}s | PnL: {w['pnl']}")

print("\n--- FIRST 10 LOSSES ---")
for i, l in enumerate(losses[:10]):
    print(f"LOSS #{i+1:02d} | Closed: {l['time']} | Exit Price: ${l['exit']:.2f} | Duration: {l['dur']}s | PnL: {l['pnl']}")
