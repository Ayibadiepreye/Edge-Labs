import asyncio, sys
from playwright.async_api import async_playwright

# Set stdout to UTF-8
sys.stdout.reconfigure(encoding='utf-8')

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Search Google
        await page.goto("https://www.google.com/search?q=candlestick+open+high+low+close+formation+cycle+Judas+swing+expansion+phase", wait_until="domcontentloaded")
        await asyncio.sleep(3)
        
        results = await page.eval_on_selector_all(
            "div.g, div[data-sokoban-container]", 
            "elements => elements.slice(0, 5).map(e => ({ title: e.querySelector('h3') ? e.querySelector('h3').innerText : '', snippet: e.querySelector('.VwiC3b, .s3v9rd') ? e.querySelector('.VwiC3b, .s3v9rd').innerText : '' }))"
        )
        
        print("=== GOOGLE SEARCH RESULTS: CANDLESTICK FORMATION CYCLE & OPENING WICKS ===")
        for i, r in enumerate(results):
            if r['title']:
                print(f"[{i+1}] {r['title']}")
                print(f"    {r['snippet']}\n")
            
        await page.goto("https://www.google.com/search?q=how+to+avoid+getting+stopped+out+on+candle+open+scalping+gold+XAUUSD", wait_until="domcontentloaded")
        await asyncio.sleep(3)
        
        results2 = await page.eval_on_selector_all(
            "div.g, div[data-sokoban-container]", 
            "elements => elements.slice(0, 5).map(e => ({ title: e.querySelector('h3') ? e.querySelector('h3').innerText : '', snippet: e.querySelector('.VwiC3b, .s3v9rd') ? e.querySelector('.VwiC3b, .s3v9rd').innerText : '' }))"
        )
        print("\n=== GOOGLE SEARCH RESULTS: AVOIDING STOP OUTS ON CANDLE OPEN ===")
        for i, r in enumerate(results2):
            if r['title']:
                print(f"[{i+1}] {r['title']}")
                print(f"    {r['snippet']}\n")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
