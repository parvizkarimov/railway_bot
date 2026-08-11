import asyncio
from playwright.async_api import async_playwright
from urllib.parse import unquote

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        await page.goto("https://eticket.railway.uz/api/v1/csrf-token", wait_until="networkidle", timeout=40000)
        
        cookies = await context.cookies()
        xsrf = unquote(next((c["value"] for c in cookies if c["name"].upper() == "XSRF-TOKEN"), ""))
        print("Found XSRF:", xsrf)
        if xsrf:
            print("Cookies:", cookies)
            
        await browser.close()
        
if __name__ == "__main__":
    asyncio.run(test())
