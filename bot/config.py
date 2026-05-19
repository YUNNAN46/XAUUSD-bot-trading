import os
from dotenv import load_dotenv

load_dotenv()

MT5_HOST = os.getenv("MT5_HOST", "mt5-service")
MT5_PORT = int(os.getenv("MT5_PORT", "8001"))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

BALANCE_AWAL = float(os.getenv("BALANCE_AWAL", "100"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "1.0"))
TARGET_RR = float(os.getenv("TARGET_RR", "2.0"))
MAX_LOSS_PER_DAY = float(os.getenv("MAX_LOSS_PER_DAY", "3.0"))
MAX_DRAWDOWN = float(os.getenv("MAX_DRAWDOWN", "15.0"))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", "2"))
MIN_LOT = float(os.getenv("MIN_LOT", "0.01"))
MAX_LOT = float(os.getenv("MAX_LOT", "0.05"))
SPREAD_FILTER = int(os.getenv("SPREAD_FILTER", "80"))

SYMBOL = "XAUUSD"
POLL_INTERVAL_SECONDS = 5

# (start_hour, start_min, end_hour, end_min) — WIB (UTC+7)
ACTIVE_HOURS = [
    (14, 0, 17, 0),
    (19, 0, 23, 0),
]
