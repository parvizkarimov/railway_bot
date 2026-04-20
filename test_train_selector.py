import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # User's exact case
        t_num = "127Ф"
        # We need a valid date. Let's find one that has 127Ф.
        # Actually, let's just go to a date and see what trains exist.
        url = "https://eticket.railway.uz/uz/pages/trains-page?date=25.04.2026&from=2900000&to=2900700"
        print(f"Navigating to {url}")
        
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_timeout(8000)
        
        await page.screenshot(path="test_error.png")
        
        train_items = await page.query_selector_all('app-train-item, li.train-item, .train-card, [class*="train-item"]')
        print(f"Found {len(train_items)} train_items elements")
        
        for i, item in enumerate(train_items):
            text = await item.inner_text()
            print(f"Item {i} text: {text[:50].replace(chr(10), ' ')}")
            btn = await item.query_selector('a.btn.btn-primary, button.btn-primary, button, a.btn')
            print(f"  Btn: {'FOUND' if btn else 'NONE'}")
            
        await browser.close()

asyncio.run(run())
