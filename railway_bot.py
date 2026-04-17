from urllib.parse import unquote
import asyncio
import aiohttp
import aiosqlite
import logging
import re
import os
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
# Cookie cache
_cookie_cache = {"cookie": "", "xsrf": "", "updated": None}
COOKIE_TTL = 1500  # 25 daqiqa (soniyalarda)

async def refresh_cookie():
    """Playwright orqali yangi cookie olish"""
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
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
                logging.info(f"Cookie yangilandi: {cookie_str[:100]}")
                logging.info(f"XSRF full: {xsrf}")
                return True
    except Exception as e:
        logging.error(f"Playwright xato: {e}")
    return False

async def get_cookie(force=False):
    """Keshlangan cookie qaytarish, muddati o'tgan bo'lsa yangilash"""
    if (not force and _cookie_cache["cookie"] and _cookie_cache["updated"] and
        (datetime.now() - _cookie_cache["updated"]).total_seconds() < COOKIE_TTL):
        logging.debug("Cookie keshdan qaytarildi")
        return _cookie_cache["cookie"], _cookie_cache["xsrf"]
    logging.info("Cookie yangilanmoqda...")
    await refresh_cookie()
    return _cookie_cache["cookie"], _cookie_cache["xsrf"]

WEBAPP_URL = os.getenv("WEBAPP_URL", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHECK_INTERVAL = 300
PORT = int(os.getenv("PORT", 8000))

STATIONS = {
    "Toshkent": "2900000",
    "Samarqand": "2900700",
    "Buxoro": "2900800",
    "Namangan": "2900940",
    "Andijon": "2900680",
    "Qoqon": "2900880",
    "Qarshi": "2900750",
    "Termiz": "2900255",
    "Xiva": "2900172",
    "Urgench": "2900790",
    "Jizzax": "2900720",
    "Nukus": "2900970",
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
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    payload = {"directions": {"forward": {
        "date": date, "depStationCode": from_code, "arvStationCode": to_code
    }}}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=30)) as r:
                logging.info(f"API status: {r.status}")
                logging.info(f"Payload: {json.dumps(payload)}")
                logging.info(f"Cookie uzunligi: {len(headers['Cookie'])}, XSRF: {headers['X-Xsrf-Token']}")
                if r.status == 200:
                    return await r.json(content_type=None)
                elif r.status in (401, 419) and _retry < 3:
                    logging.warning(f"Cookie eskirgan (status {r.status}), yangilanmoqda... (urinish {_retry + 1}/3)")
                    await get_cookie(force=True)
                    await asyncio.sleep(2 ** (_retry + 1))
                    return await check_trains(from_code, to_code, date, _retry=_retry + 1)
                else:
                    text = await r.text()
                    logging.error(f"API xato: {r.status} - {text[:300]}")
    except aiohttp.ClientError as e:
        if _retry < 3:
            logging.warning(f"Tarmoq xatosi, qayta urinish... ({_retry + 1}/3): {e}")
            await asyncio.sleep(2 ** (_retry + 1))
            return await check_trains(from_code, to_code, date, _retry=_retry + 1)
        logging.error(f"Request xato (3 urinishdan keyin): {e}")
    except Exception as e:
        logging.error(f"Request xato: {e}")
    return None

def parse_trains(data):
    trains = []
    try:
        forward = data.get("data", data).get("directions", {}).get("forward", {})
        for train in forward.get("trains", []):
            trains.append(train)
    except Exception as e:
        logging.error(f"Parse xato: {e}")
    return trains

def format_price(price):
    """Narxni formatlash: 120000 -> '120 000 so'm'"""
    if not price:
        return ""
    try:
        return f" — {int(price):,} so'm".replace(",", " ")
    except (ValueError, TypeError):
        return ""

def get_car_price(car):
    """Vagon narxini olish (turli API formatlarini qo'llab-quvvatlash)"""
    price = car.get("price", 0)
    if not price and isinstance(car.get("tariff"), dict):
        price = car.get("tariff", {}).get("price", 0)
    return price

def format_train_details(trains):
    """Poyezd ma'lumotlarini vagon turlari va narxlari bilan formatlash"""
    text = ""
    for t in trains:
        cars = t.get("cars", [])
        total = sum(c.get("freeSeats", 0) for c in cars)
        if total > 0:
            text += f"✅ *{t.get('brand', '?')}* — {total} joy\n"
            for c in cars:
                seats = c.get("freeSeats", 0)
                if seats > 0:
                    price = get_car_price(c)
                    text += f"    {c.get('type', '?')}: {seats} joy{format_price(price)}\n"
            text += f"🕐 {t.get('departureDate', '')} → {t.get('arrivalDate', '')}\n\n"
        else:
            text += f"❌ *{t.get('brand', '?')}* — joy yo'q\n"
    return text

# ---- Database (aiosqlite) ----
DB_PATH = "bot.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT,
            is_premium INTEGER DEFAULT 0, premium_until TEXT)""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, from_st TEXT, to_st TEXT,
            from_code TEXT, to_code TEXT, date TEXT, is_active INTEGER DEFAULT 1)""")
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

class Form(StatesGroup):
    from_st = State()
    to_st = State()
    date = State()

def st_kb(exclude=None):
    buttons = []
    row = []
    for name in STATIONS:
        if name != exclude:
            row.append(InlineKeyboardButton(text=name, callback_data=f"st|{name}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.message(Command("start"))
async def cmd_start(msg: types.Message):
    await db("INSERT OR IGNORE INTO users (user_id, username) VALUES (?,?)",
       (msg.from_user.id, msg.from_user.username))

    buttons = []
    if WEBAPP_URL:
        buttons.append([InlineKeyboardButton(
            text="🚂 Bilet kuzatuvchi",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )])
    buttons.append([InlineKeyboardButton(text="📋 Kuzatuvlarim", callback_data="my_subs")])

    await msg.answer(
        "🚂 *Temir Yo'l Bilet Kuzatuvchi*\n\n"
        "Bot poyezd biletlarini kuzatadi!\n\n"
        "• 1-10 ta reys — *bepul*\n"
        "• 10+ reys — 50⭐ Stars / 3 kun\n\n"
        "/kuzat — yangi reys\n"
        "/mening — kuzatuvlarim\n"
        "/test — ulanishni tekshirish",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.message(Command("test"))
async def cmd_test(msg: types.Message):
    await msg.answer("🔍 Cookie olinmoqda...")
    cookie, xsrf = await get_cookie()
    await msg.answer(
        f"Cookie: {len(cookie)} belgi\n"
        f"XSRF: {xsrf[:20] if xsrf else 'Yoq'}"
    )
    result = await check_trains("2900000", "2900700", (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"))
    if result:
        trains = parse_trains(result)
        await msg.answer(f"✅ API ishlayapti!\n🚂 Poyezdlar: {len(trains)} ta")
    else:
        await msg.answer("❌ API ishlamadi")

@dp.message(Command("kuzat"))
async def cmd_watch(msg: types.Message, state: FSMContext):
    user_id = msg.from_user.id
    count = (await db("SELECT COUNT(*) FROM subscriptions WHERE user_id=? AND is_active=1",
               (user_id,), fetch=True))[0][0]

    users = await db("SELECT is_premium, premium_until FROM users WHERE user_id=?", (user_id,), fetch=True)
    is_premium = False
    if users and users[0][0]:
        if users[0][1] and datetime.fromisoformat(users[0][1]) > datetime.now():
            is_premium = True

    if count >= 10 and not is_premium:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⭐ 50 Stars — 3 kunlik obuna", callback_data="buy_premium")
        ]])
        await msg.answer(f"⭐ *Premium kerak!*\n\n{count} ta reys kuzatyapsiz.\nBepul limit: 10 ta",
                        parse_mode="Markdown", reply_markup=kb)
        return
    await msg.answer("🚉 *Qayerdan?*", parse_mode="Markdown", reply_markup=st_kb())
    await state.set_state(Form.from_st)

@dp.callback_query(F.data == "my_subs")
async def cb_my_subs(cb: types.CallbackQuery):
    await cb.answer()
    await show_my_subs(cb.message, cb.from_user.id)

@dp.message(Command("mening"))
async def cmd_my(msg: types.Message):
    await show_my_subs(msg, msg.from_user.id)

async def show_my_subs(msg, user_id):
    subs = await db("SELECT id,from_st,to_st,date FROM subscriptions WHERE user_id=? AND is_active=1",
              (user_id,), fetch=True)
    if not subs:
        await msg.answer("📭 Kuzatuvlar yo'q. /kuzat bilan boshlang!")
        return
    text = "📋 *Mening kuzatuvlarim:*\n\n"
    buttons = []
    for s in subs:
        text += f"🚂 {s[1]} → {s[2]} | {s[3]}\n"
        buttons.append([InlineKeyboardButton(
            text=f"❌ {s[1]}→{s[2]} ({s[3]})", callback_data=f"del|{s[0]}")])
    await msg.answer(text, parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("st|"), Form.from_st)
async def got_from(cb: types.CallbackQuery, state: FSMContext):
    st = cb.data.split("|")[1]
    await state.update_data(from_st=st, from_code=STATIONS[st])
    await cb.message.edit_text(f"✅ Qayerdan: *{st}*\n\n🚉 *Qayerga?*",
                               parse_mode="Markdown", reply_markup=st_kb(exclude=st))
    await state.set_state(Form.to_st)

@dp.callback_query(F.data.startswith("st|"), Form.to_st)
async def got_to(cb: types.CallbackQuery, state: FSMContext):
    st = cb.data.split("|")[1]
    data = await state.get_data()
    await state.update_data(to_st=st, to_code=STATIONS[st])
    await cb.message.edit_text(
        f"✅ Qayerdan: *{data['from_st']}*\n✅ Qayerga: *{st}*\n\n📅 *Sanani yuboring* (masalan: 2026-05-01)",
        parse_mode="Markdown")
    await state.set_state(Form.date)

@dp.message(Form.date)
async def got_date(msg: types.Message, state: FSMContext):
    date = msg.text.strip()
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        await msg.answer("❌ Format noto'g'ri! Masalan: *2026-05-01*", parse_mode="Markdown")
        return
    data = await state.get_data()
    await state.clear()
    await msg.answer("🔍 Tekshirilmoqda...")
    result = await check_trains(data["from_code"], data["to_code"], date)
    await db("INSERT INTO subscriptions (user_id,from_st,to_st,from_code,to_code,date) VALUES (?,?,?,?,?,?)",
       (msg.from_user.id, data["from_st"], data["to_st"],
        data["from_code"], data["to_code"], date))
    if not result:
        await msg.answer("⚠️ Hozir ma'lumot olinmadi, lekin kuzatuv saqlandi.\n"
                        f"🔔 Har {CHECK_INTERVAL//60} daqiqada tekshirib turaman!")
        return
    trains = parse_trains(result)
    text = f"🚂 *{data['from_st']} → {data['to_st']}* ({date})\n\n"
    if trains:
        text += format_train_details(trains)
    else:
        text += "Hozircha poyezd yo'q.\n"
    text += f"\n🔔 Har {CHECK_INTERVAL//60} daqiqada tekshiraman!"
    await msg.answer(text, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("del|"))
async def del_sub(cb: types.CallbackQuery):
    await db("UPDATE subscriptions SET is_active=0 WHERE id=?", (int(cb.data.split("|")[1]),))
    await cb.answer("✅ O'chirildi!")
    await cb.message.edit_text("✅ Kuzatuv o'chirildi.")

@dp.message(F.web_app_data)
async def web_app_data(msg: types.Message):
    try:
        data = json.loads(msg.web_app_data.data)
        if data.get("action") == "watch":
            from_code = data["from"]
            to_code = data["to"]
            date = data["date"]
            from_name = next((k for k, v in STATIONS.items() if v == from_code), from_code)
            to_name = next((k for k, v in STATIONS.items() if v == to_code), to_code)
            await db("INSERT INTO subscriptions (user_id,from_st,to_st,from_code,to_code,date) VALUES (?,?,?,?,?,?)",
               (msg.from_user.id, from_name, to_name, from_code, to_code, date))
            await msg.answer(f"✅ Kuzatuvga qo'shildi!\n🚂 {from_name} → {to_name} | {date}\n🔔 Har 5 daqiqada tekshiraman!")
    except Exception as e:
        logging.error(f"WebApp data xato: {e}")

@dp.callback_query(F.data == "buy_premium")
async def buy(cb: types.CallbackQuery):
    await bot.send_invoice(
        chat_id=cb.from_user.id, title="⭐ 3 Kunlik Premium",
        description="10+ reys kuzatish. 3 kunlik muddat.", payload="premium_3days",
        currency="XTR", prices=[LabeledPrice(label="3 kunlik", amount=50)],
    )

@dp.pre_checkout_query()
async def pre_checkout(pcq: types.PreCheckoutQuery):
    await pcq.answer(ok=True)

@dp.message(F.successful_payment)
async def paid(msg: types.Message):
    until = (datetime.now() + timedelta(days=3)).isoformat()
    await db("UPDATE users SET is_premium=1, premium_until=? WHERE user_id=?", (until, msg.from_user.id))
    await msg.answer("🎉 *Premium faollashtirildi!*", parse_mode="Markdown")


@dp.message(Command("setcookie"))
async def cmd_setcookie(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        await msg.answer("❌ Ruxsat yo'q!")
        return
    parts = msg.text.split(" ", 1)
    if len(parts) < 2:
        await msg.answer("Format: /setcookie COOKIE_QIYMAT")
        return
    cookie_text = parts[1].strip()
    m = re.search(r'XSRF-TOKEN=([^;]+)', cookie_text)
    xsrf_match = unquote(m.group(1)) if m else None
    _cookie_cache["cookie"] = cookie_text
    _cookie_cache["xsrf"] = xsrf_match or ""
    _cookie_cache["updated"] = datetime.now()
    await msg.answer(f"✅ Cookie yangilandi!\nUzunlik: {len(cookie_text)} belgi\nXSRF: {xsrf_match[:20] if xsrf_match else 'Topilmadi'}")

async def checker():
    await asyncio.sleep(60)
    while True:
        try:
            subs = await db("SELECT id,user_id,from_st,to_st,from_code,to_code,date FROM subscriptions WHERE is_active=1", fetch=True)
            for sub in (subs or []):
                sid, uid, from_st, to_st, from_code, to_code, date = sub
                if date < datetime.now().strftime("%Y-%m-%d"):
                    await db("UPDATE subscriptions SET is_active=0 WHERE id=?", (sid,))
                    continue
                result = await check_trains(from_code, to_code, date)
                if not result:
                    continue
                trains = parse_trains(result)
                available = [t for t in trains if sum(c.get("freeSeats", 0) for c in t.get("cars", [])) > 0]
                if available:
                    text = f"🔔 *Bo'sh joy topildi!*\n🚂 *{from_st} → {to_st}* ({date})\n\n"
                    text += format_train_details(available)
                    text += "\n👉 https://eticket.railway.uz"
                    try:
                        await bot.send_message(uid, text, parse_mode="Markdown")
                    except Exception as e:
                        logging.error(f"Xabar xato: {e}")
        except Exception as e:
            logging.error(f"Checker xato: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

# ---- Web server for WebApp ----
async def handle_webapp(request):
    with open("webapp.html", "r", encoding="utf-8") as f:
        content = f.read()
    return web.Response(text=content, content_type="text/html")

async def handle_trains_api(request):
    try:
        body = await request.json()
        from_code = body.get("from")
        to_code = body.get("to")
        date = body.get("date")
        result = await check_trains(from_code, to_code, date)
        if result:
            trains = parse_trains(result)
            return web.json_response({"trains": trains})
        return web.json_response({"trains": []})
    except Exception as e:
        return web.json_response({"trains": [], "error": str(e)})

async def handle_get_subs(request):
    """WebApp uchun kuzatuvlarni olish"""
    try:
        user_id = request.query.get("user_id")
        if not user_id:
            return web.json_response({"subs": [], "error": "user_id kerak"})
        subs = await db(
            "SELECT id,from_st,to_st,from_code,to_code,date FROM subscriptions WHERE user_id=? AND is_active=1",
            (int(user_id),), fetch=True)
        result = []
        for s in (subs or []):
            result.append({"id": s[0], "from_st": s[1], "to_st": s[2],
                          "from_code": s[3], "to_code": s[4], "date": s[5]})
        return web.json_response({"subs": result})
    except Exception as e:
        return web.json_response({"subs": [], "error": str(e)})

async def handle_add_sub(request):
    """WebApp orqali kuzatuv qo'shish"""
    try:
        body = await request.json()
        user_id = body.get("user_id")
        from_code = body.get("from")
        to_code = body.get("to")
        date = body.get("date")
        if not all([user_id, from_code, to_code, date]):
            return web.json_response({"ok": False, "error": "Barcha maydonlar kerak"})
        from_name = next((k for k, v in STATIONS.items() if v == from_code), from_code)
        to_name = next((k for k, v in STATIONS.items() if v == to_code), to_code)
        await db("INSERT INTO subscriptions (user_id,from_st,to_st,from_code,to_code,date) VALUES (?,?,?,?,?,?)",
           (int(user_id), from_name, to_name, from_code, to_code, date))
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def handle_del_sub(request):
    """WebApp orqali kuzatuvni o'chirish"""
    try:
        body = await request.json()
        sub_id = body.get("id")
        if not sub_id:
            return web.json_response({"ok": False, "error": "id kerak"})
        await db("UPDATE subscriptions SET is_active=0 WHERE id=?", (int(sub_id),))
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def start_webserver():
    app = web.Application()
    app.router.add_get("/", handle_webapp)
    app.router.add_post("/api/trains", handle_trains_api)
    app.router.add_get("/api/subs", handle_get_subs)
    app.router.add_post("/api/subs", handle_add_sub)
    app.router.add_post("/api/subs/delete", handle_del_sub)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logging.info(f"Web server port {PORT} da ishga tushdi!")

async def cookie_refresher():
    """Har 30 daqiqada cookie yangilash"""
    while True:
        await refresh_cookie()
        await asyncio.sleep(1800)

async def main():
    await init_db()
    await start_webserver()
    await refresh_cookie()
    asyncio.create_task(checker())
    asyncio.create_task(cookie_refresher())
    logging.info("Bot ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
