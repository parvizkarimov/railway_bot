import asyncio
from playwright.async_api import async_playwright
import datetime

async def run():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        
        target_date = (datetime.datetime.now() + datetime.timedelta(days=5)).strftime("%d.%m.%Y")
        url = f"https://eticket.railway.uz/uz/pages/trains-page?date={target_date}&from=2900000&to=2900700"
        
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(8000)
        
        body_html = await page.evaluate("() => document.body.innerHTML")
        with open("body.html", "w", encoding="utf-8") as f:
            f.write(body_html)
            
        await browser.close()

asyncio.run(run())
