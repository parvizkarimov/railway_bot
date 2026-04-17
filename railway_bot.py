from urllib.parse import unquote
import asyncio
import aiohttp
import aiosqlite
import logging
import re
import os
import time
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, WebAppInfo
import json

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TOKEN")
ADMIN_ID = 474681690  # Xatoliklar yuboriladigan ID

async def send_error_to_admin(msg):
    """Xatoliklarni adminga yuborish"""
    try:
        await bot.send_message(ADMIN_ID, f"⚠️ *BOT XATOLIGI:*\n\n{msg}", parse_mode="Markdown")
    except:
        logging.error(f"Admin xabar yuborishda xato: {msg}")

# Cookie cache
_cookie_cache = {"cookie": "", "xsrf": "", "updated": None}
COOKIE_TTL = 1500  # 25 daqiqa

async def refresh_cookie():
    """Playwright orqali yangi cookie olish"""
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            await page.goto("https://eticket.railway.uz/uz/home", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)
            await page.goto("https://eticket.railway.uz/uz/pages/trains-page", wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(3000)
            cookies = await context.cookies()
            cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
            xsrf = unquote(next((c["value"] for c in cookies if c["name"] == "XSRF-TOKEN"), ""))
            await browser.close()
            if cookie_str and xsrf:
                _cookie_cache["cookie"] = cookie_str
                _cookie_cache["xsrf"] = xsrf
                _cookie_cache["updated"] = datetime.now()
                logging.info(f"Cookie yangilandi")
                return True
            else:
                await send_error_to_admin("Cookie yoki XSRF token olinmadi. Sayt strukturasi o'zgargan bo'lishi mumkin.")
    except Exception as e:
        err_msg = str(e)
        logging.error(f"Playwright xato: {err_msg}")
        if "timeout" in err_msg.lower():
            await send_error_to_admin("Playwright timeout: Sayt juda sekin ishlayapti yoki IP bloklangan bo'lishi mumkin.")
        else:
            await send_error_to_admin(f"Playwright orqali cookie olishda xato: {err_msg}")
    return False

async def get_cookie(force=False):
    if (not force and _cookie_cache["cookie"] and _cookie_cache["updated"] and
        (datetime.now() - _cookie_cache["updated"]).total_seconds() < COOKIE_TTL):
        return _cookie_cache["cookie"], _cookie_cache["xsrf"]
    await refresh_cookie()
    return _cookie_cache["cookie"], _cookie_cache["xsrf"]

WEBAPP_URL = os.getenv("WEBAPP_URL", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PORT = int(os.getenv("PORT", 8000))

STATIONS = {
    "Toshkent": "2900000", "Samarqand": "2900700", "Buxoro": "2900800",
    "Namangan": "2900940", "Andijon": "2900680", "Qoqon": "2900880",
    "Qarshi": "2900750", "Termiz": "2900255", "Xiva": "2900172",
    "Urgench": "2900790", "Jizzax": "2900720", "Nukus": "2900970",
}

async def check_trains(from_code, to_code, date, _retry=0):
    url = "https://eticket.railway.uz/api/v3/handbook/trains/list"
    cookie, xsrf = await get_cookie()
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "uz-UZ,uz;q=0.9,ru;q=0.8,en;q=0.7",
        "Content-Type": "application/json",
        "Cookie": cookie,
        "X-Xsrf-Token": xsrf,
        "Device-Type": "BROWSER",
        "Origin": "https://eticket.railway.uz",
        "Referer": "https://eticket.railway.uz/uz/pages/trains-page",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }
    payload = {"directions": {"forward": {"date": date, "depStationCode": from_code, "arvStationCode": to_code}}}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=30) as r:
                if r.status == 200:
                    return await r.json(content_type=None)
                elif r.status == 403:
                    await send_error_to_admin(f"❌ IP BLOKLANDI (Status 403). Railway sayti so'rovni rad etdi.")
                elif r.status in (401, 419) and _retry < 2:
                    await get_cookie(force=True)
                    return await check_trains(from_code, to_code, date, _retry=_retry+1)
                else:
                    logging.warning(f"API status xatosi: {r.status}")
    except Exception as e:
        logging.error(f"check_trains xato: {e}")
    return None

def parse_trains(data):
    try: return data.get("data", data).get("directions", {}).get("forward", {}).get("trains", [])
    except: return []

def get_car_price(car):
    price = car.get("price", 0)
    if not price and isinstance(car.get("tariff"), dict):
        price = car.get("tariff", {}).get("price", 0)
    return price

# ---- Database ----
DB_PATH = "bot.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT,
            is_premium INTEGER DEFAULT 0, premium_until TEXT)""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, from_st TEXT, to_st TEXT,
            from_code TEXT, to_code TEXT, date TEXT, 
            check_interval INTEGER DEFAULT 300,
            preferred_seats TEXT DEFAULT '[]',
            max_price INTEGER DEFAULT 0,
            last_checked INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1)""")
        await conn.commit()

async def db(query, params=(), fetch=False):
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(query, params)
        result = await cursor.fetchall() if fetch else None
        await conn.commit()
        return result

# ---- Bot ----
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

@dp.message(Command("start"))
async def cmd_start(msg: types.Message):
    await db("INSERT OR IGNORE INTO users (user_id, username) VALUES (?,?)", (msg.from_user.id, msg.from_user.username))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚂 WebApp orqali kuzatish", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton(text="📋 Kuzatuvlarim", callback_data="my_subs")]
    ])
    await msg.answer("🚂 *Railway Bilet Kuzatuvchi*\n\nBarcha sozlamalar WebApp orqali amalga oshiriladi.", parse_mode="Markdown", reply_markup=kb)

@dp.callback_query(F.data == "my_subs")
async def cb_my_subs(cb: types.CallbackQuery):
    subs = await db("SELECT id,from_st,to_st,date FROM subscriptions WHERE user_id=? AND is_active=1", (cb.from_user.id,), fetch=True)
    if not subs:
        await cb.message.answer("📭 Kuzatuvlar yo'q.")
        return
    text = "📋 *Mening kuzatuvlarim:*\n\n"
    buttons = []
    for s in subs:
        text += f"🚂 {s[1]} → {s[2]} | {s[3]}\n"
        buttons.append([InlineKeyboardButton(text=f"❌ O'chirish {s[1]}→{s[2]}", callback_data=f"del|{s[0]}")])
    await cb.message.answer(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("del|"))
async def del_sub(cb: types.CallbackQuery):
    await db("UPDATE subscriptions SET is_active=0 WHERE id=?", (int(cb.data.split("|")[1]),))
    await cb.answer("✅ O'chirildi")
    await cb.message.edit_text("✅ Kuzatuv o'chirildi.")

# ---- Checker Logic ----
async def checker():
    await asyncio.sleep(10)
    while True:
        try:
            now = int(time.time())
            # Faqat vaqti kelgan va faol kuzatuvlarni olish
            subs = await db("SELECT id, user_id, from_st, to_st, from_code, to_code, date, check_interval, preferred_seats, max_price FROM subscriptions WHERE is_active=1 AND (last_checked + check_interval) <= ?", (now,), fetch=True)
            
            for sub in (subs or []):
                sid, uid, f_st, t_st, f_code, t_code, s_date, s_interval, s_prefs, s_max_p = sub
                
                # Muddatni tekshirish
                if s_date < datetime.now().strftime("%Y-%m-%d"):
                    await db("UPDATE subscriptions SET is_active=0 WHERE id=?", (sid,))
                    continue

                # API so'rovi
                result = await check_trains(f_code, t_code, s_date)
                await db("UPDATE subscriptions SET last_checked=? WHERE id=?", (now, sid))
                
                if not result: continue
                trains = parse_trains(result)
                prefs = json.loads(s_prefs) # ["lower", "upper", "sitting"]
                
                found_text = ""
                for t in trains:
                    match_cars = []
                    total_train_seats = 0
                    for c in t.get("cars", []):
                        seats = c.get("freeSeats", 0)
                        if seats <= 0: continue
                        
                        price = get_car_price(c)
                        if s_max_p > 0 and price > s_max_p: continue
                        
                        p_types = c.get("placeTypes", [])
                        if not p_types:
                            match_cars.append(f"    {c.get('type','?')}: {seats} joy | {price:,} so'm")
                            total_train_seats += seats
                        else:
                            details = []
                            for pt in p_types:
                                pt_name = pt.get("name", "").lower()
                                pt_count = pt.get("count", 0)
                                if pt_count > 0:
                                    if not prefs or pt_name in prefs or (pt_name == "sitting" and c.get("type") == "O'tirish"):
                                        details.append(f"    {pt_name.capitalize()}: {pt_count} joy | {price:,} so'm")
                                        total_train_seats += pt_count
                            if details:
                                match_cars.append("\n".join(details))
                    
                    if match_cars:
                        dep_time = t.get('departureDate', '')
                        arr_time = t.get('arrivalDate', '')
                        found_text += f"✅ *{t.get('brand','Poyezd')}* — {total_train_seats} joy\n" + "\n".join(match_cars) + f"\n🕐 {dep_time} → {arr_time}\n\n"

                if found_text:
                    msg = f"🔔 *Bo'sh joy topildi!*\n🚂 {f_st} → {t_st} ({s_date})\n\n{found_text}👉 https://eticket.railway.uz"
                    try: await bot.send_message(uid, msg, parse_mode="Markdown")
                    except: pass
        except Exception as e:
            logging.error(f"Checker error: {e}")
        await asyncio.sleep(5) # Har 5 soniyada bazani qarab chiqadi

# ---- Web Server ----
async def handle_webapp(request):
    with open("webapp.html", "r", encoding="utf-8") as f: return web.Response(text=f.read(), content_type="text/html")

async def handle_trains_api(request):
    try:
        body = await request.json()
        result = await check_trains(body.get("from"), body.get("to"), body.get("date"))
        return web.json_response({"trains": parse_trains(result) if result else []})
    except: return web.json_response({"trains": []})

async def handle_get_subs(request):
    uid = request.query.get("user_id")
    subs = await db("SELECT id,from_st,to_st,from_code,to_code,date,check_interval,preferred_seats,max_price FROM subscriptions WHERE user_id=? AND is_active=1", (int(uid),), fetch=True)
    res = []
    for s in (subs or []):
        res.append({"id":s[0],"from_st":s[1],"to_st":s[2],"from_code":s[3],"to_code":s[4],"date":s[5],"interval":s[6],"prefs":json.loads(s[7]),"max_price":s[8]})
    return web.json_response({"subs": res})

async def handle_add_sub(request):
    try:
        b = await request.json()
        f_name = next((k for k, v in STATIONS.items() if v == b['from']), b['from'])
        t_name = next((k for k, v in STATIONS.items() if v == b['to']), b['to'])
        # JSON sifatida saqlash
        prefs = json.dumps(b.get("prefs", []))
        await db("INSERT INTO subscriptions (user_id,from_st,to_st,from_code,to_code,date,check_interval,preferred_seats,max_price) VALUES (?,?,?,?,?,?,?,?,?)",
           (int(b['user_id']), f_name, t_name, b['from'], b['to'], b['date'], int(b.get('interval', 300)), prefs, int(b.get('max_price', 0))))
        return web.json_response({"ok": True})
    except Exception as e: return web.json_response({"ok": False, "error": str(e)})

async def handle_del_sub(request):
    b = await request.json()
    await db("UPDATE subscriptions SET is_active=0 WHERE id=?", (int(b.get("id")),))
    return web.json_response({"ok": True})

async def start_webserver():
    app = web.Application()
    app.router.add_get("/", handle_webapp)
    app.router.add_post("/api/trains", handle_trains_api)
    app.router.add_get("/api/subs", handle_get_subs)
    app.router.add_post("/api/subs", handle_add_sub)
    app.router.add_post("/api/subs/delete", handle_del_sub)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()

async def main():
    await init_db()
    await start_webserver()
    await refresh_cookie()
    asyncio.create_task(checker())
    asyncio.create_task(asyncio.sleep(1800)) # Cookie refresher o'rniga loop
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
