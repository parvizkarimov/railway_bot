import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as pw:
        # Use a user_agent to avoid 403 Forbidden
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # URL for Toshkent -> Samarqand on 20.05.2026
        url = "https://eticket.railway.uz/uz/pages/trains-page?date=20.05.2026&from=2900000&to=2900700"
        print(f"Navigating to {url}")
        
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        print("Waiting for trains to load...")
        await page.wait_for_timeout(10000) # Wait 10 seconds for angular to render
        
        # Get all elements that look like a train wrapper
        # Let's just get the main container
        cards = await page.evaluate("""
            () => {
                const results = [];
                // Find all buttons on the page to trace their parents
                const btns = document.querySelectorAll('button, a.btn');
                for (const btn of btns) {
                    if (btn.innerText.toLowerCase().includes('tanlash') || btn.innerText.toLowerCase().includes('выбрать') || btn.innerText.toLowerCase().includes('select')) {
                        let parent = btn.parentElement;
                        while(parent && parent.tagName !== 'BODY' && !parent.className.includes('train')) {
                            parent = parent.parentElement;
                        }
                        results.push({
                            btnText: btn.innerText,
                            btnClass: btn.className,
                            parentTag: parent ? parent.tagName : 'NONE',
                            parentClass: parent ? parent.className : 'NONE',
                            parentHtml: parent ? parent.outerHTML.substring(0, 300) : 'NONE'
                        });
                    }
                }
                return results;
            }
        """)
        
        import json
        with open("train_dom_debug.json", "w", encoding="utf-8") as f:
            json.dump(cards, f, indent=2, ensure_ascii=False)
            
        print(f"Found {len(cards)} train selection buttons.")
        await browser.close()

asyncio.run(run())
