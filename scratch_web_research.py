import urllib.request
import urllib.parse
import re

def search_ddg(query):
    url = 'https://html.duckduckgo.com/html/?q=' + urllib.parse.quote(query)
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        html = response.read().decode('utf-8', errors='ignore')
    
    snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', html, re.DOTALL)
    titles = re.findall(r'<a class="result__a[^>]*>(.*?)</a>', html, re.DOTALL)
    
    results = []
    for t, s in zip(titles, snippets):
        clean_t = re.sub(r'<[^>]+>', '', t).strip()
        clean_s = re.sub(r'<[^>]+>', '', s).strip()
        results.append({'title': clean_t, 'snippet': clean_s})
    return results

print("=== SEARCH 1: Candlestick open high low close formation timing ===")
r1 = search_ddg("candlestick lifecycle opening wick expansion phase intraday")
for i, item in enumerate(r1[:4]):
    print(f"[{i+1}] {item['title']}")
    print(f"    {item['snippet']}\n")

print("\n=== SEARCH 2: Avoid fakeouts on candle open tight stop loss XAUUSD scalping ===")
r2 = search_ddg("avoid candle open fakeout wick scalping tight stop loss gold")
for i, item in enumerate(r2[:4]):
    print(f"[{i+1}] {item['title']}")
    print(f"    {item['snippet']}\n")
