from urllib.parse import unquote
import asyncio
import aiohttp
import random
from playwright.async_api import async_playwright
import aiosqlite
import logging
import os
import time
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, WebAppInfo
import json

# ---- Configuration ----
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip() or None
ADMIN_ID = int(os.getenv("ADMIN_ID", "0").strip() or 0)
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
DB_PATH = os.getenv("DB_PATH", "bot.db")
PORT = int(os.getenv("PORT", 8080))

if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN topilmadi! Railway Variables bo'limini tekshiring.")
    exit(1)

async def send_error_to_admin(msg):
    """Xatoliklarni adminga yuborish"""
    try:
        await bot.send_message(ADMIN_ID, f"⚠️ *BOT XATOLIGI:*\n\n{msg}", parse_mode="Markdown")
    except:
        logging.error(f"Admin xabar yuborishda xato: {msg}")

# Cookie cache
_cookie_cache = {"cookie": "", "xsrf": "", "updated": None}
COOKIE_TTL = 1500  # 25 daqiqa

# Barcha stansiyalar
STATIONS = {
    "Toshkent": "2900000", "Samarqand": "2900700", "Buxoro": "2900800",
    "Namangan": "2900940", "Andijon": "2900680", "Qoqon": "2900880",
    "Qarshi": "2900750", "Termiz": "2900255", "Xiva": "2900172",
    "Urgench": "2900790", "Jizzax": "2900720", "Nukus": "2900970",
}

# Persistent HTTP session (har API chaqiriqda yangi ulanish ochilmaydi)
_http_session: aiohttp.ClientSession | None = None

async def get_http_session() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession()
    return _http_session

# webapp.html ni xotirada saqlash (diskdan har safar o'qilmaydi)
_webapp_cache: str | None = None

def get_webapp_html() -> str:
    global _webapp_cache
    if _webapp_cache is None:
        with open("webapp.html", "r", encoding="utf-8") as f:
            _webapp_cache = f.read()
    return _webapp_cache

async def cookie_refresher():
    """Orqa fonda cookielarni har 20 minutda yangilab turish"""
    while True:
        try:
            await refresh_cookie()
            logging.info("Fon rejimida cookie yangilandi")
        except Exception as e:
            logging.error(f"Fon rejimida cookie yangilashda xato: {e}")
        await asyncio.sleep(1200) # 20 daqiqa

async def refresh_cookie():
    """Playwright orqali yangi cookie olish (Optimallashtirilgan)"""
    for attempt in range(1, 4):
        browser = None
        try:
            logging.info(f"Cookie yangilash urinishi: {attempt}")
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=[
                    "--no-sandbox", 
                    "--disable-dev-shm-usage",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled", # Anti-bot bypass
                    "--no-first-run",
                    "--no-zygote",
                    "--single-process"
                ])
                
                # Turli xil User-Agentlar
                user_agents = [
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ]
                
                context = await browser.new_context(
                    user_agent=random.choice(user_agents),
                    viewport={'width': 1280, 'height': 720}
                )
                page = await context.new_page()
                
                # Sarlavhalarni qo'shish
                await page.set_extra_http_headers({
                    "Accept-Language": "uz-UZ,uz;q=0.9,ru;q=0.8,en;q=0.7",
                    "Upgrade-Insecure-Requests": "1"
                })

                # Timeoutni bo'lib ishlatamiz. networkidle o'rniga domcontentloaded va keyin kutish
                try:
                    response = await page.goto("https://eticket.railway.uz/uz/pages/trains-page", 
                                             wait_until="domcontentloaded", 
                                             timeout=40000)
                    
                    if response and response.status == 403:
                        logging.warning(f"Urinish {attempt}: 403 Forbidden. IP bloklangan bo'lishi mumkin.")
                        if attempt == 3:
                            await send_error_to_admin("Playwright: 403 Forbidden (Blok). IP manzilingiz Railway tomonidan bloklangan.")
                        await browser.close()
                        await asyncio.sleep(random.uniform(5, 10))
                        continue

                    # Sahifa yuklanishini biroz kutamiz (networkidle har doim ham ishlamasligi mumkin)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=15000)
                    except:
                        logging.warning(f"Urinish {attempt}: Networkidle timeout, lekin davom etamiz...")

                except Exception as e:
                    logging.error(f"Urinish {attempt} goto xato: {e}")
                    await browser.close()
                    await asyncio.sleep(2)
                    continue

                await asyncio.sleep(random.uniform(3, 7)) # Real userdek kutish
                
                cookies = await context.cookies()
                cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                xsrf = unquote(next((c["value"] for c in cookies if c["name"] == "XSRF-TOKEN"), ""))
                
                await browser.close()

                if cookie_str and xsrf:
                    _cookie_cache["cookie"] = cookie_str
                    _cookie_cache["xsrf"] = xsrf
                    _cookie_cache["updated"] = datetime.now()
                    logging.info(f"Cookie muvaffaqiyatli yangilandi (Urinish {attempt})")
                    return True
                else:
                    logging.warning(f"Urinish {attempt}: Cookie yoki XSRF topilmadi.")
                    if attempt == 3:
                        await send_error_to_admin("Cookie yoki XSRF token olinmadi. Sayt strukturasi o'zgargan bo'lishi mumkin.")
                    await asyncio.sleep(2)
                    
        except Exception as e:
            logging.error(f"Playwright fatal error (Urinish {attempt}): {e}")
            if browser:
                try: await browser.close()
                except: pass
            await asyncio.sleep(2)

    return False

async def get_cookie(force=False):
    if (not force and _cookie_cache["cookie"] and _cookie_cache["updated"] and
        (datetime.now() - _cookie_cache["updated"]).total_seconds() < COOKIE_TTL):
        return _cookie_cache["cookie"], _cookie_cache["xsrf"]
    await refresh_cookie()
    return _cookie_cache["cookie"], _cookie_cache["xsrf"]


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
    payload = {"directions": {"forward": {"date": date, "depStationCode": from_code, "arvStationCode": to_code}}}
    try:
        session = await get_http_session()
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as r:
            if r.status == 200:
                return await r.json(content_type=None)
            elif r.status == 403:
                logging.warning("API: 403 Forbidden — IP bloklangan yoki cookie eskirgan")
                await get_cookie(force=True)
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
    # API'ning turli versiyalarida narx har xil joyda keladi
    # 1. To'g'ridan-to'g'ri 'price'
    price = car.get("price", 0)
    
    # 2. 'tariff' obyekti ichida (eng ko'p uchraydigan holat)
    if not price and isinstance(car.get("tariff"), (dict, int, float)):
        t = car.get("tariff")
        if isinstance(t, dict):
            # 'price' yoki 'tariff' kaliti ostida bo'lishi mumkin
            price = t.get("price") or t.get("tariff") or 0
        else:
            price = t
            
    # 3. 'tariffs' ro'yxati ichida
    if not price:
        tariffs = car.get("tariffs", [])
        if tariffs and isinstance(tariffs, list):
            price = tariffs[0].get("price") or tariffs[0].get("tariff") or 0
            
    # 4. 'categories' ichida
    if not price:
        cats = car.get("categories", [])
        if cats and isinstance(cats, list):
            price = cats[0].get("price") or cats[0].get("tariff") or 0

    return int(price) if price else 0

def get_seat_details(car):
    # O'rinlarni seatDetail dan olish
    sd = car.get("seatDetail", {})
    details = []
    if sd.get("down", 0) > 0: details.append({"name": "lower", "count": sd["down"]})
    if sd.get("up", 0) > 0: details.append({"name": "upper", "count": sd["up"]})
    if sd.get("lateralDn", 0) > 0: details.append({"name": "side_lower", "count": sd["lateralDn"]})
    if sd.get("lateralUp", 0) > 0: details.append({"name": "side_upper", "count": sd["lateralUp"]})
    return details

def format_pt_name(name):
    names = {
        "lower": "Pastki",
        "upper": "Tepadagi",
        "side_lower": "Yon pastki",
        "side_upper": "Yon tepa",
        "sitting": "O'tirish"
    }
    return names.get(name.lower(), name.capitalize())

# ---- Database ----
async def init_db():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT,
            coins INTEGER DEFAULT 0,
            is_premium INTEGER DEFAULT 0, premium_until TEXT)""")
        # Eski bazalarga full_name qo'shish
        try: await conn.execute("ALTER TABLE users ADD COLUMN full_name TEXT");
        except: pass
        await conn.execute("""CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, from_st TEXT, to_st TEXT,
            from_code TEXT, to_code TEXT, date TEXT, 
            train_num TEXT,
            check_interval INTEGER DEFAULT 300,
            preferred_seats TEXT DEFAULT '[]',
            max_price INTEGER DEFAULT 0,
            last_checked INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1)""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS support_chat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            sender TEXT,
            message TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        # Eski bazalarni yangilash (agar train_num bo'lmasa)
        try: await conn.execute("ALTER TABLE subscriptions ADD COLUMN train_num TEXT");
        except: pass
        await conn.execute("""CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            train_num TEXT,
            train_brand TEXT,
            from_st TEXT,
            to_st TEXT,
            date TEXT,
            passenger_name TEXT,
            passenger_passport TEXT,
            passenger_birth TEXT,
            status TEXT DEFAULT 'pending',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        # Profil ustunlari
        try: await conn.execute("ALTER TABLE users ADD COLUMN p_name TEXT")
        except: pass
        try: await conn.execute("ALTER TABLE users ADD COLUMN p_passport TEXT")
        except: pass
        try: await conn.execute("ALTER TABLE users ADD COLUMN p_birth TEXT")
        except: pass
        # Auto-book ustuni
        try: await conn.execute("ALTER TABLE subscriptions ADD COLUMN auto_book INTEGER DEFAULT 0")
        except: pass
        # Login/Parol ustunlari
        try: await conn.execute("ALTER TABLE users ADD COLUMN r_login TEXT")
        except: pass
        try: await conn.execute("ALTER TABLE users ADD COLUMN r_password TEXT")
        except: pass
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

@dp.message(F.reply_to_message & (F.from_user.id == ADMIN_ID))
async def admin_reply_handler(message: types.Message):
    orig = message.reply_to_message.text or message.reply_to_message.caption
    if not orig or "🆔 ID:" not in orig: return
    
    try:
        # ID ni xabardan ajratib olish
        target_uid = int(orig.split("🆔 ID:")[1].split("\n")[0].strip())
        reply_text = message.text
        
        # Bazaga saqlash
        await db("INSERT INTO support_chat (user_id, sender, message) VALUES (?, 'admin', ?)", (target_uid, reply_text))
        
        # Foydalanuvchiga bot orqali yuborish
        user_msg = f"🎧 <b>Support xabari:</b>\n\n{reply_text}"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Chatni ochish", web_app=WebAppInfo(url=f"{WEBAPP_URL}#support"))]
        ])
        await bot.send_message(target_uid, user_msg, parse_mode="HTML", reply_markup=kb)
        await message.answer(f"✅ Xabar yuborildi (ID: {target_uid})")
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")

@dp.message(Command("start"))
async def cmd_start(msg: types.Message):
    await db("INSERT INTO users (user_id, username, full_name) VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, full_name=excluded.full_name", 
             (msg.from_user.id, msg.from_user.username, msg.from_user.full_name))
    user = await db("SELECT coins FROM users WHERE user_id=?", (msg.from_user.id,), fetch=True)
    coins = user[0][0] if user else 0
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚂 WebApp orqali kuzatish", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton(text="📋 Kuzatuvlarim", callback_data="my_subs"), InlineKeyboardButton(text="💰 Tangalar", callback_data="buy_coins")]
    ])
    await msg.answer(f"🚂 *Railway Bilet Kuzatuvchi*\n\n💰 Balansingiz: *{coins}* ⭐\n\nLimit: 2 ta bepul kuzatuv. Qo'shimcha kuzatuv uchun 1 ta ⭐ (Yulduz) kerak.", parse_mode="Markdown", reply_markup=kb)

@dp.callback_query(F.data == "buy_coins")
@dp.message(Command("stars"))
async def cmd_buy_coins(event):
    if isinstance(event, types.CallbackQuery):
        try: await event.answer()
        except: pass
    msg = event if isinstance(event, types.Message) else event.message
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ 1 ta Yulduz", callback_data="pay|1|1")],
        [InlineKeyboardButton(text="⭐ 5 ta Yulduz", callback_data="pay|5|5")],
        [InlineKeyboardButton(text="⭐ 10 ta Yulduz", callback_data="pay|10|10")]
    ])
    await msg.answer("⭐ *Yulduzlar sotib olish*\n\n2 tadan ko'p kuzatuv qo'shish uchun Yulduzlar kerak bo'ladi.", parse_mode="Markdown", reply_markup=kb)

@dp.callback_query(F.data.startswith("pay|"))
async def process_pay(cb: types.CallbackQuery):
    try: await cb.answer()
    except: pass
    _, count, price = cb.data.split("|")
    await cb.message.answer_invoice(
        title=f"{count} ta Yulduz",
        description=f"Railway bot uchun {count} ta kuzatuv yulduzi",
        payload=f"coins_{count}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Stars", amount=int(price))]
    )

@dp.pre_checkout_query()
async def pre_checkout_handler(query: types.PreCheckoutQuery):
    await query.answer(ok=True)

@dp.message(F.successful_payment)
async def success_payment_handler(msg: types.Message):
    days = int(msg.successful_payment.invoice_payload.split("_")[1])
    amount = msg.successful_payment.total_amount
    
    # Premium muddatni hisoblash
    user = await db("SELECT premium_until FROM users WHERE user_id=?", (msg.from_user.id,), fetch=True)
    current_until = None
    if user and user[0][0]:
        try:
            current_until = datetime.fromisoformat(user[0][0])
        except: pass
    
    start_date = current_until if (current_until and current_until > datetime.now()) else datetime.now()
    new_until = (start_date + timedelta(days=days)).isoformat()
    
    await db("UPDATE users SET premium_until = ? WHERE user_id = ?", (new_until, msg.from_user.id))
    
    await msg.answer(f"✅ Tabriklaymiz! Premium obunangiz {days} kunga uzaytirildi.\n📅 Muddat: {new_until[:10]}")
    
    admin_msg = (f"💰 *Yangi to'lov (Premium)!*\n\n"
                 f"👤 Kimdan: {msg.from_user.full_name} (@{msg.from_user.username})\n"
                 f"⭐ Miqdori: {amount} yulduz\n"
                 f"📅 Yangi muddat: {new_until[:10]}")
    await send_error_to_admin(admin_msg)

@dp.message(Command("users"))
async def cmd_admin_users(msg: types.Message):
    logging.info(f"Admin command call: /users from {msg.from_user.id}")
    if msg.from_user.id != ADMIN_ID:
        return await msg.answer(f"❌ Siz admin emassiz.\nID: `{msg.from_user.id}`\nAdmin ID: `{ADMIN_ID}`")
    
    users = await db("""
        SELECT u.user_id, u.username, u.premium_until, 
        (SELECT COUNT(*) FROM subscriptions s WHERE s.user_id = u.user_id AND s.is_active = 1) as sub_count,
        u.full_name
        FROM users u
    """, fetch=True)
    if not users:
        return await msg.answer("Foydalanuvchilar topilmadi.")
    
    total = len(users)
    text = f"<b>👥 Jami foydalanuvchilar:</b> {total}\n\n"
    
    for u_id, u_username, p_until, sub_count, u_full_name in users[:50]:
        status = "Oddiy"
        if p_until:
            try:
                if datetime.fromisoformat(p_until) > datetime.now():
                    status = f"✅ Premium ({p_until[:10]})"
                else:
                    status = f"❌ Muddati o'tgan ({p_until[:10]})"
            except: pass
        
        name = u_full_name if u_full_name else "Foydalanuvchi"
        name = name.replace("<", "&lt;").replace(">", "&gt;")
        user_link = f" @{u_username}" if u_username else ""
        
        text += f"👤 {name}{user_link} (<code>{u_id}</code>) — {status} | 🔔 {sub_count} ta\n"
    
    if total > 50:
        text += f"\n... va yana {total-50} ta foydalanuvchi."
        
    await msg.answer(text, parse_mode="HTML")

@dp.message(Command("send"))
async def cmd_broadcast(msg: types.Message):
    """Barcha foydalanuvchilarga xabar yuborish (Faqat Admin)"""
    if msg.from_user.id != ADMIN_ID:
        return
    
    # Buyruqdan keyingi matnni olish: /send Matn...
    text = msg.text.replace("/send", "", 1).strip()
    if not text:
        return await msg.answer("❌ Xabar matnini yozing. Masalan: `/send Salom barchaga!`", parse_mode="Markdown")
    
    users = await db("SELECT user_id FROM users", fetch=True)
    if not users:
        return await msg.answer("Foydalanuvchilar topilmadi.")
    
    count = 0
    errors = 0
    status_msg = await msg.answer(f"⏳ Xabar yuborilmoqda... (Jami: {len(users)})")
    
    for user in users:
        try:
            await bot.send_message(user[0], text, parse_mode="HTML")
            count += 1
            # Bot bloklanib qolmasligi uchun kichik pauza (har 20 xabarda)
            if count % 20 == 0:
                await asyncio.sleep(0.5)
        except Exception as e:
            errors += 1
            logging.error(f"Broadcast error for {user[0]}: {e}")
            
    await status_msg.edit_text(f"✅ Xabar yuborildi!\n\n🚀 Muvaffaqiyatli: {count}\n❌ Xatolik (bloklaganlar): {errors}")

@dp.callback_query(F.data == "my_subs")
async def cb_my_subs(cb: types.CallbackQuery):
    try: await cb.answer()
    except: pass
    subs = await db("SELECT id,from_st,to_st,date FROM subscriptions WHERE user_id=? AND is_active=1", (cb.from_user.id,), fetch=True)
    if not subs:
        await cb.message.answer("📭 Kuzatuvlar yo'q.")
        return
    text = "📋 *Mening kuzatuvlarim:*\n\n"
    buttons = []
    for s in subs:
        text += f"🚂 {s[1]} → {s[2]} | {s[3]}\n"
        buttons.append([
            InlineKeyboardButton(text=f"⏱ Vaqt: {s[1]}→{s[2]}", callback_data=f"edit_int|{s[0]}"),
            InlineKeyboardButton(text=f"❌ O'chirish", callback_data=f"del|{s[0]}")
        ])
    await cb.message.answer(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("edit_int|"))
async def cb_edit_int_menu(cb: types.CallbackQuery):
    try: await cb.answer()
    except: pass
    sid = cb.data.split("|")[1]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="15 soniya ⭐", callback_data=f"set_int|{sid}|15")],
        [InlineKeyboardButton(text="30 soniya ⭐", callback_data=f"set_int|{sid}|30")],
        [InlineKeyboardButton(text="60 soniya", callback_data=f"set_int|{sid}|60")],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="my_subs")]
    ])
    await cb.message.edit_text("⏱ Yangi tekshirish intervalini tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("set_int|"))
async def cb_set_int(cb: types.CallbackQuery):
    try: await cb.answer()
    except: pass
    _, sid, interval = cb.data.split("|")
    interval = int(interval)
    
    # Premium tekshiruvi
    if interval < 60:
        user = await db("SELECT premium_until FROM users WHERE user_id=?", (cb.from_user.id,), fetch=True)
        is_premium = False
        if user and user[0][0]:
            try: is_premium = datetime.fromisoformat(user[0][0]) > datetime.now()
            except: pass
        if not is_premium:
            return await cb.message.answer("❌ 15s va 30s intervallar faqat Premium userlar uchun. Obunani bot boshida sotib olishingiz mumkin.")

    await db("UPDATE subscriptions SET check_interval=? WHERE id=?", (interval, int(sid)))
    await cb.message.edit_text(f"✅ Kuzatuv vaqti {interval} soniyaga o'zgartirildi.")

@dp.callback_query(F.data.startswith("del|"))
async def del_sub(cb: types.CallbackQuery):
    try: await cb.answer()
    except: pass
    await db("UPDATE subscriptions SET is_active=0 WHERE id=?", (int(cb.data.split("|")[1]),))
    await cb.message.edit_text("✅ Kuzatuv o'chirildi.")

# ---- Checker Logic ----
async def process_subscription(sub, now):
    sid, uid, f_st, t_st, f_code, t_code, s_date, s_interval, s_prefs, s_max_p, s_train_num = sub
    logging.info(f"Checking sub {sid} for user {uid} ({f_st}->{t_st}, {s_date}, reys: {s_train_num})")
    
    # API so'rovi
    result = await check_trains(f_code, t_code, s_date)
    await db("UPDATE subscriptions SET last_checked=? WHERE id=?", (now, sid))
    
    if not result:
        logging.warning(f"Sub {sid}: API dan javob kelmadi")
        return
        
    trains = parse_trains(result)
    logging.info(f"Sub {sid}: API dan {len(trains)} ta poyezd keldi")
    
    if s_train_num:
        trains = [t for t in trains if str(t.get("number")).strip() == str(s_train_num).strip()]
        logging.info(f"Sub {sid}: Filtrlashdan so'ng {len(trains)} ta poyezd qoldi")
    
    prefs = json.loads(s_prefs)
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
            if not p_types: p_types = get_seat_details(c)
                
            if not p_types:
                match_cars.append(f"    {c.get('type','?')}: {seats} joy | {price:,} so'm")
                total_train_seats += seats
            else:
                for pt in p_types:
                    pt_name = pt.get("name", "").lower()
                    pt_count = pt.get("count", 0)
                    if pt_count > 0:
                        if not prefs or pt_name in prefs or (pt_name == "sitting" and c.get("type") == "O'tirish"):
                            match_cars.append(f"    {format_pt_name(pt_name)}: {pt_count} joy | {price:,} so'm")
                            total_train_seats += pt_count
        
        if match_cars:
            dep_time = t.get('departureDate', '')
            arr_time = t.get('arrivalDate', '')
            found_text += f"✅ <b>{t.get('brand','Poyezd')}</b> — {total_train_seats} joy\n" + "\n".join(match_cars) + f"\n🕐 {dep_time} → {arr_time}\n\n"

    if found_text:
        logging.info(f"Sub {sid}: Joy topildi! Xabar yuborilmoqda...")
        msg = f"🔔 <b>Bo'sh joy topildi!</b>\n🚂 {f_st} → {t_st} ({s_date})\n\n{found_text}👉 https://eticket.railway.uz"
        try: 
            await bot.send_message(uid, msg, parse_mode="HTML")
            # Avtomatik olish yoqilgan bo'lsa
            if sub[10]: # sub[10] = auto_book (id, uid, f_st, t_st, f_code, t_code, s_date, s_interval, s_prefs, s_max_p, s_train_num, ..., auto_book)
                # sub indexlarini tekshirish: SELECT id(0), user_id(1), from_st(2), to_st(3), from_code(4), to_code(5), date(6), check_interval(7), preferred_seats(8), max_price(9), train_num(10), ..., auto_book(13)
                # Checker dagi subs query: SELECT id, user_id, from_st, to_st, from_code, to_code, date, check_interval, preferred_seats, max_price, train_num, auto_book FROM ...
                if sub[11]: # auto_book (11-index)
                    await bot.send_message(uid, "⚡️ <b>Avtomatik olish boshlandi...</b>\nIltimos, kuting.", parse_mode="HTML")
                    asyncio.create_task(run_auto_booking(sid))
        except Exception as e: logging.error(f"Xabar yuborishda xato: {e}")
    else:
        logging.info(f"Sub {sid}: Bo'sh joy topilmadi")

async def checker():
    await asyncio.sleep(10)
    # Bir vaqtning o'zida ko'p so'rov yubormaslik uchun limit (semaphore)
    sem = asyncio.Semaphore(3) 

    async def throttled_process(sub, now):
        async with sem:
            await process_subscription(sub, now)

    while True:
        try:
            now = int(time.time())
            subs = await db("SELECT id, user_id, from_st, to_st, from_code, to_code, date, check_interval, preferred_seats, max_price, train_num, auto_book FROM subscriptions WHERE is_active=1 AND (last_checked + check_interval) <= ?", (now,), fetch=True)
            
            if subs:
                tasks = []
                for sub in subs:
                    # Muddatni tekshirish
                    if sub[6] < datetime.now().strftime("%Y-%m-%d"):
                        await db("UPDATE subscriptions SET is_active=0 WHERE id=?", (sub[0],))
                        continue
                    tasks.append(throttled_process(sub, now))
                
                if tasks:
                    await asyncio.gather(*tasks)
                    
        except Exception as e:
            logging.error(f"Checker error: {e}")
        await asyncio.sleep(5)


# ---- Web Server ----
async def handle_webapp(request):
    return web.Response(text=get_webapp_html(), content_type="text/html")

async def handle_trains_api(request):
    try:
        body = await request.json()
        result = await check_trains(body.get("from"), body.get("to"), body.get("date"))
        trains = parse_trains(result) if result else []
        
        # WebApp uchun narxlarni oldindan hisoblab chiqish
        for t in trains:
            for c in t.get("cars", []):
                c["price"] = get_car_price(c)
                
        return web.json_response({"trains": trains})
    except: return web.json_response({"trains": []})

async def handle_get_subs(request):
    uid = request.query.get("user_id")
    user = await db("SELECT premium_until FROM users WHERE user_id=?", (int(uid),), fetch=True)
    
    premium_until = user[0][0] if user else None
    is_premium = False
    if premium_until:
        try:
            is_premium = datetime.fromisoformat(premium_until) > datetime.now()
        except: pass

    subs = await db("SELECT id,from_st,to_st,from_code,to_code,date,check_interval,preferred_seats,max_price,auto_book FROM subscriptions WHERE user_id=? AND is_active=1", (int(uid),), fetch=True)
    res = []
    for s in (subs or []):
        prefs = json.loads(s[7])
        # Tarjima qilingan prefs
        uz_prefs = [format_pt_name(p) for p in prefs]
        res.append({
            "id":s[0],"from_st":s[1],"to_st":s[2],"from_code":s[3],"to_code":s[4],
            "date":s[5],"interval":s[6],"prefs":uz_prefs,"max_price":s[8],
            "auto_book": bool(s[9])
        })
    return web.json_response({"subs": res, "is_premium": is_premium, "premium_until": premium_until[:10] if premium_until else None})

async def handle_add_sub(request):
    try:
        b = await request.json()
        uid = int(b['user_id'])
        
        # Premium statusni tekshirish
        user = await db("SELECT premium_until FROM users WHERE user_id=?", (uid,), fetch=True)
        is_premium = False
        if user and user[0][0]:
            try:
                is_premium = datetime.fromisoformat(user[0][0]) > datetime.now()
            except: pass

        # Oddiy userlar uchun cheklovlar
        if not is_premium:
            active_subs = await db("SELECT COUNT(*) FROM subscriptions WHERE user_id=? AND is_active=1", (uid,), fetch=True)
            if active_subs and active_subs[0][0] >= 2:
                return web.json_response({"ok": False, "error": "Limitga yetdingiz (2 ta). Ko'proq kuzatuv uchun Premium obuna bo'ling."})
            
            # Intervalni 60s ga majburlash
            interval = int(b.get('interval', 300))
            if interval < 60:
                return web.json_response({"ok": False, "error": "Tezkor intervallar (15s, 30s) faqat Premium userlar uchun."})

        f_name = next((k for k, v in STATIONS.items() if v == b['from']), b['from'])
        t_name = next((k for k, v in STATIONS.items() if v == b['to']), b['to'])
        if f_name == t_name:
            return web.json_response({"ok": False, "error": "Qayerdan va Qayerga bir xil bo'lishi mumkin emas."})
        
        await db("""INSERT INTO subscriptions 
            (user_id, from_st, to_st, from_code, to_code, date, train_num, check_interval, preferred_seats, auto_book) 
            VALUES (?,?,?,?,?,?,?,?,?,?)""", (
            uid, f_name, t_name, b['from'], b['to'], b['date'], b.get('train_num'), b.get('interval', 60), json.dumps(b.get('prefs', [])) , 1 if b.get('auto_book') else 0
        ))
        
        # Yangi ID ni olish va darhol tekshiruvni boshlash
        last_id = await db("SELECT last_insert_rowid()", fetch=True)
        if last_id:
            new_sub = await db("SELECT id, user_id, from_st, to_st, from_code, to_code, date, check_interval, preferred_seats, max_price, train_num FROM subscriptions WHERE id=?", (last_id[0][0],), fetch=True)
            if new_sub:
                asyncio.create_task(process_subscription(new_sub[0], int(time.time())))

        return web.json_response({"ok": True})
    except Exception as e: return web.json_response({"ok": False, "error": str(e)})

async def handle_del_sub(request):
    b = await request.json()
    await db("UPDATE subscriptions SET is_active=0 WHERE id=?", (int(b.get("id")),))
    return web.json_response({"ok": True})

async def handle_update_sub(request):
    try:
        b = await request.json()
        sid = int(b.get("id"))
        interval = int(b.get("interval"))
        
        # Premium tekshiruvi (agar interval 60dan kichik bo'lsa)
        if interval < 60:
            uid = await db("SELECT user_id FROM subscriptions WHERE id=?", (sid,), fetch=True)
            if uid:
                user = await db("SELECT premium_until FROM users WHERE user_id=?", (uid[0][0],), fetch=True)
                is_premium = False
                if user and user[0][0]:
                    try: is_premium = datetime.fromisoformat(user[0][0]) > datetime.now()
                    except: pass
                if not is_premium:
                    return web.json_response({"ok": False, "error": "Premium obuna talab qilinadi."})
        
        await db("UPDATE subscriptions SET check_interval=? WHERE id=?", (interval, sid))
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def handle_create_invoice(request):
    try:
        b = await request.json()
        days = int(b.get("days", 1))
        price = 1 if days == 1 else (5 if days == 5 else 10)
        
        link = await bot.create_invoice_link(
            title=f"{days} kunlik Premium",
            description=f"Railway bot uchun {days} kunlik premium obuna",
            payload=f"coins_{days}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="Stars", amount=price)]
        )
        return web.json_response({"ok": True, "link": link})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def handle_support_api(request):
    try:
        body = await request.json()
        uid = body.get("user_id")
        name = body.get("user_name")
        username = body.get("username", "")
        msg = body.get("message")
        
        # Bazaga saqlash
        await db("INSERT INTO support_chat (user_id, sender, message) VALUES (?, 'user', ?)", (uid, msg))
        
        admin_msg = f"🎧 <b>Yangi Support xabari!</b>\n\n" \
                    f"👤 <b>Kimdan:</b> {name} (@{username})\n" \
                    f"🆔 <b>ID:</b> <code>{uid}</code>\n\n" \
                    f"📝 <b>Xabar:</b>\n{msg}\n\n" \
                    f"<i>Javob berish uchun ushbu xabarga 'Reply' qiling.</i>"
        
        try:
            await bot.send_message(ADMIN_ID, admin_msg, parse_mode="HTML")
            return web.json_response({"ok": True})
        except Exception as e:
            return web.json_response({"ok": False, "error": "Admin xabar qabul qila olmadi"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def handle_get_chat_api(request):
    try:
        uid = request.query.get("user_id")
        rows = await db("SELECT sender, message, timestamp FROM support_chat WHERE user_id=? ORDER BY id ASC", (uid,), fetch=True)
        msgs = [{"sender": r[0], "text": r[1], "time": r[2]} for r in rows]
        return web.json_response({"ok": True, "messages": msgs})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def handle_book_api(request):
    try:
        b = await request.json()
        uid = b.get("user_id")
        await db("""INSERT INTO bookings 
            (user_id, train_num, train_brand, from_st, to_st, date, passenger_name, passenger_passport, passenger_birth) 
            VALUES (?,?,?,?,?,?,?,?,?)""", (
            uid, b.get('train_num'), b.get('train_brand'), b.get('from_st'), b.get('to_st'), 
            b.get('date'), b.get('p_name'), b.get('p_passport'), b.get('p_birth')
        ))
        admin_msg = f"🛒 <b>Yangi Chipta Buyurtmasi!</b>\n\n" \
                    f"👤 <b>User:</b> {b.get('user_name')} (ID: {uid})\n" \
                    f"🚂 <b>Poyezd:</b> {b.get('train_brand')} (№{b.get('train_num')})\n" \
                    f"📍 <b>Yo'nalish:</b> {b.get('from_st')} → {b.get('to_st')}\n" \
                    f"📅 <b>Sana:</b> {b.get('date')}\n\n" \
                    f"👤 <b>Yo'lovchi:</b> {b.get('p_name')}\n" \
                    f"🆔 <b>Pasport:</b> {b.get('p_passport')}\n" \
                    f"🎂 <b>Tug'ilgan sana:</b> {b.get('p_birth')}"
        await bot.send_message(ADMIN_ID, admin_msg, parse_mode="HTML")
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def verify_railway_login(login, password):
    """Railway saytiga login/parol to'g'riligini tekshirish"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        try:
            await page.goto("https://eticket.railway.uz/uz/pages/login", timeout=30000)
            await page.fill("input[name='login']", login)
            await page.fill("input[name='password']", password)
            await page.click("button[type='submit']")
            await page.wait_for_load_state("networkidle")
            
            # Agar login xato bo'lsa, xatolik xabari chiqadi yoki login sahifasida qoladi
            # Muvaffaqiyatli bo'lsa, /profile yoki asosiy sahifaga o'tadi
            if "login" in page.url:
                # Saytdagi xatolik xabarini qidirish
                error = await page.query_selector(".alert-danger")
                if error:
                    err_text = await error.inner_text()
                    return False, err_text.strip()
                return False, "Login yoki parol xato."
            return True, None
        except Exception as e:
            return False, f"Ulanishda xato: {e}"
        finally:
            await browser.close()

async def handle_profile_api(request):
    uid = request.query.get("user_id")
    if request.method == "GET":
        user = await db("SELECT p_name, p_passport, p_birth, r_login, r_password FROM users WHERE user_id=?", (int(uid),), fetch=True)
        if user:
            return web.json_response({"ok": True, "p_name": user[0][0], "p_passport": user[0][1], "p_birth": user[0][2], "r_login": user[0][3], "r_password": user[0][4]})
        return web.json_response({"ok": False})
    else:
        b = await request.json()
        login = b.get('login', '').strip()
        password = b.get('password', '').strip()
        
        # Agar login/parol kiritilgan bo'lsa, tekshirib ko'ramiz
        if login and password:
            ok, err = await verify_railway_login(login, password)
            if not ok:
                return web.json_response({"ok": False, "error": err})
        
        await db("UPDATE users SET p_name=?, p_passport=?, p_birth=?, r_login=?, r_password=? WHERE user_id=?", 
                 (b.get('name'), b.get('passport'), b.get('birth'), login, password, int(uid)))
        return web.json_response({"ok": True})

async def run_auto_booking(sub_id):
    """Orqa fonda Playwright orqali avtomatik olish mantiqi"""
    logging.info(f"Auto-booking started for sub: {sub_id}")
    
    # 1. Ma'lumotlarni bazadan olish
    sub_rows = await db("SELECT user_id, from_code, to_code, date, train_num, preferred_seats FROM subscriptions WHERE id=?", (sub_id,), fetch=True)
    if not sub_rows: return
    uid, f_code, t_code, date, t_num, prefs_json = sub_rows[0]
    
    user_rows = await db("SELECT p_name, p_passport, p_birth, r_login, r_password FROM users WHERE user_id=?", (uid,), fetch=True)
    if not user_rows or not user_rows[0][0]:
        await bot.send_message(uid, "❌ <b>Xato:</b> Profilingiz to'ldirilmagan! WebApp -> Profil bo'limiga kiring.")
        return
    p_name, p_pass, p_birth, r_login, r_pass = user_rows[0]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # 2. Avtorizatsiya (Login)
            await page.goto("https://eticket.railway.uz/uz/pages/login", timeout=60000)
            if r_login and r_pass:
                await page.fill("input[name='login']", r_login)
                await page.fill("input[name='password']", r_pass)
                await page.click("button[type='submit']")
                await page.wait_for_load_state("networkidle")
            
            # 3. Qidiruv sahifasiga o'tish
            url = f"https://eticket.railway.uz/uz/pages/trains-page?date={date}&from={f_code}&to={t_code}"
            await page.goto(url, timeout=60000)
            await page.wait_for_load_state("networkidle")
            
            # 3. Poyezdni topish va tanlash
            # Reys raqami bo'yicha qidirish
            train_selector = f"text='{t_num}'"
            await page.wait_for_selector(train_selector, timeout=10000)
            
            # "Tanlash" tugmasini topish (poyezd blokining ichidan)
            train_card = page.locator(".train-item").filter(has_text=t_num)
            await train_card.get_by_role("button", name="Tanlash").click()
            await asyncio.sleep(2)
            
            # 4. Vagon va o'rin tanlash
            # Birinchi bo'sh vagonni tanlash
            await page.locator(".wagon-item").first.click()
            await asyncio.sleep(1)
            
            # Birinchi bo'sh o'rinni tanlash
            await page.locator(".seat-available").first.click()
            await page.get_by_role("button", name="Davom etish").click()
            
            # 5. Yo'lovchi ma'lumotlarini to'ldirish
            # Ism va familiyani ajratish (agar bo'sh joy bo'lsa)
            name_parts = p_name.split()
            surname = name_parts[0] if len(name_parts) > 0 else p_name
            firstname = name_parts[1] if len(name_parts) > 1 else ""
            
            await page.fill("input[placeholder*='Familiya']", surname)
            await page.fill("input[placeholder*='Ism']", firstname)
            await page.fill("input[placeholder*='Seriya']", p_pass[:2])
            await page.fill("input[placeholder*='Raqam']", p_pass[2:])
            
            # Tug'ilgan sana (input type="date" bo'lishi mumkin)
            await page.fill("input[type='date']", p_birth)
            
            # 6. Bron qilishni yakunlash
            await page.get_by_role("button", name="Bron qilish").click()
            await page.wait_for_load_state("networkidle")
            
            # 7. To'lov havolasini olish
            final_url = page.url
            if "order" in final_url or "pay" in final_url:
                msg = f"✅ <b>Chipta muvaffaqiyatli band qilindi!</b>\n\n🔗 <b>To'lov havolasi:</b>\n{final_url}\n\n⚠️ <i>Diqqat: 15 daqiqa ichida to'lov qilishingiz kerak!</i>"
                await bot.send_message(uid, msg, parse_mode="HTML")
                # Kuzatuvni o'chirish
                await db("UPDATE subscriptions SET is_active=0 WHERE id=?", (sub_id,))
            else:
                await bot.send_message(uid, "❌ <b>Avtomatik olishda xato:</b> To'lov sahifasiga o'tib bo'lmadi.")
                
        except Exception as e:
            logging.error(f"Auto-booking error for {uid}: {e}")
            await bot.send_message(uid, f"❌ <b>Avtomatik olishda xato:</b>\n{str(e)[:100]}...")
        finally:
            await browser.close()

async def start_webserver():
    app = web.Application()
    app.router.add_get("/", handle_webapp)
    app.router.add_post("/api/trains", handle_trains_api)
    app.router.add_get("/api/subs", handle_get_subs)
    app.router.add_post("/api/subs", handle_add_sub)
    app.router.add_post("/api/subs/delete", handle_del_sub)
    app.router.add_post("/api/subs/update", handle_update_sub)
    app.router.add_post("/api/create_invoice", handle_create_invoice)
    app.router.add_post("/api/support", handle_support_api)
    app.router.add_get("/api/support/messages", handle_get_chat_api)
    app.router.add_post("/api/book", handle_book_api)
    app.router.add_get("/api/profile", handle_profile_api)
    app.router.add_post("/api/profile", handle_profile_api)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    logging.info(f"Web server {PORT} portda ishga tushdi")

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )
    await init_db()
    await start_webserver()
    asyncio.create_task(cookie_refresher())
    asyncio.create_task(checker())
    await send_error_to_admin("🚀 *Bot ishga tushdi!*")
    try:
        await dp.start_polling(bot)
    finally:
        if _http_session and not _http_session.closed:
            await _http_session.close()

if __name__ == "__main__":
    asyncio.run(main())
