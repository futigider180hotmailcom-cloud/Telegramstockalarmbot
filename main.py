    )
    await update.message.reply_text(help_text)


# === Yeni: Web arayÃ¼zÃ¼ butonu ===
async def web_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Buraya kendi URLâ€™ini koy (ngrok veya sunucu linkin)
    web_url = "https://7df5e175-45d0-426c-bc51-31463e91adce-00-wnyb5jz19m0o.sisko.replit.dev/"
    keyboard = [[
        InlineKeyboardButton("ğŸŒ Web UygulamasÄ±nÄ± AÃ§",
                             web_app=WebAppInfo(url=web_url))
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Web arayÃ¼zÃ¼nÃ¼ aÃ§mak iÃ§in aÅŸaÄŸÄ±daki butona tÄ±kla ğŸ‘‡",
        reply_markup=reply_markup)


# === Telegram botu baÅŸlat ===
def start_bot():
    threading.Thread(target=check_alarms, daemon=True).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("alarm_ekle", add_alarm))
    app.add_handler(CommandHandler("alarm_listele", list_alarms))
    app.add_handler(CommandHandler("alarm_sil", remove_alarm))
    app.add_handler(CommandHandler("web", web_command))
    print("ğŸ¤– Telegram botu Ã§alÄ±ÅŸÄ±yor...")
    app.run_polling()


# === Flask (UptimeRobot + WebApp iÃ§in) ===
app_flask = Flask(__name__)


@app_flask.route('/')
def home():
    return "<h2>Bot aktif ğŸš€</h2><p>Web ArayÃ¼zÃ¼ne hoÅŸ geldin!</p>"


def run_flask():
    app_flask.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)


# === Ana baÅŸlatma ===
if __name__ == "__main__":
    # Flask sunucusunu ayrÄ± bir thread olarak baÅŸlat
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # 3 saniye bekle, sonra Replit linkini al ve yazdÄ±r
    time.sleep(3)
    print("ğŸŒ Flask web arayÃ¼zÃ¼ aktif. AÅŸaÄŸÄ±daki linki kopyala:")
    print("â¡ï¸  https://" + os.getenv("REPL_SLUG") + "." +
          os.getenv("REPL_OWNER") + ".repl.co")

    # Telegram botunu baÅŸlat
    start_bot()
