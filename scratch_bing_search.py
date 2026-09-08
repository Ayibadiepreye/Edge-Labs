import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Search Bing
        await page.goto("https://www.bing.com/search?q=candlestick+lifecycle+opening+wick+expansion+phase+microstructure+trading", wait_until="domcontentloaded")
        await asyncio.sleep(3)
        
        results = await page.eval_on_selector_all(
            "li.b_algo", 
            "elements => elements.slice(0, 4).map(e => ({ title: e.querySelector('h2') ? e.querySelector('h2').innerText : '', snippet: e.querySelector('.b_caption') ? e.querySelector('.b_caption').innerText : '' }))"
        )
        
        print("=== BING SEARCH 1: CANDLESTICK FORMATION & OPENING WICK EXPANSION ===")
        for i, r in enumerate(results):
            print(f"[{i+1}] {r['title']}")
            print(f"    {r['snippet']}\n")
            
        await page.goto("https://www.bing.com/search?q=how+to+avoid+wick+fakeout+on+candle+open+scalping+gold+tight+stop+loss", wait_until="domcontentloaded")
        await asyncio.sleep(3)
        
        results2 = await page.eval_on_selector_all(
            "li.b_algo", 
            "elements => elements.slice(0, 4).map(e => ({ title: e.querySelector('h2') ? e.querySelector('h2').innerText : '', snippet: e.querySelector('.b_caption') ? e.querySelector('.b_caption').innerText : '' }))"
        )
        print("\n=== BING SEARCH 2: AVOIDING OPENING WICK STOP OUTS ===")
        for i, r in enumerate(results2):
            print(f"[{i+1}] {r['title']}")
            print(f"    {r['snippet']}\n")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
