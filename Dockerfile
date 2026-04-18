# Playwright uchun maxsus tayyorlangan Python tasviri
# Bu barcha kerakli Linux kutubxonalari va shriftlarni o'z ichiga olgan
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# Ishchi katalogni belgilaymiz
WORKDIR /app

# Avval requirements.txt ni ko'chirib, o'rnatamiz (Cache bo'lishi uchun)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Qolgan barcha fayllarni ko'chiramiz
COPY . .

# Railway uchun PORT sozlamasi
ENV PORT=8080

# Botni ishga tushiramiz
CMD ["python", "railway_bot.py"]
