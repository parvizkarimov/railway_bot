import asyncio
from playwright.async_api import async_playwright
import json

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            "--no-sandbox", 
            "--disable-dev-shm-usage",
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-zygote",
            "--single-process"
        ])
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 720}
        )
        page = await context.new_page()
        
        await page.set_extra_http_headers({
            "Accept-Language": "uz-UZ,uz;q=0.9,ru;q=0.8,en;q=0.7",
            "Upgrade-Insecure-Requests": "1"
        })

        print("Navigating...")
        response = await page.goto("https://eticket.railway.uz/uz/pages/trains-page", wait_until="domcontentloaded", timeout=40000)
        print(f"Status: {response.status if response else 'None'}")
        
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:
            print(f"Networkidle timeout: {e}")

        cookies = await context.cookies()
        print("Cookies:")
        for c in cookies:
            print(f"- {c['name']} = {c['value'][:20]}...")
            
        # Let's also check the title and content
        title = await page.title()
        print(f"Title: {title}")
        content = await page.content()
        print(f"Content length: {len(content)}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
