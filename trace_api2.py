import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 720}
        )
        page = await context.new_page()
        
        async def handle_request(request):
            if request.method == "POST" and "/api/" in request.url:
                print(f"-> {request.method} {request.url}")
                try:
                    print("Request body:", request.post_data)
                except: pass

        page.on("request", handle_request)
        
        print("Going to railway site...")
        await page.goto("https://eticket.railway.uz/uz/pages/trains-page?date=25.07.2026&stationFrom=2900000&stationTo=2900790", wait_until="networkidle", timeout=60000)
        
        # Click the search button. It has text "Izlash" or "Найти" or "Search"
        print("Clicking search button...")
        try:
            # The button might be disabled until stations are loaded. Let's wait.
            await page.wait_for_timeout(5000)
            await page.evaluate("""
                () => {
                    const btns = Array.from(document.querySelectorAll('button'));
                    const searchBtn = btns.find(b => b.innerText.toLowerCase().includes('izlash') || b.innerText.toLowerCase().includes('найти') || b.innerText.toLowerCase().includes('topish'));
                    if(searchBtn) searchBtn.click();
                }
            """)
            await page.wait_for_timeout(10000)
        except Exception as e:
            print("Failed to click:", e)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
