import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Search DuckDuckGo full
        await page.goto("https://duckduckgo.com/?q=intraday+candlestick+formation+phases+opening+wick+expansion+microstructure")
        await page.wait_for_selector("article, .result", timeout=10000)
        
        snippets = await page.eval_on_selector_all(
            "article, [data-testid='result']", 
            "elements => elements.slice(0, 5).map(e => e.innerText)"
        )
        
        print("=== PLAYWRIGHT WEB SEARCH RESULTS: CANDLESTICK EXPANSION & WICK TIMING ===")
        for i, s in enumerate(snippets):
            print(f"--- RESULT {i+1} ---")
            print(s[:400] + "\n")
            
        await page.goto("https://duckduckgo.com/?q=how+to+avoid+getting+stopped+out+by+opening+wick+scalping+gold")
        await page.wait_for_selector("article, .result", timeout=10000)
        snippets2 = await page.eval_on_selector_all(
            "article, [data-testid='result']", 
            "elements => elements.slice(0, 5).map(e => e.innerText)"
        )
        print("\n=== PLAYWRIGHT WEB SEARCH RESULTS: AVOIDING OPENING WICK STOP OUTS ===")
        for i, s in enumerate(snippets2):
            print(f"--- RESULT {i+1} ---")
            print(s[:400] + "\n")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
