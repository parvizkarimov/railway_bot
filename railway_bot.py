"""
O'zbekiston Temir Yo'llari - Bilet Kuzatuvchi Bot
aiogram 2.x versiyasi
"""

import asyncio
import aiohttp
import logging
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import executor
import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
COOKIE = os.getenv("RAILWAY_COOKIE", "__stripe_mid=f43f7783-226c-4ff7-9510-625484dac49e0d4cf0; XSRF-TOKEN=d89afd60-e961-4304-8cf2-d7318b56a71d")
XSRF_TOKEN = os.getenv("XSRF_TOKEN", "d89afd60-e961-4304-8cf2-d7318b56a71d")
CHECK_INTERVAL = 300

STATIONS = {
    "Toshkent": "2900000",
    "Samarqand": "2900700",
    "Buxoro": "2900600",
    "Namangan": "2908600",
    "Andijon": "2900200",
    "Farg'ona": "2905000",
    "Qarshi": "2904100",
    "Termiz": "2907500",
    "Urganch": "2909000",
    "Nukus": "2903400",
}

def init_db():
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT,
        is_premium INTEGER DEFAULT 0, premium_until TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, from_st TEXT, to_st TEXT,
        from_code TEXT, to_code TEXT, date TEXT, is_active INTEGER DEFAULT 1)""")
    conn.commit()
    conn.close()

def db(query, params=(), fetch=False):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute(query, params)
    result = c.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return result

async def check_trains(from_code, to_code, date):
    url = "https://eticket.railway.uz/api/v3/handbook/trains/list"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Cookie": COOKIE,
        "X-Xsrf-Token": XSRF_TOKEN,
        "Device-Type": "BROWSER",
        "Origin": "https://eticket.railway.uz",
        "User-Agent": "Mozilla/5.0 (Linux; Android 6.0) AppleWebKit/537.36 Chrome/147.0.0.0 Mobile Safari/537.36",
    }
    payload = {"directions": {"forward": {"date": date, "depStationCode": from_code, "arvStationCode": to_code}}}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    return await r.json()
    except Exception as e:
        logging.error(f"API xato: {e}")
    return None

def parse_trains(data):
    trains = []
    try:
        for train in data.get("directions", {}).get("forward", []):
            cars = train.get("cars", [])
            total = sum(c.get("freeSeats", 0) for c in cars)
            car_info = [f"{c['type']}: {c['freeSeats']} joy" for c in cars if c.get("freeSeats", 0) > 0]
            trains.append({"name": train.get("brand", "?"), "dep": train.get("departureDate", ""),
                           "arr": train.get("arrivalDate", ""), "total": total, "cars": car_info})
    except Exception as e:
        logging.error(f"Parse xato: {e}")
    return trains

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

class Form(StatesGroup):
    from_st = State()
    to_st = State()
    date = State()

def st_kb(exclude=None):
    kb = InlineKeyboardMarkup(row_width=2)
    for name in STATIONS:
        if name != exclude:
            kb.insert(InlineKeyboardButton(name, callback_data=f"st|{name}"))
    return kb

@dp.message_handler(commands=["start"])
async def cmd_start(msg: types.Message):
    db("INSERT OR IGNORE INTO users (user_id, username) VALUES (?,?)", (msg.from_user.id, msg.from_user.username))
    await msg.answer(
        "🚂 *Temir Yo'l Bilet Kuzatuvchi*\n\n"
        "Bot poyezd biletlarini kuzatadi!\n\n"
        "• 1 ta reys — *bepul*\n"
        "• 3+ reys — 50⭐ Stars / 3 kun\n\n"
        "/kuzat — yangi reys\n/mening — kuzatuvlarim",
        parse_mode="Markdown")

@dp.message_handler(commands=["kuzat"])
async def cmd_watch(msg: types.Message):
    user_id = msg.from_user.id
    users = db("SELECT is_premium, premium_until FROM users WHERE user_id=?", (user_id,), fetch=True)
    is_premium = False
    if users and users[0][0]:
        if users[0][1] and datetime.fromisoformat(users[0][1]) > datetime.now():
            is_premium = True
    count = db("SELECT COUNT(*) FROM subscriptions WHERE user_id=? AND is_active=1", (user_id,), fetch=True)[0][0]
    if count >= 1 and not is_premium:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("⭐ 50 Stars — 3 kunlik obuna", callback_data="buy_premium"))
        await msg.answer(f"⭐ *Premium kerak!*\n\n{count} ta reys kuzatyapsiz. Bepul limit: 1 ta", parse_mode="Markdown", reply_markup=kb)
        return
    await msg.answer("🚉 *Qayerdan?*", parse_mode="Markdown", reply_markup=st_kb())
    await Form.from_st.set()

@dp.callback_query_handler(lambda c: c.data.startswith("st|"), state=Form.from_st)
async def got_from(cb: types.CallbackQuery, state: FSMContext):
    st = cb.data.split("|")[1]
    await state.update_data(from_st=st, from_code=STATIONS[st])
    await cb.message.edit_text(f"✅ Qayerdan: *{st}*\n\n🚉 *Qayerga?*", parse_mode="Markdown", reply_markup=st_kb(exclude=st))
    await Form.to_st.set()

@dp.callback_query_handler(lambda c: c.data.startswith("st|"), state=Form.to_st)
async def got_to(cb: types.CallbackQuery, state: FSMContext):
    st = cb.data.split("|")[1]
    data = await state.get_data()
    await state.update_data(to_st=st, to_code=STATIONS[st])
    await cb.message.edit_text(
        f"✅ Qayerdan: *{data['from_st']}*\n✅ Qayerga: *{st}*\n\n📅 *Sanani yuboring* (masalan: 2026-04-25)",
        parse_mode="Markdown")
    await Form.date.set()

@dp.message_handler(state=Form.date)
async def got_date(msg: types.Message, state: FSMContext):
    date = msg.text.strip()
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        await msg.answer("❌ Format noto'g'ri! Masalan: *2026-04-25*", parse_mode="Markdown")
        return
    data = await state.get_data()
    await state.finish()
    await msg.answer("🔍 Tekshirilmoqda...")
    result = await check_trains(data["from_code"], data["to_code"], date)
    if not result:
        await msg.answer("❌ Saytga ulanishda xato. Cookie yangilanishi kerak.")
        return
    db("INSERT INTO subscriptions (user_id,from_st,to_st,from_code,to_code,date) VALUES (?,?,?,?,?,?)",
       (msg.from_user.id, data["from_st"], data["to_st"], data["from_code"], data["to_code"], date))
    trains = parse_trains(result)
    text = f"🚂 *{data['from_st']} → {data['to_st']}* ({date})\n\n"
    if trains:
        for t in trains:
            if t["total"] > 0:
                text += f"✅ *{t['name']}* — {t['total']} joy\n🕐 {t['dep']} → {t['arr']}\n"
                for c in t["cars"]: text += f"   • {c}\n"
                text += "\n"
            else:
                text += f"❌ *{t['name']}* — joy yo'q ({t['dep']})\n"
    else:
        text += "Hozircha poyezd yo'q.\n"
    text += f"\n🔔 Har {CHECK_INTERVAL//60} daqiqada tekshiraman!"
    await msg.answer(text, parse_mode="Markdown")

@dp.message_handler(commands=["mening"])
async def cmd_my(msg: types.Message):
    subs = db("SELECT id,from_st,to_st,date FROM subscriptions WHERE user_id=? AND is_active=1", (msg.from_user.id,), fetch=True)
    if not subs:
        await msg.answer("📭 Kuzatuvlar yo'q. /kuzat bilan boshlang!")
        return
    text = "📋 *Mening kuzatuvlarim:*\n\n"
    kb = InlineKeyboardMarkup()
    for s in subs:
        text += f"🚂 {s[1]} → {s[2]} | {s[3]}\n"
        kb.add(InlineKeyboardButton(f"❌ {s[1]}→{s[2]} ({s[3]})", callback_data=f"del|{s[0]}"))
    await msg.answer(text, parse_mode="Markdown", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("del|"))
async def del_sub(cb: types.CallbackQuery):
    db("UPDATE subscriptions SET is_active=0 WHERE id=?", (int(cb.data.split("|")[1]),))
    await cb.answer("✅ O'chirildi!")
    await cb.message.edit_text("✅ Kuzatuv o'chirildi.")

@dp.callback_query_handler(lambda c: c.data == "buy_premium")
async def buy(cb: types.CallbackQuery):
    await bot.send_invoice(cb.from_user.id, title="⭐ 3 Kunlik Premium",
        description="3+ reys kuzatish. 3 kunlik muddat.", payload="premium_3days",
        currency="XTR", prices=[types.LabeledPrice("3 kunlik", 50)], provider_token="")

@dp.pre_checkout_query_handler()
async def pre_checkout(pcq: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pcq.id, ok=True)

@dp.message_handler(content_types=types.ContentType.SUCCESSFUL_PAYMENT)
async def paid(msg: types.Message):
    until = (datetime.now() + timedelta(days=3)).isoformat()
    db("UPDATE users SET is_premium=1, premium_until=? WHERE user_id=?", (until, msg.from_user.id))
    await msg.answer("🎉 *Premium faollashtirildi!* 3 kun davomida cheksiz kuzatuv.", parse_mode="Markdown")

async def checker():
    await asyncio.sleep(30)
    while True:
        try:
            subs = db("SELECT id,user_id,from_st,to_st,from_code,to_code,date FROM subscriptions WHERE is_active=1", fetch=True)
            for sub in (subs or []):
                sid, uid, from_st, to_st, from_code, to_code, date = sub
                if date < datetime.now().strftime("%Y-%m-%d"):
                    db("UPDATE subscriptions SET is_active=0 WHERE id=?", (sid,))
                    continue
                result = await check_trains(from_code, to_code, date)
                if not result: continue
                available = [t for t in parse_trains(result) if t["total"] > 0]
                if available:
                    text = f"🔔 *Bo'sh joy topildi!*\n🚂 *{from_st} → {to_st}* ({date})\n\n"
                    for t in available:
                        text += f"✅ *{t['name']}* — {t['total']} joy\n🕐 {t['dep']} → {t['arr']}\n"
                    text += "\n👉 https://eticket.railway.uz"
                    try: await bot.send_message(uid, text, parse_mode="Markdown")
                    except: pass
        except Exception as e:
            logging.error(f"Checker xato: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

async def on_startup(dp):
    init_db()
    asyncio.create_task(checker())

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
