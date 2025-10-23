
 from flask import Flask
 from dotenv import load_dotenv
 import threading
 import requests
 import yfinance as yf
 import json
 import time
 import os
 import asyncio
 from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
 from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
 
 # === Ortam değişkenlerini yükle ===
 load_dotenv()
 
 # === Telegram ayarları ===
 BOT_TOKEN = os.getenv("BOT_TOKEN")
-CHAT_ID = int(os.getenv("CHAT_ID"))
+
+chat_id_raw = os.getenv("CHAT_ID")
+CHAT_ID = None
+
+try:
+    if chat_id_raw:
+        CHAT_ID = int(chat_id_raw)
+except (TypeError, ValueError):
+    print("⚠️  CHAT_ID ortam değişkeni bir tam sayı olmalıdır.")
+    CHAT_ID = None
+
+TELEGRAM_ENABLED = True
+
+if not BOT_TOKEN:
+    print("⚠️  BOT_TOKEN ortam değişkeni bulunamadı. Telegram botu başlatılmayacak.")
+    TELEGRAM_ENABLED = False
+
+if CHAT_ID is None:
+    print("⚠️  CHAT_ID ortam değişkeni geçerli değil. Telegram botu başlatılmayacak.")
+    TELEGRAM_ENABLED = False
 
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
+    if not TELEGRAM_ENABLED:
+        print(f"📭 Telegram devre dışı: {text}")
+        return
+
     url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
-    requests.post(url, json={"chat_id": CHAT_ID, "text": text})
+    try:
+        requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=10)
+    except requests.RequestException as exc:
+        print(f"❌ Telegram mesajı gönderilemedi: {exc}")
 
 
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
-        direction = "above" if target >= get_price(symbol) else "below"
+        current_price = get_price(symbol)
+
+        if current_price is None:
+            await update.message.reply_text("❌ Sembol fiyatı alınamadı. Lütfen tekrar deneyin.")
+            return
+
+        direction = "above" if target >= current_price else "below"
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
@@ -137,61 +169,72 @@ async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
         "**Notlar:**\n"
         "- Kripto paralar: Binance sembolü (BTCUSDT, ETHUSDT, vb.)\n"
         "- Borsa İstanbul hisseleri: Yahoo Finance formatı (THYAO.IS, ASELS.IS, vb.)\n"
         "- ABD hisseleri: Yahoo Finance formatı (AAPL, TSLA, vb.)\n"
         "- Emtialar: Yahoo Finance sembolü (XAUUSD, XAGUSD, CL=F, vb.)\n"
         "- Fiyat kontrolü her 1 dakikada bir yapılır.\n"
         "- Alarm tetiklendiğinde mesaj içeriği ile birlikte Telegram’a gönderilir."
     )
     await update.message.reply_text(help_text)
 
 
 async def web_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
     web_url = "https://telegramstockalarmbot.onrender.com/"
     keyboard = [[
         InlineKeyboardButton("🌐 Web Uygulamasını Aç",
                              web_app=WebAppInfo(url=web_url))
     ]]
     reply_markup = InlineKeyboardMarkup(keyboard)
     await update.message.reply_text(
         "Web arayüzünü açmak için aşağıdaki butona tıkla 👇",
         reply_markup=reply_markup)
 
 
 # === Telegram botu başlat ===
 async def start_bot_async():
+    if not TELEGRAM_ENABLED:
+        print("⚠️  Telegram botu devre dışı bırakıldı. Ortam değişkenlerini kontrol edin.")
+        return
+
     threading.Thread(target=check_alarms, daemon=True).start()
     app = ApplicationBuilder().token(BOT_TOKEN).build()
     app.add_handler(CommandHandler("help", help_command))
     app.add_handler(CommandHandler("alarm_ekle", add_alarm))
     app.add_handler(CommandHandler("alarm_listele", list_alarms))
     app.add_handler(CommandHandler("alarm_sil", remove_alarm))
     app.add_handler(CommandHandler("web", web_command))
     print("🤖 Telegram botu çalışıyor...")
     await app.run_polling()
 
 
 # === Flask (UptimeRobot + Render için) ===
 app_flask = Flask(__name__)
 
 
 @app_flask.route('/')
 def home():
     return "<h2>Bot aktif 🚀</h2><p>Web Arayüzüne hoş geldin!</p>"
 
 
 def run_flask():
-    app_flask.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)
+    port_str = os.getenv("PORT", "8080")
+    try:
+        port = int(port_str)
+    except ValueError:
+        print(f"⚠️  PORT ortam değişkeni geçersiz ('{port_str}'). Varsayılan 8080 kullanılacak.")
+        port = 8080
+
+    app_flask.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
 
 
 # === Ana başlatma ===
 if __name__ == "__main__":
     # Flask'ı ayrı bir thread'de çalıştır
     flask_thread = threading.Thread(target=run_flask, daemon=True)
     flask_thread.start()
 
     # Telegram botunu ayrı thread'de çalıştır
     threading.Thread(target=lambda: asyncio.run(start_bot_async()), daemon=True).start()
 
     # Render ortamı botu kapatmasın diye ana thread açık kalır
     while True:
         time.sleep(60)
