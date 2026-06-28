import os
from dotenv import load_dotenv

load_dotenv()

MT5_HOST = os.getenv("MT5_HOST") or "mt5-service"
MT5_PORT = int(os.getenv("MT5_PORT") or "8001")
MT5_LOGIN = int(os.getenv("MT5_LOGIN") or "0")
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

BALANCE_AWAL = float(os.getenv("BALANCE_AWAL") or "100")
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE") or "1.0")
TARGET_RR = float(os.getenv("TARGET_RR") or "4.0")
TP1_RR    = float(os.getenv("TP1_RR") or "1.5")
MAX_LOSS_PER_DAY = float(os.getenv("MAX_LOSS_PER_DAY") or "3.0")
MAX_DRAWDOWN = float(os.getenv("MAX_DRAWDOWN") or "15.0")
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES") or "2")
MIN_LOT = float(os.getenv("MIN_LOT") or "0.01")
MAX_LOT = float(os.getenv("MAX_LOT") or "0.05")
SPREAD_FILTER = int(os.getenv("SPREAD_FILTER") or "80")

MT5_MAGIC = int(os.getenv("MT5_MAGIC") or "12345")
MT5_DEVIATION = int(os.getenv("MT5_DEVIATION") or "20")

NEWS_BLACKOUT_BEFORE = int(os.getenv("NEWS_BLACKOUT_BEFORE") or "30")  # menit sebelum berita
NEWS_BLACKOUT_AFTER = int(os.getenv("NEWS_BLACKOUT_AFTER") or "15")    # menit setelah berita

SYMBOL = "XAUUSD"
POLL_INTERVAL_SECONDS = 2

# (start_hour, start_min, end_hour, end_min) — WIB (UTC+7)
# London Breakout window: order placement + monitoring
ACTIVE_HOURS = [
    (14, 50, 17, 0),
]

# London Breakout Strategy
ASIAN_RANGE_START  = (7, 0)    # (hour, minute) WIB — Asian session range begins
ASIAN_RANGE_END    = (14, 0)   # (hour, minute) WIB — Asian session range ends
ORDERS_PLACE_TIME  = (14, 50)  # (hour, minute) WIB — place pending orders
ORDERS_EXPIRY_TIME = (17, 0)   # (hour, minute) WIB — cancel unfilled pending orders

RANGE_MIN_USD        = float(os.getenv("RANGE_MIN_USD",        "5.0"))   # skip if range < $5
RANGE_MAX_USD        = float(os.getenv("RANGE_MAX_USD",        "25.0"))  # skip if range > $25
BREAKOUT_BUFFER_USD  = float(os.getenv("BREAKOUT_BUFFER_USD",  "0.5"))   # entry buffer beyond range edge
SL_BUFFER_USD        = float(os.getenv("SL_BUFFER_USD",        "0.3"))   # SL buffer beyond opposite edge
TP_RR_BREAKOUT       = float(os.getenv("TP_RR_BREAKOUT",       "1.5"))   # TP = range × TP_RR from entry
