from flask import Flask
from dotenv import load_dotenv
import threading
import requests
import yfinance as yf
import json
import time
import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# === Ortam değişkenlerini yükle ===
load_dotenv()

# === Telegram ayarları ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

ALARMS_FILE = "alarms.json"
CHECK_INTERVAL = 60  # saniye


# === Yardımcı fonksiyonlar ===
def load_alarms():
    try:
        with open(ALARMS_FILE, "r") as f:
            return json.load(f)
    except:
        return []


def save_alarms(alarms):
    with open(ALARMS_FILE, "w") as f:
        json.dump(alarms, f, indent=2)


def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": text})


def get_price(symbol):
    if symbol.endswith("USDT"):
        try:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
            r = requests.get(url, timeout=10).json()
            return float(r["price"])
        except:
            return None
    else:
        try:
            data = yf.Ticker(symbol)
            price = data.history(period="1d")["Close"].iloc[-1]
            return float(price)
        except:
            return None


# === Alarm kontrol fonksiyonu ===
def check_alarms():
    while True:
        alarms = load_alarms()
        for alarm in alarms[:]:
            price = get_price(alarm["symbol"])
            if price is None:
                continue
            if (alarm["direction"] == "above" and price >= alarm["target"]) or \
               (alarm["direction"] == "below" and price <= alarm["target"]):
                send_message(
                    f"🚨 {alarm['symbol']} {alarm['target']} seviyesine ulaştı!\nMesaj: {alarm['message']}\nFiyat: {price}"
                )
                alarms.remove(alarm)
                save_alarms(alarms)
        time.sleep(CHECK_INTERVAL)


# === Telegram komutları ===
async def add_alarm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        symbol = context.args[0].upper()
        target = float(context.args[1])
        direction = "above" if target >= get_price(symbol) else "below"
        message = " ".join(context.args[2:]) if len(context.args) > 2 else ""
        alarms = load_alarms()
        alarms.append({
            "symbol": symbol,
            "target": target,
            "direction": direction,
            "message": message
        })
        save_alarms(alarms)
        await update.message.reply_text(
            f"✅ Alarm eklendi: {symbol} {direction} {target}, mesaj: {message}"
        )
    except Exception:
        await update.message.reply_text(
            "❌ Hata! Kullanım: /alarm_ekle SYMBOL TARGET Mesaj")


async def list_alarms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    alarms = load_alarms()
    if not alarms:
        await update.message.reply_text("📭 Aktif alarm yok.")
    else:
        msg = "🔔 Aktif Alarmlar:\n"
        for a in alarms:
            msg += f"{a['symbol']} {a['direction']} {a['target']} Mesaj: {a['message']}\n"
        await update.message.reply_text(msg)


async def remove_alarm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        symbol = context.args[0].upper()
        alarms = [a for a in load_alarms() if a["symbol"] != symbol]
        save_alarms(alarms)
        await update.message.reply_text(f"🗑️ {symbol} alarmları silindi.")
    except:
        await update.message.reply_text("❌ Hata! Kullanım: /alarm_sil SYMBOL")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 **Fiyat Alarm Botu Kullanım Kılavuzu**\n\n"
        "Bu bot ile kripto paralar, Borsa İstanbul hisseleri, ABD hisseleri ve değerli emtialar için fiyat alarmı oluşturabilirsiniz.\n\n"
        "**Komutlar:**\n"
        "/alarm_ekle SYMBOL TARGET Mesaj\n"
        "  - Alarm ekler.\n"
        "  - Örnek: /alarm_ekle BTCUSDT 150000 Acil sat\n\n"
        "/alarm_listele\n"
        "  - Mevcut tüm aktif alarmları listeler.\n\n"
        "/alarm_sil SYMBOL\n"
        "  - Belirtilen sembole ait alarmı siler.\n"
        "  - Örnek: /alarm_sil BTCUSDT\n\n"
        "/help\n"
        "  - Bu yardım mesajını gösterir.\n\n"
        "**Notlar:**\n"
        "- Kripto paralar: Binance sembolü (BTCUSDT, ETHUSDT, vb.)\n"
        "- Borsa İstanbul hisseleri: Yahoo Finance formatı (THYAO.IS, ASELS.IS, vb.)\n"
        "- ABD hisseleri: Yahoo Finance formatı (AAPL, TSLA, vb.)\n"
        "- Emtialar: Yahoo Finance sembolü (XAUUSD, XAGUSD, CL=F, vb.)\n"
        "- Fiyat kontrolü her 1 dakikada bir yapılır.\n"
        "- Alarm tetiklendiğinde mesaj içeriği ile birlikte Telegram’a gönderilir."
    )
    await update.message.reply_text(help_text)


# === Yeni: Web arayüzü butonu ===
async def web_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Buraya kendi URL’ini koy (ngrok veya sunucu linkin)
    web_url = "https://7df5e175-45d0-426c-bc51-31463e91adce-00-wnyb5jz19m0o.sisko.replit.dev/"
    keyboard = [[
        InlineKeyboardButton("🌐 Web Uygulamasını Aç",
                             web_app=WebAppInfo(url=web_url))
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Web arayüzünü açmak için aşağıdaki butona tıkla 👇",
        reply_markup=reply_markup)


# === Telegram botu başlat ===
def start_bot():
    threading.Thread(target=check_alarms, daemon=True).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("alarm_ekle", add_alarm))
    app.add_handler(CommandHandler("alarm_listele", list_alarms))
    app.add_handler(CommandHandler("alarm_sil", remove_alarm))
    app.add_handler(CommandHandler("web", web_command))
    print("🤖 Telegram botu çalışıyor...")
    app.run_polling()


# === Flask (UptimeRobot + WebApp için) ===
app_flask = Flask(__name__)


@app_flask.route('/')
def home():
    return "<h2>Bot aktif 🚀</h2><p>Web Arayüzüne hoş geldin!</p>"


def run_flask():
    app_flask.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)


# === Ana başlatma ===
if __name__ == "__main__":
    # Flask sunucusunu ayrı bir thread olarak başlat
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # 3 saniye bekle, sonra Replit linkini al ve yazdır
    time.sleep(3)
    print("🌐 Flask web arayüzü aktif. Aşağıdaki linki kopyala:")
    print("➡️  https://" + os.getenv("REPL_SLUG") + "." +
          os.getenv("REPL_OWNER") + ".repl.co")

    # Telegram botunu başlat
    start_bot()
