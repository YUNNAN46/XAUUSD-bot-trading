import os
from dotenv import load_dotenv

load_dotenv()

MT5_HOST = os.getenv("MT5_HOST") or "mt5-service"
MT5_PORT = int(os.getenv("MT5_PORT") or "8001")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

BALANCE_AWAL = float(os.getenv("BALANCE_AWAL") or "100")
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE") or "1.0")
TARGET_RR = float(os.getenv("TARGET_RR") or "2.0")
MAX_LOSS_PER_DAY = float(os.getenv("MAX_LOSS_PER_DAY") or "3.0")
MAX_DRAWDOWN = float(os.getenv("MAX_DRAWDOWN") or "15.0")
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES") or "2")
MIN_LOT = float(os.getenv("MIN_LOT") or "0.01")
MAX_LOT = float(os.getenv("MAX_LOT") or "0.05")
SPREAD_FILTER = int(os.getenv("SPREAD_FILTER") or "80")

MT5_MAGIC = int(os.getenv("MT5_MAGIC") or "12345")
MT5_DEVIATION = int(os.getenv("MT5_DEVIATION") or "20")

SYMBOL = "XAUUSD"
POLL_INTERVAL_SECONDS = 2

# (start_hour, start_min, end_hour, end_min) — WIB (UTC+7)
ACTIVE_HOURS = [
    (14, 0, 17, 0),
    (19, 0, 23, 0),
]
