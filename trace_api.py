import asyncio
from playwright.async_api import async_playwright
import json

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 720}
        )
        page = await context.new_page()
        
        page.on("request", lambda request: print(f"-> {request.method} {request.url}") if "/api/" in request.url else None)
        
        async def handle_response(response):
            if "/api/" in response.url:
                print(f"<- {response.status} {response.url}")
                if "trains" in response.url:
                    try:
                        print("Body:", await response.text())
                    except:
                        pass
        
        page.on("response", handle_response)
        
        print("Going to railway site...")
        await page.goto("https://eticket.railway.uz/uz/pages/trains-page?date=25.07.2026&stationFrom=2900000&stationTo=2900790", wait_until="domcontentloaded", timeout=60000)
        
        print("Waiting 15s for page to load and API calls to finish...")
        await page.wait_for_timeout(15000)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
