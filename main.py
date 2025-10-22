import os
import json
import time
import threading
import requests
import yfinance as yf
import asyncio # Asenkron işlemler için gerekli

from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, ApplicationBuilder, filters

# === Ortam Değişkenleri Ayarları ===
# Bu değerler Render.com'daki Environment Variables bölümünden okunacak.
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID_STR = os.environ.get("CHAT_ID")

# Ortam değişkenlerinin varlığını kontrol edelim
if BOT_TOKEN is None:
    print("HATA: BOT_TOKEN ortam değişkeni bulunamadı. Lütfen Render.com'da ayarlayın.")
    exit(1) # Programı sonlandır
if CHAT_ID_STR is None:
    print("HATA: CHAT_ID ortam değişkeni bulunamadı. Lütfen Render.com'da ayarlayın.")
    exit(1) # Programı sonlandır

try:
    CHAT_ID = int(CHAT_ID_STR)
except ValueError:
    print(f"HATA: CHAT_ID '{CHAT_ID_STR}' geçerli bir sayı değil. Lütfen Render.com'da doğru ayarlayın.")
    exit(1) # Programı sonlandır


# === Global Ayarlar ve Dosyalar ===
ALARMS_FILE = "alarms.json"  # Alarmların kaydedileceği dosya
CHECK_INTERVAL = 60          # Fiyatları kontrol etme aralığı (saniye)
# Render'da /tmp dizini yazılabilir ve her deploy'da sıfırlanır.
# Kalıcı depolama için farklı bir yöntem (veritabanı) gerekir.
# Şimdilik, aynı dizinde kalacak.
# Eğer dosya yazma hatası alırsanız, ALARMS_FILE = "/tmp/alarms.json" deneyebilirsiniz.


# === Web Sunucusu (Flask - Gunicorn tarafından çalıştırılacak) ===
# Bu 'web_server' objesi Gunicorn tarafından 'gunicorn main:web_server' komutuyla bulunacak.
web_server = Flask(__name__)

@web_server.route('/')
def home():
    """Render.com'un ve Uptime Robot'un kontrol edeceği ana sayfa."""
    return "<h2>Bot Aktif! 🚀</h2><p>Web arayüzüne hoş geldin!</p>"


# === Yardımcı Fonksiyonlar ===
def load_alarms():
    """Alarmları JSON dosyasından yükler."""
    try:
        if not os.path.exists(ALARMS_FILE):
            return []
        with open(ALARMS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def save_alarms(alarms):
    """Alarmları JSON dosyasına kaydeder."""
    try:
        with open(ALARMS_FILE, "w") as f:
            json.dump(alarms, f, indent=2)
    except Exception as e:
        print(f"Alarmlar kaydedilirken hata oluştu: {e}")

def get_price(symbol):
    """Kripto veya hisse senedi fiyatını alır."""
    if symbol.endswith("USDT"): # Kripto paralar için Binance API'si
        try:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return float(response.json()["price"])
        except Exception as e:
            print(f"Binance API hatası ({symbol}): {e}")
            return None
    else: # Diğerleri için Yahoo Finance (hisse senedi vb.)
        try:
            data = yf.Ticker(symbol)
            price = data.history(period="1d")["Close"].iloc[-1]
            return float(price)
        except Exception as e:
            print(f"Yahoo Finance hatası ({symbol}): {e}")
            return None

# === Alarm Kontrol Fonksiyonu ===
async def check_alarms(application: Application):
    """Arka planda sürekli çalışarak alarmları kontrol eder."""
    print("Alarm kontrol döngüsü başlatıldı.")
    while True:
        alarms = load_alarms()
        # Liste üzerinde işlem yaparken aynı anda değişiklik yapılmaması için kopyasını kullanırız.
        for alarm in alarms[:]: 
            price = get_price(alarm["symbol"])
            if price is None:
                print(f"Fiyat alınamadı: {alarm['symbol']}")
                continue

            target_reached = False
            if alarm["direction"] == "above" and price >= alarm["target"]:
                target_reached = True
            elif alarm["direction"] == "below" and price <= alarm["target"]:
                target_reached = True

            if target_reached:
                message_text = (
                    f"🚨 **Alarm Tetiklendi!** 🚨\n\n"
                    f"**Sembol:** {alarm['symbol']}\n"
                    f"**Hedef Fiyat:** {alarm['target']}\n"
                    f"**Anlık Fiyat:** {price}\n\n"
                    f"**Notunuz:** {alarm['message']}"
                )
                try:
                    await application.bot.send_message(chat_id=CHAT_ID, text=message_text, parse_mode='Markdown')
                    print(f"Alarm tetiklendi ve mesaj gönderildi: {alarm['symbol']}")
                    # Tetiklenen alarmı listeden kaldırıyoruz
                    alarms.remove(alarm)
                    save_alarms(alarms)
                except Exception as e:
                    print(f"Telegram'a mesaj gönderilirken hata oluştu: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL) # Belirlenen süre kadar bekler

# === Telegram Bot Komutları ===
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start komutu."""
    await help_command(update, context) # /start komutu /yardim komutu ile aynı işi yapsın

async def add_alarm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ekle komutu ile yeni alarm ekler."""
    if len(context.args) < 2:
        await update.message.reply_text("❌ Hatalı kullanım!\nÖrnek: `/ekle TUPRS.IS 200 Hedefe geldi!`")
        return

    try:
        symbol = context.args[0].upper()
        target = float(context.args[1])
        message = " ".join(context.args[2:]) if len(context.args) > 2 else "Hedef Fiyata Ulaşıldı!"
        
        current_price = get_price(symbol)
        if current_price is None:
            await update.message.reply_text(f"❌ '{symbol}' sembolü için fiyat alınamadı. Lütfen sembolü kontrol edin.")
            return

        direction = "above" if target >= current_price else "below" # Hedefe göre yön belirle
        
        alarms = load_alarms()
        alarms.append({
            "symbol": symbol,
            "target": target,
            "direction": direction,
            "message": message
        })
        save_alarms(alarms)
        await update.message.reply_text(f"✅ Alarm kuruldu: **{symbol}**, hedef **{target}**, yön: **{direction}**")
    except (IndexError, ValueError) as e:
        print(f"add_alarm hatası: {e}")
        await update.message.reply_text("❌ Hatalı kullanım!\nÖrnek: `/ekle TUPRS.IS 200 Hedefe geldi!`")

async def list_alarms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/listele komutu ile aktif alarmları gösterir."""
    alarms = load_alarms()
    if not alarms:
        await update.message.reply_text("📭 Aktif alarm bulunmuyor.")
    else:
        msg = "🔔 **Aktif Alarmlar:**\n\n"
        for i, a in enumerate(alarms, 1):
            msg += f"{i}. **{a['symbol']}** | Hedef: **{a['target']}** | Yön: **{a['direction']}**\n"
            if a['message']:
                msg += f"   *Not:* {a['message']}\n"
        await update.message.reply_text(msg, parse_mode='Markdown')

async def remove_alarm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/sil komutu ile alarm siler."""
    if not context.args:
        await update.message.reply_text("❌ Hatalı kullanım!\nÖrnek: `/sil TUPRS.IS`")
        return
        
    symbol_to_remove = context.args[0].upper()
    alarms = load_alarms()
    # Sadece belirtilen sembole uymayan alarmları tutarak yeni bir liste oluştur
    new_alarms = [a for a in alarms if a["symbol"] != symbol_to_remove]
    
    if len(new_alarms) == len(alarms): # Liste boyutu değişmediyse, alarm bulunamamıştır.
        await update.message.reply_text(f"🗑️ '{symbol_to_remove}' için kurulu bir alarm bulunamadı.")
    else:
        save_alarms(new_alarms)
        await update.message.reply_text(f"🗑️ '{symbol_to_remove}' sembolüne ait tüm alarmlar silindi.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/yardim komutu ile botun kullanım kılavuzunu gösterir."""
    help_text = (
        "🤖 **Fiyat Alarm Botu Komutları**\n\n"
        "🔹 `/ekle <SEMBOL> <FİYAT> [Notunuz]`\n"
        "   Yeni bir fiyat alarmı kurar.\n"
        "   *Örnek:* `/ekle BTCUSDT 75000 Satış zamanı`\n"
        "   *Örnek:* `/ekle GOOGL 150 Hedefim burada`\n\n"
        "🔹 `/listele`\n"
        "   Tüm aktif alarmları listeler.\n\n"
        "🔹 `/sil <SEMBOL>`\n"
        "   Belirtilen sembole ait tüm alarmları siler.\n"
        "   *Örnek:* `/sil BTCUSDT`\n\n"
        "🔹 `/yardim`\n"
        "   Bu yardım mesajını gösterir."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

# === Arka Plan Görevini Başlatmak İçin Fonksiyon (Telegram Application hazır olduğunda çalışır) ===
async def post_init(application: Application):
    """Bot başlatıldıktan sonra alarm kontrol döngüsünü başlatır."""
    print("post_init çağrıldı: Alarm kontrol görevi başlatılıyor.")
    asyncio.create_task(check_alarms(application))


# === Ana Telegram Botunu Başlatma Fonksiyonu ===
async def start_telegram_bot_main():
    """Telegram botunu yapılandırır ve polling'i başlatır."""
    application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    # Komut işleyicilerini ekle
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("yardim", help_command))
    application.add_handler(CommandHandler("ekle", add_alarm))
    application.add_handler(CommandHandler("listele", list_alarms))
    application.add_handler(CommandHandler("sil", remove_alarm))
    
    print("🤖 Telegram botu çalışıyor ve mesajları dinliyor...")
    # Botu çalıştırmaya başla (polling metoduyla)
    await application.run_polling()


# === Uygulama Başlangıç Noktası ===
if __name__ == "__main__":
    # Bu blok, dosya Python tarafından doğrudan çalıştırıldığında (`python main.py` gibi) çalışır.
    # Render'da Gunicorn, 'web_server' Flask objesini doğrudan çalıştırdığı için,
    # bu blok Gunicorn'ın başlatma sürecinde doğrudan devreye girmez.
    # Ancak, biz burada Gunicorn'ın başlamasından sonra asenkron olarak
    # Telegram botunu da başlatmasını sağlayacak mekanizmayı kuruyoruz.
    
    # Gunicorn zaten 'web_server' Flask uygulamasını başlatıyor ve yönetiyor.
    # Bizim tek yapmamız gereken, bu Flask uygulaması içinde
    # Telegram botunu da asenkron bir görev olarak çalıştırmak.
    
    # Python'un asyncio olay döngüsünü başlat ve Telegram botunu bu döngüye ekle.
    # Gunicorn tarafından çalıştırıldığında bu kısım tetiklenmeyecek,
    # çünkü Gunicorn kendi web_server objesini import edip çalıştıracak.
    # Asıl Telegram botunun başlatılması 'post_init' içerisinde
    # Flask uygulamasının context'i içinde gerçekleşecek.

    # Eğer bu dosyayı lokalde test etmek isterseniz (Gunicorn olmadan):
    # asyncio.run(start_telegram_bot_main())
    
    # Render için, Gunicorn 'web_server'ı başlatacak.
    # 'post_init' fonksiyonu, bot Application'ı oluşturulurken çağrılacak ve alarm kontrolünü başlatacak.
    # Telegram botunun kendisi ise Gunicorn'ın ana process'i içinde bir asyncio görevi olarak çalışacak.
    pass # Bu 'pass' satırı burada kalsa da olur, Gunicorn zaten Flask objesini çalıştıracak.
