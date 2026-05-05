# 🚂 Railway Monitoring Bot - Agent Yo'riqnomasi

Ushbu loyiha O'zbekiston Temir Yo'llari (eticket.railway.uz) uchun chiptalarni monitoring qilish va Telegram bot orqali xabar berish tizimidir.

## 🛠 Texnologik Stek
- **Backend:** Python 3.11+ (`aiogram` bot, `aiohttp` web server, `aiosqlite` ma'lumotlar bazasi)
- **Frontend:** Vanilla HTML5, CSS3, JavaScript (Telegram WebApp API orqali)
- **Avtomatizatsiya:** `Playwright` (Anti-bot cookie yangilash uchun)
- **Video:** `Hls.js` (Jonli TV streaming uchun)

---

## 🏗 Loyiha Arxitekturasi

### 1. Bot Qatlami (`railway_bot.py`)
Bot foydalanuvchilar bilan asosiy muloqotni amalga oshiradi:
- `/start`: WebApp-ni ochadi.
- `/stars`: Premium obuna sotib olish (Telegram Stars).
- `/users` (Admin): Statistikani ko'rish.

### 2. Web Server (API)
WebApp uchun backend xizmatini bajaradi:
- `/api/trains`: Poyezdlarni qidirish.
- `/api/subs`: Monitoring qo'shish, o'chirish va ko'rish.
- `/api/support`: Support chat xabarlari.
- `/api/create_invoice`: Telegram Stars to'lovini yaratish.

### 3. Monitoring (Checker)
`checker()` asinxron funksiyasi orqa fonda har bir foydalanuvchining kuzatuvlarini tekshiradi. Joy topilganda foydalanuvchiga poyezd turi, soni va narxi bilan xabar yuboradi.

### 4. Cookie Refresher (Playwright)
Railway saytining qattiq himoyasini chetlab o'tish uchun `cookie_refresher()` har 20 daqiqada Playwright orqali yangi `laravel_session` va `XSRF-TOKEN` oladi. Bu loyihaning eng muhim qismlaridan biridir.

---

## 📜 Agentlar uchun Qoidalar (Rules)

> [!IMPORTANT]
> Quyidagi qoidalar loyihaning barqarorligini ta'minlash uchun zarur:

1. **Funksionallikni Saqlash:** TV streaming (`tv-section`) va Support Chat (`chat-view`) funksiyalarini hech qachon o'chirib tashlamang. Ular foydalanuvchilarni ushlab turish (retention) uchun muhim.
2. **HLS Player:** `webapp.html` faylidagi `Hls.js` integratsiyasiga tegmaslikka harakat qiling, chunki u maxsus CDN va Safari native qo'llab-quvvatlashi uchun optimallashtirilgan.
3. **Playwright Zaruriyati:** `requirements.txt` va `Dockerfile` fayllaridan Playwright-ni olib tashlamang. Garchi avtomatik sotib olish (booking) o'chirilgan bo'lsa-da, monitoring tizimi ishlashi uchun cookie yangilash (refresher) kerak.
4. **Hiding vs Deleting:** Agar biror bo'lim (masalan, Profil yoki Auto-book) kerak bo'lmasa, uni koddan o'chirib yubormasdan, CSS orqali yashiring (`display: none`). Bu kelajakda funksiyani qayta tiklashni osonlashtiradi.
5. **DB Tranzaksiyalari:** Barcha ma'lumotlar bazasi so'rovlari uchun `aiosqlite` asinxron kutubxonasidan foydalaning va doim `try...except` bloklarida xatolarni boshqaring.
6. **Aesthetics:** WebApp premium va zamonaviy ko'rinishi shart (glassmorphism effekti, animatsiyalar, dark mode).

---

## 📦 Deployment
Loyiha **Railway.app** uchun mo'ljallangan.
- **Dockerfile:** `mcr.microsoft.com/playwright/python` tasviridan foydalanadi.
- **Environment Variables:** `BOT_TOKEN`, `WEBAPP_URL`, `ADMIN_ID` sozlanishi shart.
- **Volume:** `bot.db` fayli saqlanib qolishi uchun Railway-da `/app/data` (yoki default `/app`) papkasiga persistency qo'shilgan bo'liveradi.
