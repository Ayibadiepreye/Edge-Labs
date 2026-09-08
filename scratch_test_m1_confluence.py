import sys, os, time
import pandas as pd
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\Users\Setons\.gemini\antigravity\scratch\edge_labs_bot')
from core.api_client import EdgeLabsClient

client = EdgeLabsClient()
# Fetch 1m and 5m candles for today
df_1m = client.tl.get_price_history(client.instrument_id, resolution='1m', lookback_period='1D')
df_5m = client.tl.get_price_history(client.instrument_id, resolution='5m', lookback_period='1D')

df_1m['dt'] = pd.to_datetime(df_1m['t'], unit='ms', utc=True)
df_5m['dt'] = pd.to_datetime(df_5m['t'], unit='ms', utc=True)

today_start = pd.to_datetime('2026-09-01 00:00:00', utc=True)
df_1m = df_1m[df_1m['dt'] >= today_start].copy().reset_index(drop=True)
df_5m = df_5m[df_5m['dt'] >= today_start].copy().reset_index(drop=True)

print(f"=== M1 + M5 CONFLUENCE SIMULATION (Today: {len(df_1m)} M1 bars, {len(df_5m)} M5 bars) ===")

# Test confluence algorithm:
# Rule 1: M5 Trend Bias is strong (score >= 0.30 or previous 2 M5 candles same color)
# Rule 2: Active M1 candle is in the SAME direction with M1 body >= 0.15 and M1 opposing wick < 25%
# Rule 3: Spread <= 10¢ (0.10)
# Rule 4: Dynamic Sweet Spot (scaled by M5 avg body)

confluence_signals = []

for i in range(10, len(df_1m)):
    m1_curr = df_1m.iloc[i]
    m1_time = m1_curr['dt']
    
    # Find matching M5 context
    m5_sub = df_5m[df_5m['dt'] <= m1_time]
    if len(m5_sub) < 3:
        continue
    
    m5_curr = m5_sub.iloc[-1]
    m5_prev = m5_sub.iloc[-2]
    
    # M5 Direction
    m5_is_green = (m5_curr['c'] > m5_curr['o']) and (m5_prev['c'] > m5_prev['o'])
    m5_is_red = (m5_curr['c'] < m5_curr['o']) and (m5_prev['c'] < m5_prev['o'])
    
    # M1 Candle Characteristics
    m1_o = m1_curr['o']
    m1_h = m1_curr['h']
    m1_l = m1_curr['l']
    m1_c = m1_curr['c']
    m1_body = abs(m1_c - m1_o)
    m1_range = max(0.01, m1_h - m1_l)
    
    m1_is_green = (m1_c > m1_o)
    m1_is_red = (m1_c < m1_o)
    
    if m1_is_green:
        m1_opp_wick = (m1_h - m1_c) / m1_range
    else:
        m1_opp_wick = (m1_c - m1_l) / m1_range
        
    # Check alignment
    aligned_buy = (m5_is_green and m1_is_green and m1_body >= 0.20 and m1_opp_wick < 0.25)
    aligned_sell = (m5_is_red and m1_is_red and m1_body >= 0.20 and m1_opp_wick < 0.25)
    
    if aligned_buy or aligned_sell:
        side = 'BUY' if aligned_buy else 'SELL'
        
        # Check forward outcome in next 3-5 M1 bars (+- $2.00 target, 12c stop)
        entry_p = m1_c
        tp_target = (entry_p + 2.00) if side == 'BUY' else (entry_p - 2.00)
        sl_line = (entry_p - 0.12) if side == 'BUY' else (entry_p + 0.12)
        
        # Look forward up to 10 M1 bars
        fwd = df_1m.iloc[i+1:i+11]
        outcome = 'TIMEOUT'
        max_fav = 0.0
        max_adv = 0.0
        
        for _, f_bar in fwd.iterrows():
            if side == 'BUY':
                adv = entry_p - f_bar['l']
                fav = f_bar['h'] - entry_p
                max_fav = max(max_fav, fav)
                max_adv = max(max_adv, adv)
                if f_bar['l'] <= sl_line:
                    outcome = 'LOSS_SL'
                    break
                elif f_bar['h'] >= tp_target:
                    outcome = 'WIN_TP'
                    break
            else:
                adv = f_bar['h'] - entry_p
                fav = entry_p - f_bar['l']
                max_fav = max(max_fav, fav)
                max_adv = max(max_adv, adv)
                if f_bar['h'] >= sl_line:
                    outcome = 'LOSS_SL'
                    break
                elif f_bar['l'] <= tp_target:
                    outcome = 'WIN_TP'
                    break
                    
        confluence_signals.append({
            'time': m1_time.strftime('%H:%M'),
            'side': side,
            'entry': entry_p,
            'm1_body': round(m1_body, 2),
            'm1_opp_wick': round(m1_opp_wick * 100, 1),
            'max_fav': round(max_fav, 2),
            'max_adv': round(max_adv, 2),
            'outcome': outcome
        })

print(f"Total High-Confluence Signals Found Today: {len(confluence_signals)}")
sig_df = pd.DataFrame(confluence_signals)
if not sig_df.empty:
    print(sig_df.head(15).to_string())
    print("\nOutcome Distribution:")
    print(sig_df['outcome'].value_counts().to_string())
