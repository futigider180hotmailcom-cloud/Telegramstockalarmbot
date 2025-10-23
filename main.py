import os
import threading
import asyncio
import time
import requests
import yfinance as yf
from flask import Flask, render_template, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# === Flask Web Arayüzü === #
app = Flask(__name__)

alarmlar = {}  # { "kullanici_id": [{"sembol": "AAPL", "fiyat": 200.0, "yon": "üst"}] }

@app.route("/")
def home():
    return render_template("index.html", alarmlar=alarmlar)

@app.route("/ekle", methods=["POST"])
def ekle():
    sembol = request.form["sembol"].upper()
    fiyat = float(request.form["fiyat"])
    yon = request.form["yon"]
    kullanici = request.form["kullanici"]
    if kullanici not in alarmlar:
        alarmlar[kullanici] = []
    alarmlar[kullanici].append({"sembol": sembol, "fiyat": fiyat, "yon": yon})
    return f"<h3>{kullanici} için alarm eklendi: {sembol} {fiyat} ({yon})</h3>"

@app.route("/liste")
def liste():
    return str(alarmlar)

def run_flask():
    app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)


# === Telegram Bot === #

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📈 Hoş geldin! Alarm kurmak için /alarm_ekle komutunu kullan!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "/start - Başlat\n"
        "/alarm_ekle - Alarm ekle (örnek: /alarm_ekle AAPL 200 üst)\n"
        "/alarm_listele - Alarm listeni gör\n"
        "/alarm_sil - Alarm sil (örnek: /alarm_sil AAPL)\n"
    )
    await update.message.reply_text(text)

async def alarm_ekle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        sembol = context.args[0].upper()
        fiyat = float(context.args[1])
        yon = context.args[2]
        user = str(update.effective_user.id)
        if user not in alarmlar:
            alarmlar[user] = []
        alarmlar[user].append({"sembol": sembol, "fiyat": fiyat, "yon": yon})
        await update.message.reply_text(f"✅ Alarm eklendi: {sembol} {fiyat} ({yon})")
    except Exception:
        await update.message.reply_text("❌ Kullanım: /alarm_ekle Sembol Fiyat üst/alt")

async def alarm_listele(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = str(update.effective_user.id)
    if user not in alarmlar or not alarmlar[user]:
        await update.message.reply_text("📭 Henüz alarmın yok.")
        return
    text = "\n".join([f"{a['sembol']} {a['fiyat']} ({a['yon']})" for a in alarmlar[user]])
    await update.message.reply_text("🔔 Alarmların:\n" + text)

async def alarm_sil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        sembol = context.args[0].upper()
        user = str(update.effective_user.id)
        if user in alarmlar:
            alarmlar[user] = [a for a in alarmlar[user] if a["sembol"] != sembol]
        await update.message.reply_text(f"🗑️ {sembol} alarmı silindi.")
    except Exception:
        await update.message.reply_text("❌ Kullanım: /alarm_sil Sembol")


# === Alarm kontrol fonksiyonu === #
def check_alarms():
    while True:
        for user, liste in list(alarmlar.items()):
            for alarm in liste:
                try:
                    data = yf.Ticker(alarm["sembol"]).history(period="1d")
                    if data.empty:
                        continue
                    current = data["Close"].iloc[-1]
                    hedef = alarm["fiyat"]
                    if alarm["yon"] == "üst" and current >= hedef:
                        send_message(user, f"🚀 {alarm['sembol']} {hedef}$ seviyesinin ÜSTÜNE çıktı! ({current}$)")
                        liste.remove(alarm)
                    elif alarm["yon"] == "alt" and current <= hedef:
                        send_message(user, f"📉 {alarm['sembol']} {hedef}$ seviyesinin ALTINA indi! ({current}$)")
                        liste.remove(alarm)
                except Exception as e:
                    print("Hata:", e)
        time.sleep(30)

def send_message(chat_id, text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": chat_id, "text": text}
        )
    except Exception as e:
        print("Mesaj gönderilemedi:", e)


# === Uygulama Başlat === #
if __name__ == "__main__":
    # Flask web sunucusunu ayrı thread’de başlat
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Render dış bağlantı adresi
    url = os.getenv("RENDER_EXTERNAL_URL") or "http://localhost:8080"
    print(f"🌐 Flask web arayüzü aktif. Aşağıdaki linki kopyala:\n➡️  {url}")

    # Telegram botunu asenkron başlat
    async def start_async_bot():
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("alarm_ekle", alarm_ekle))
        app.add_handler(CommandHandler("alarm_listele", alarm_listele))
        app.add_handler(CommandHandler("alarm_sil", alarm_sil))

        threading.Thread(target=check_alarms, daemon=True).start()
        print("🤖 Telegram botu çalışıyor...")

        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()  # Sonsuza kadar açık kal

    asyncio.run(start_async_bot())
