import asyncio
import aiohttp
from datetime import datetime

async def get_cookie():
    return "YOUR_COOKIE", "YOUR_XSRF"

async def check():
    url = "https://eticket.railway.uz/api/v3/handbook/trains/list"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Device-Type": "BROWSER"
    }
    # 2900000 Toshkent
    # 2900790 Urgench
    payload = {"directions": {"forward": {"date": "2024-05-28", "depStationCode": "2900000", "arvStationCode": "2900790"}}}
    
    # We won't pass valid cookies, so it might fail or give 403, but let's see.
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as r:
            print(r.status)
            if r.status == 200:
                print(await r.text())
                
if __name__ == "__main__":
    asyncio.run(check())
