import asyncio
import os
import sys

# Append the directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from railway_bot import check_trains, init_db

async def test():
    # In order to use check_trains, we might need DB or other things initialized
    # But get_http_session in railway_bot is tied to db? No, just a global
    await init_db()
    res = await check_trains("2900000", "2900790", "2024-05-28")
    print(res)

if __name__ == "__main__":
    asyncio.run(test())
