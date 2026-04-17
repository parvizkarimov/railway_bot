# 🚂 Railway Bilet Kuzatuvchi - Loyiha Arxitekturasi

Ushbu hujjat botning ishlash prinsipi, texnologik steki va tarkibiy qismlari haqida batafsil ma'lumot beradi.

## 🛠 Texnologik Stek
- **Til:** Python 3.10+
- **Bot Framework:** `aiogram 3.x` (Asinxron Telegram bot)
- **Web Server:** `aiohttp` (WebApp va API uchun)
- **Ma'lumotlar bazasi:** `aiosqlite` (SQLite bazasi doimiy Volume bilan)
- **Brauzer Avtomatizatsiyasi:** `Playwright` (Anti-bot tizimini chetlab o'tish uchun)
- **Frontend:** HTML5, CSS3 (Vanilla), JavaScript (Telegram WebApp API)

---

## 🏗 Loyiha Tuzilishi

### 1. Bot Qatlami (`railway_bot.py`)
Botning asosiy interfeysi. Foydalanuvchilarni ro'yxatga olish, Premium obuna (Telegram Stars orqali) va admin buyruqlari bilan ishlaydi.
- `/start`: Foydalanuvchini WebApp'ga yo'naltiruvchi asosiy menyu.
- `/stars`: Yulduzlar sotib olish va premium muddatni uzaytirish.
- `/users`: Faqat admin uchun foydalanuvchilar statistikasini ko'rish.

### 2. Checker (Kuzatuvchi) Qatlami
Orqa fonda (background) ishlovchi asinxron loop. 
- Foydalanuvchi tanlagan intervalga (15s, 30s, 60s) qarab Railway API'ga so'rov yuboradi.
- Bo'sh joy topilganda darhol foydalanuvchiga poyezd turi, joylar soni va narxi bilan xabar yuboradi.

### 3. Cookie & Anti-Bot Qatlami
Railway saytining qattiq himoyasini chetlab o'tish uchun maxsus tizim.
- **`cookie_refresher`**: Har 20 daqiqada orqa fonda Playwright (headless brauzer) ochadi.
- Saytga haqiqiy odamdek kirib, `laravel_session` va `XSRF-TOKEN` larni yangilab turadi.

### 4. WebApp (Frontend)
Foydalanuvchi uchun zamonaviy va premium dizayndagi interfeys.
- **Qidiruv:** Toshkent, Samarqand va boshqa shaharlar orasida poyezdlarni real vaqtda qidirish.
- **Filtrlar:** O'rin turi (Pastki, Tepadagi, O'tirish) va narx bo'yicha filtrlash.
- **Boshqaruv:** Faol kuzatuvlarni ko'rish, intervalni tahrirlash va o'chirish.

---

## 💰 Monetizatsiya va Premium Tizimi
Bot "Freemium" modelida ishlaydi:
- **Oddiy foydalanuvchi:** Maksimal 2 ta kuzatuv va faqat 60 soniyalik interval.
- **Premium foydalanuvchi:** Cheksiz kuzatuvlar va tezkor (15s, 30s) intervallar. 
- **To'lov:** 1 Star (Yulduz) = 1 kunlik Premium.

---

## 📦 Deployment va Persistence
Loyiha **Railway.app** kabi platformalar uchun optimallashtirilgan.
- **Volume:** Ma'lumotlar o'chib ketmasligi uchun `/data/bot.db` manzili ishlatiladi.
- **Environments:** `BOT_TOKEN`, `WEBAPP_URL`, `ADMIN_ID`, `DB_PATH` kabi o'zgaruvchilar orqali sozlanadi.
