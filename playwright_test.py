import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        # Go to search page directly with parameters
        await page.goto("https://eticket.railway.uz/uz/pages/trains-page?date=28.05.2024&stationFrom=2900000&stationTo=2900790")
        await page.wait_for_timeout(10000)
        content = await page.content()
        
        if "Jaloliddin" in content or "Manguberdi" in content:
            print("FOUND Jaloliddin in HTML!")
            # try to extract its number
            import re
            matches = re.findall(r'.{0,50}Jaloliddin.{0,50}', content)
            print(matches)
        else:
            print("Not found in HTML")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
