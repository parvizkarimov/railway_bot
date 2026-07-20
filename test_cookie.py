import asyncio
import aiohttp

async def test():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Device-Type": "BROWSER"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get("https://eticket.railway.uz/api/v1/csrf-token", headers=headers) as resp:
            xsrf = resp.cookies.get('XSRF-TOKEN').value
            
        headers["X-Xsrf-Token"] = xsrf
        headers["Cookie"] = f"XSRF-TOKEN={xsrf}"
        
        url = "https://eticket.railway.uz/api/v1/handbook/stations/list"
        async with session.post(url, headers=headers, json={"name":""}) as resp:
            data = await resp.json()
            # print the first 5 stations
            print(data[:5] if isinstance(data, list) else list(data.keys())[:5])

if __name__ == "__main__":
    asyncio.run(test())
