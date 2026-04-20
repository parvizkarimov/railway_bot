import asyncio
from playwright.async_api import async_playwright
import json

async def run():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        url = "https://eticket.railway.uz/uz/pages/trains-page?date=20.05.2026&from=2900000&to=2900700"
        print(f"Navigating to {url}")
        
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(10000)
        
        # Get all text from body
        body_text = await page.evaluate("() => document.body.innerText")
        print(f"Body text length: {len(body_text)}")
        print("First 500 chars:")
        print(body_text[:500])
        
        # Look for 127 in body
        print("Contains '127':", "127" in body_text)
        print("Contains '127Ф':", "127Ф" in body_text)
        
        await browser.close()

asyncio.run(run())
