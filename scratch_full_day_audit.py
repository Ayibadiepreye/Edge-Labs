import sys, os, time
import pandas as pd
import numpy as np
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\Users\Setons\.gemini\antigravity\scratch\edge_labs_bot')
from core.api_client import EdgeLabsClient
from core.analysis_engine import AnalysisEngine, _candle_body, _is_green
from core.execution_engine import ExecutionEngine
import config

client = EdgeLabsClient()
df = client.get_historical_candles('2D')
df['dt'] = pd.to_datetime(df['t'], unit='ms', utc=True)

# Filter for today's candles: 2026-09-01 from 00:00 UTC onwards
today_start = pd.to_datetime('2026-09-01 00:00:00', utc=True)
today_df = df[df['dt'] >= today_start].copy().reset_index(drop=True)

candles_list = today_df.to_dict('records')

ae = AnalysisEngine()
ee = ExecutionEngine(client=client)

print(f"=== FULL DAY UNBIASED M5 CANDLE AUDIT (2026-09-01: {len(candles_list)} CANDLES) ===")

results = []
for i in range(1, len(candles_list)):
    history = candles_list[:i]
    current_c = candles_list[i]
    t_str = current_c['dt'].strftime('%H:%M')
    
    # Analyze candle structure
    open_p = current_c['o']
    high_p = current_c['h']
    low_p = current_c['l']
    close_p = current_c['c']
    body = abs(close_p - open_p)
    rng = max(0.01, high_p - low_p)
    color = 'GREEN' if close_p > open_p else ('RED' if close_p < open_p else 'DOJI')
    
    if color == 'GREEN':
        upper_wick = high_p - close_p
        lower_wick = open_p - low_p
    else:
        upper_wick = high_p - open_p
        lower_wick = close_p - low_p
        
    upper_ratio = upper_wick / rng
    lower_ratio = lower_wick / rng
    
    # Run Analysis Engine on this historical candle as if it was forming/completing
    snap = ae.analyse(
        completed_candles=history,
        forming_candle=current_c,
        tick_velocity=50.0,
        price_velocity=body / 5.0,
        current_price=close_p,
        spread=0.07,
        orderflow_delta={'delta_ratio': 0.45 if color == 'GREEN' else -0.45}
    )
    
    setup = ee.calculate_trade_setup(snap, entry_price=close_p, candle_time=int(current_c['t']))
    
    tr_a = setup['track_a']['simulation_passed']
    tr_b = setup['track_b']['simulation_passed']
    
    # Identify failing factors
    reasons = []
    if not snap.is_sweetspot_ignition:
        reasons.append(f"SweetSpot({snap.directional_displacement:.2f}$ not in [{snap.sweetspot_min}-{snap.sweetspot_max}])")
    if snap.direction.bias == 'mixed':
        reasons.append(f"TrendBias(mixed score {snap.direction.score:.2f})")
    if (upper_ratio >= 0.18 and color == 'GREEN') or (lower_ratio >= 0.18 and color == 'RED'):
        opp_w = upper_ratio if color == 'GREEN' else lower_ratio
        reasons.append(f"OpposingWick({opp_w*100:.0f}% >= 18%)")
    if snap.speed.classification == 'slow':
        reasons.append("Speed(slow)")
    if not snap.opening_window_cleared:
        reasons.append("OpeningTimer(<20s)")
    if not snap.ready_to_simulate and not (tr_a or tr_b):
        if not reasons:
            reasons.append("SimFilterFail")
            
    status_str = "TRIGGERED" if (tr_a or tr_b) else f"BLOCKED: {', '.join(reasons)}"
    
    results.append({
        'time': t_str,
        'color': color,
        'open': open_p,
        'high': high_p,
        'low': low_p,
        'close': close_p,
        'body': body,
        'range': rng,
        'upper_w_pct': round(upper_ratio * 100, 1),
        'lower_w_pct': round(lower_ratio * 100, 1),
        'disp': snap.directional_displacement,
        'sweet_ign': snap.is_sweetspot_ignition,
        'dir_bias': snap.direction.bias,
        'dir_score': round(snap.direction.score, 2),
        'tr_a': tr_a,
        'tr_b': tr_b,
        'reasons': reasons,
        'status_str': status_str
    })

res_df = pd.DataFrame(results)
print(f"\nTotal Analyzed Candles Today: {len(res_df)}")
triggered_cnt = len(res_df[(res_df['tr_a'] == True) | (res_df['tr_b'] == True)])
print(f"Total Candles That Triggered: {triggered_cnt}")

print("\n=== TOP 10 LARGEST IMPULSE CANDLES TODAY ===")
top_movers = res_df.sort_values(by='body', ascending=False).head(10)
for _, r in top_movers.iterrows():
    opp_w_pct = r['upper_w_pct'] if r['color'] == 'GREEN' else r['lower_w_pct']
    print(f"[{r['time']} UTC] {r['color']} | Body: ${r['body']:.2f} | Range: ${r['range']:.2f} | Opposing Wick: {opp_w_pct}% | Bias: {r['dir_bias']} ({r['dir_score']}) | Status: {r['status_str']}")

print("\n=== HOURLY SESSION BREAKDOWN ===")
res_df['hour'] = res_df['time'].apply(lambda x: x.split(':')[0])
for hr, grp in res_df.groupby('hour'):
    avg_body = grp['body'].mean()
    avg_range = grp['range'].mean()
    green_c = len(grp[grp['color']=='GREEN'])
    red_c = len(grp[grp['color']=='RED'])
    print(f"Hour {hr}:00 UTC -> Candles: {len(grp)} (Green: {green_c}, Red: {red_c}) | Avg Body: ${avg_body:.2f} | Avg Range: ${avg_range:.2f}")

print("\n=== ALL REJECTION REASONS FREQUENCY TODAY ===")
all_reasons = []
for r in res_df['reasons']:
    all_reasons.extend([x.split('(')[0] for x in r])
s_reasons = pd.Series(all_reasons).value_counts()
print(s_reasons.to_string())
