import sys
import pandas as pd
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\Users\Setons\.gemini\antigravity\scratch\edge_labs_bot')
from core.api_client import EdgeLabsClient

client = EdgeLabsClient()
df_1m = client.tl.get_price_history(client.instrument_id, resolution='1m', lookback_period='1D')
df_5m = client.tl.get_price_history(client.instrument_id, resolution='5m', lookback_period='1D')

df_1m['dt'] = pd.to_datetime(df_1m['t'], unit='ms', utc=True)
df_5m['dt'] = pd.to_datetime(df_5m['t'], unit='ms', utc=True)

today_start = pd.to_datetime('2026-09-01 00:00:00', utc=True)
df_1m = df_1m[df_1m['dt'] >= today_start].copy().reset_index(drop=True)
df_5m = df_5m[df_5m['dt'] >= today_start].copy().reset_index(drop=True)

# Calculate indicators
df_1m['ema9'] = df_1m['c'].ewm(span=9, adjust=False).mean()
df_1m['ema21'] = df_1m['c'].ewm(span=21, adjust=False).mean()

df_5m['ema9'] = df_5m['c'].ewm(span=9, adjust=False).mean()
df_5m['ema21'] = df_5m['c'].ewm(span=21, adjust=False).mean()

print("=== QUANTITATIVE M1 + M5 MULTI-TIMEFRAME AUDIT ===")

# Test Strategy:
# 1. M5 EMA9 > EMA21 for BUY, EMA9 < EMA21 for SELL (Clear Trend Filter)
# 2. M1 Ignition: M1 candle pulls back to M1 EMA9 and then forms a strong rejection wick (< 15% opp wick) and breaks past open
# 3. Breakeven at +$0.50 favorable move
# 4. Target: +$1.50 to +$2.00

for sl_val in [0.12, 0.20, 0.30]:
    wins = 0
    bes = 0
    losses = 0
    net_pnl = 0.0
    trades = []
    
    for i in range(25, len(df_1m)-10):
        m1 = df_1m.iloc[i]
        m1_t = m1['dt']
        m5_sub = df_5m[df_5m['dt'] <= m1_t]
        if len(m5_sub) < 5: continue
        m5 = m5_sub.iloc[-1]
        
        m5_trend_buy = (m5['c'] > m5['ema9'] > m5['ema21'])
        m5_trend_sell = (m5['c'] < m5['ema9'] < m5['ema21'])
        
        m1_body = abs(m1['c'] - m1['o'])
        m1_range = max(0.01, m1['h'] - m1['l'])
        
        # M1 Ignition with clean airflow (opposing wick < 15%)
        if m5_trend_buy and m1['c'] > m1['o'] and m1_body >= 0.20 and ((m1['h'] - m1['c'])/m1_range) < 0.15:
            side = 'BUY'
        elif m5_trend_sell and m1['c'] < m1['o'] and m1_body >= 0.20 and ((m1['c'] - m1['l'])/m1_range) < 0.15:
            side = 'SELL'
        else:
            continue
            
        entry_p = m1['c']
        tp_target = entry_p + 1.50 if side == 'BUY' else entry_p - 1.50
        sl_line = entry_p - sl_val if side == 'BUY' else entry_p + sl_val
        be_line = entry_p + 0.40 if side == 'BUY' else entry_p - 0.40
        
        be_active = False
        outcome = 'TIMEOUT'
        
        for j in range(i+1, min(i+15, len(df_1m))):
            f_bar = df_1m.iloc[j]
            if side == 'BUY':
                if not be_active and f_bar['h'] >= be_line:
                    be_active = True
                    sl_line = entry_p  # Move SL to breakeven!
                if f_bar['l'] <= sl_line:
                    outcome = 'BE' if be_active else 'LOSS'
                    break
                elif f_bar['h'] >= tp_target:
                    outcome = 'WIN'
                    break
            else:
                if not be_active and f_bar['l'] <= be_line:
                    be_active = True
                    sl_line = entry_p
                if f_bar['h'] >= sl_line:
                    outcome = 'BE' if be_active else 'LOSS'
                    break
                elif f_bar['l'] <= tp_target:
                    outcome = 'WIN'
                    break
                    
        if outcome == 'WIN':
            wins += 1
            net_pnl += (1.50 * 10)  # +$15.00 on 0.10L
        elif outcome == 'BE':
            bes += 1
            net_pnl += 0.0
        elif outcome == 'LOSS':
            losses += 1
            net_pnl -= (sl_val * 10) # -$1.20 to -$3.00 on 0.10L
            
    total_trades = wins + bes + losses
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    prot_rate = ((wins + bes) / total_trades * 100) if total_trades > 0 else 0
    print(f"SL: {int(sl_val*100)}¢ | Trades: {total_trades} | Wins: {wins} | Breakevens: {bes} | Losses: {losses} | Pure Win Rate: {win_rate:.1f}% | Capital Protection Rate: {prot_rate:.1f}% | Net PnL (0.10L): ${net_pnl:+.2f}")
