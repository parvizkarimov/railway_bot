"""
O'zbekiston Temir Yo'llari - Bilet Kuzatuvchi Telegram Bot
==========================================================
O'rnatish:
    pip install aiogram aiohttp

Ishga tushirish:
    python railway_bot.py

Kerakli o'zgaruvchilar (.env yoki to'g'ridan-to'g'ri):
    BOT_TOKEN - @BotFather dan olingan token
"""

import asyncio
import aiohttp
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import json
import sqlite3

# ==================== SOZLAMALAR ====================
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # @BotFather dan oling

# Cookie ni yangilab turish kerak (har 24 soatda)
COOKIE = "__stripe_mid=f43f7783-226c-4ff7-9510-625484dac49e0d4cf0; _ga=GA1.1.1292918010.1767087098; XSRF-TOKEN=d89afd60-e961-4304-8cf2-d7318b56a71d"
XSRF_TOKEN = "d89afd60-e961-4304-8cf2-d7318b56a71d"

# Tekshirish intervali (soniyada) - 5 daqiqa
CHECK_INTERVAL = 300

# Bepul kuzatish limiti
FREE_LIMIT = 1

# ==================== STANSIYA KODLARI ====================
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

# ==================== DATABASE ====================
def init_db():
    conn = sqlite3.connect("railway_bot.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            from_station TEXT,
            to_station TEXT,
            from_code TEXT,
            to_code TEXT,
            date TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            is_premium INTEGER DEFAULT 0,
            premium_until TEXT,
            sub_count INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect("railway_bot.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def create_user(user_id, username):
    conn = sqlite3.connect("railway_bot.db")
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users (user_id, username, is_premium, sub_count) VALUES (?, ?, 0, 0)",
        (user_id, username)
    )
    conn.commit()
    conn.close()

def get_user_sub_count(user_id):
    conn = sqlite3.connect("railway_bot.db")
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) FROM subscriptions WHERE user_id = ? AND is_active = 1",
        (user_id,)
    )
    count = c.fetchone()[0]
    conn.close()
    return count

def add_subscription(user_id, from_station, to_station, from_code, to_code, date):
    conn = sqlite3.connect("railway_bot.db")
    c = conn.cursor()
    c.execute("""
        INSERT INTO subscriptions (user_id, from_station, to_station, from_code, to_code, date, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
    """, (user_id, from_station, to_station, from_code, to_code, date, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_all_active_subscriptions():
    conn = sqlite3.connect("railway_bot.db")
    c = conn.cursor()
    c.execute("SELECT * FROM subscriptions WHERE is_active = 1")
    subs = c.fetchall()
    conn.close()
    return subs

def deactivate_subscription(sub_id):
    conn = sqlite3.connect("railway_bot.db")
    c = conn.cursor()
    c.execute("UPDATE subscriptions SET is_active = 0 WHERE id = ?", (sub_id,))
    conn.commit()
    conn.close()

def get_user_subscriptions(user_id):
    conn = sqlite3.connect("railway_bot.db")
    c = conn.cursor()
    c.execute(
        "SELECT * FROM subscriptions WHERE user_id = ? AND is_active = 1",
        (user_id,)
    )
    subs = c.fetchall()
    conn.close()
    return subs

# ==================== API ====================
async def check_trains(from_code: str, to_code: str, date: str):
    """eticket.railway.uz dan poyezdlar ro'yxatini olish"""
    url = "https://eticket.railway.uz/api/v3/handbook/trains/list"
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Cookie": COOKIE,
        "X-Xsrf-Token": XSRF_TOKEN,
        "Device-Type": "BROWSER",
        "Origin": "https://eticket.railway.uz",
        "Referer": "https://eticket.railway.uz/uz/home",
        "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5) AppleWebKit/537.36 Chrome/147.0.0.0 Mobile Safari/537.36",
    }
    
    payload = {
        "directions": {
            "forward": {
                "date": date,
                "depStationCode": from_code,
                "arvStationCode": to_code
            }
        }
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data
                else:
                    logging.error(f"API xato: {resp.status}")
                    return None
    except Exception as e:
        logging.error(f"So'rov xatosi: {e}")
        return None

def parse_trains(data):
    """API javobidan poyezdlar ma'lumotini ajratib olish"""
    trains = []
    try:
        forward = data.get("directions", {}).get("forward", [])
        for train in forward:
            name = train.get("brand", "Noma'lum")
            dep = train.get("departureDate", "")
            arr = train.get("arrivalDate", "")
            cars = train.get("cars", [])
            
            total_free = sum(car.get("freeSeats", 0) for car in cars)
            car_info = []
            for car in cars:
                if car.get("freeSeats", 0) > 0:
                    car_info.append(f"{car['type']}: {car['freeSeats']} joy")
            
            trains.append({
                "name": name,
                "departure": dep,
                "arrival": arr,
                "total_free": total_free,
                "cars": car_info
            })
    except Exception as e:
        logging.error(f"Parse xatosi: {e}")
    return trains

# ==================== BOT ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class TrainSearch(StatesGroup):
    from_station = State()
    to_station = State()
    date = State()

def station_keyboard():
    buttons = []
    row = []
    for i, station in enumerate(STATIONS.keys()):
        row.append(InlineKeyboardButton(text=station, callback_data=f"st_{station}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.message(CommandStart())
async def start(message: types.Message):
    create_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "🚂 *O'zbekiston Temir Yo'llari - Bilet Kuzatuvchi*\n\n"
        "Bu bot poyezd biletlarini kuzatadi va bo'sh joy chiqsa xabar beradi!\n\n"
        "📌 *Imkoniyatlar:*\n"
        "• 1 ta reys — *bepul*\n"
        "• 3+ reys — Telegram Stars (3 kunlik obuna)\n\n"
        "Boshlash uchun /kuzat buyrug'ini yuboring",
        parse_mode="Markdown"
    )

@dp.message(Command("kuzat"))
async def watch_train(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    sub_count = get_user_sub_count(user_id)
    user = get_user(user_id)
    
    is_premium = user[2] if user else 0
    
    if sub_count >= FREE_LIMIT and not is_premium:
        await message.answer(
            "⭐ *Premium kerak!*\n\n"
            f"Siz allaqachon {sub_count} ta reys kuzatyapsiz.\n"
            "Bepul limit: 1 ta reys\n\n"
            "3+ reys uchun *3 kunlik obuna* sotib oling:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⭐ 50 Stars — 3 kunlik obuna", callback_data="buy_premium")
            ]])
        )
        return
    
    await message.answer("🚉 *Qayerdan?* Stansiyani tanlang:", parse_mode="Markdown", reply_markup=station_keyboard())
    await state.set_state(TrainSearch.from_station)

@dp.callback_query(F.data.startswith("st_"), TrainSearch.from_station)
async def select_from(callback: types.CallbackQuery, state: FSMContext):
    station = callback.data.replace("st_", "")
    await state.update_data(from_station=station, from_code=STATIONS[station])
    await callback.message.edit_text(f"✅ Qayerdan: *{station}*\n\n🚉 *Qayerga?* Stansiyani tanlang:", parse_mode="Markdown", reply_markup=station_keyboard())
    await state.set_state(TrainSearch.to_station)

@dp.callback_query(F.data.startswith("st_"), TrainSearch.to_station)
async def select_to(callback: types.CallbackQuery, state: FSMContext):
    station = callback.data.replace("st_", "")
    data = await state.get_data()
    
    if station == data["from_station"]:
        await callback.answer("❌ Boshqa stansiya tanlang!", show_alert=True)
        return
    
    await state.update_data(to_station=station, to_code=STATIONS[station])
    await callback.message.edit_text(
        f"✅ Qayerdan: *{data['from_station']}*\n"
        f"✅ Qayerga: *{station}*\n\n"
        f"📅 *Sanani yuboring* (masalan: 2026-04-25)",
        parse_mode="Markdown"
    )
    await state.set_state(TrainSearch.date)

@dp.message(TrainSearch.date)
async def select_date(message: types.Message, state: FSMContext):
    date_text = message.text.strip()
    
    try:
        datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        await message.answer("❌ Noto'g'ri format! Masalan: *2026-04-25*", parse_mode="Markdown")
        return
    
    data = await state.get_data()
    await state.clear()
    
    # Avval bir marta tekshirib ko'ramiz
    await message.answer("🔍 Tekshirilmoqda...")
    
    result = await check_trains(data["from_code"], data["to_code"], date_text)
    
    if result is None:
        await message.answer("❌ Saytga ulanishda xato. Cookie eskirgan bo'lishi mumkin.")
        return
    
    trains = parse_trains(result)
    
    # Obunani saqlash
    add_subscription(
        message.from_user.id,
        data["from_station"], data["to_station"],
        data["from_code"], data["to_code"],
        date_text
    )
    
    if trains:
        text = f"🚂 *{data['from_station']} → {data['to_station']}* ({date_text})\n\n"
        for t in trains:
            if t["total_free"] > 0:
                text += f"✅ *{t['name']}*\n"
                text += f"🕐 {t['departure']} → {t['arrival']}\n"
                text += f"💺 Bo'sh joylar: {t['total_free']}\n"
                for c in t["cars"]:
                    text += f"   • {c}\n"
                text += "\n"
            else:
                text += f"❌ *{t['name']}* — joy yo'q\n"
                text += f"🕐 {t['departure']} → {t['arrival']}\n\n"
        
        text += f"\n🔔 Har {CHECK_INTERVAL//60} daqiqada tekshirib turaman!"
        await message.answer(text, parse_mode="Markdown")
    else:
        await message.answer(
            f"😔 *{data['from_station']} → {data['to_station']}* ({date_text})\n\n"
            "Hozircha poyezd topilmadi.\n"
            f"🔔 Har {CHECK_INTERVAL//60} daqiqada tekshirib xabar beraman!",
            parse_mode="Markdown"
        )

@dp.message(Command("mening_kuzatuvlarim"))
async def my_subscriptions(message: types.Message):
    subs = get_user_subscriptions(message.from_user.id)
    if not subs:
        await message.answer("📭 Hozircha kuzatuvlar yo'q. /kuzat buyrug'i bilan boshlang!")
        return
    
    text = "📋 *Mening kuzatuvlarim:*\n\n"
    buttons = []
    for sub in subs:
        sub_id, user_id, from_st, to_st, from_code, to_code, date, is_active, created = sub
        text += f"🚂 {from_st} → {to_st} | {date}\n"
        buttons.append([InlineKeyboardButton(text=f"❌ O'chirish: {from_st}→{to_st}", callback_data=f"del_{sub_id}")])
    
    await message.answer(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("del_"))
async def delete_sub(callback: types.CallbackQuery):
    sub_id = int(callback.data.replace("del_", ""))
    deactivate_subscription(sub_id)
    await callback.answer("✅ Kuzatuv o'chirildi!")
    await callback.message.edit_text("✅ Kuzatuv muvaffaqiyatli o'chirildi.")

@dp.callback_query(F.data == "buy_premium")
async def buy_premium(callback: types.CallbackQuery):
    # Telegram Stars to'lov
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="⭐ 3 Kunlik Premium Obuna",
        description="3 ta va undan ko'p reyslarni kuzatish imkoniyati. 3 kunlik muddat.",
        payload="premium_3days",
        currency="XTR",  # Telegram Stars
        prices=[types.LabeledPrice(label="3 kunlik obuna", amount=50)],
    )

@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):
    from datetime import timedelta
    user_id = message.from_user.id
    premium_until = (datetime.now() + timedelta(days=3)).isoformat()
    
    conn = sqlite3.connect("railway_bot.db")
    c = conn.cursor()
    c.execute(
        "UPDATE users SET is_premium = 1, premium_until = ? WHERE user_id = ?",
        (premium_until, user_id)
    )
    conn.commit()
    conn.close()
    
    await message.answer(
        "🎉 *To'lov qabul qilindi!*\n\n"
        "⭐ 3 kunlik Premium obuna faollashtirildi!\n"
        "Endi 3 ta va undan ko'p reyslarni kuzatishingiz mumkin.\n\n"
        "/kuzat buyrug'i bilan yangi reys qo'shing!",
        parse_mode="Markdown"
    )

# ==================== BACKGROUND CHECKER ====================
async def background_checker():
    """Har 5 daqiqada barcha obunalarni tekshiradi"""
    while True:
        await asyncio.sleep(CHECK_INTERVAL)
        logging.info("Tekshirish boshlandi...")
        
        subs = get_all_active_subscriptions()
        
        for sub in subs:
            sub_id, user_id, from_st, to_st, from_code, to_code, date, is_active, created = sub
            
            # O'tgan sanalarni o'chirish
            if date < datetime.now().strftime("%Y-%m-%d"):
                deactivate_subscription(sub_id)
                continue
            
            result = await check_trains(from_code, to_code, date)
            if result is None:
                continue
            
            trains = parse_trains(result)
            available = [t for t in trains if t["total_free"] > 0]
            
            if available:
                text = f"🔔 *Bo'sh joy topildi!*\n\n"
                text += f"🚂 *{from_st} → {to_st}* ({date})\n\n"
                for t in available:
                    text += f"✅ *{t['name']}*\n"
                    text += f"🕐 {t['departure']} → {t['arrival']}\n"
                    text += f"💺 Bo'sh: {t['total_free']} joy\n"
                    for c in t["cars"]:
                        text += f"   • {c}\n"
                    text += "\n"
                text += "👉 Tez harid qiling: https://eticket.railway.uz"
                
                try:
                    await bot.send_message(user_id, text, parse_mode="Markdown")
                except Exception as e:
                    logging.error(f"Xabar yuborishda xato {user_id}: {e}")

# ==================== MAIN ====================
async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    
    # Background checker ni parallel ishlatish
    asyncio.create_task(background_checker())
    
    print("🚂 Bot ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
