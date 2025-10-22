import yfinance as yf

print("🔍 Veri çekiliyor...")

data = yf.Ticker("THYAO.IS")
df = data.history(period="1d")

print(df)
