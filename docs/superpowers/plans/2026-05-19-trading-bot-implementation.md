# XAU/USD Copy Trading Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bangun bot copy trading XAU/USD yang jalan di Docker, konek ke MT5 via mt5linux, filter trade dengan money management ketat, dan kirim alert Telegram real-time.

**Architecture:** MT5 terminal (Wine container) subscribe ke signal provider dan auto-copy trade ke akun Exness. Bot Python memantau posisi setiap 5 detik, menutup posisi yang tidak lolos filter (jam, spread, daily loss), menyesuaikan TP sesuai RR 1:2, dan mengirim notifikasi Telegram.

**Tech Stack:** Python 3.11, mt5linux (RPyC), python-telegram-bot 20+, Docker Compose, pytest, pytz, python-dotenv

---

## File Structure

```
bot-trading/
├── docker-compose.yml
├── .env                         ← credentials (tidak di-commit)
├── .env.example                 ← template kredensial
└── bot/
    ├── Dockerfile
    ├── requirements.txt
    ├── config.py                ← semua konstanta dari env vars
    ├── logger.py                ← setup logging
    ├── money_management.py      ← kalkulasi lot, TP, cek limit
    ├── trade_filter.py          ← jam trading, spread, daily loss
    ├── mt5_connector.py         ← wrapper MT5 via mt5linux
    ├── signal_watcher.py        ← deteksi posisi baru, kelola bot
    ├── telegram_alert.py        ← kirim pesan + handler commands
    ├── main.py                  ← entry point, orchestration
    └── tests/
        ├── conftest.py
        ├── test_money_management.py
        ├── test_trade_filter.py
        ├── test_mt5_connector.py
        └── test_signal_watcher.py
```

---

## Task 1: Infrastructure — Docker & Config Files

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `bot/Dockerfile`
- Create: `bot/requirements.txt`

- [ ] **Step 1: Inisialisasi git**

```bash
cd "E:\DOCKER BACKUP\claude project\bot-trading"
git init
echo ".env" > .gitignore
echo "__pycache__/" >> .gitignore
echo "*.pyc" >> .gitignore
echo "bot.log" >> .gitignore
```

- [ ] **Step 2: Buat `docker-compose.yml`**

```yaml
services:
  mt5-service:
    image: gmag11/metatrader5:latest
    environment:
      - MT5_LOGIN=${MT5_LOGIN}
      - MT5_PASSWORD=${MT5_PASSWORD}
      - MT5_SERVER=${MT5_SERVER}
      - MT5_RPYC_PORT=8001
    ports:
      - "8001:8001"
      - "3000:3000"
    volumes:
      - mt5-data:/root/.metatrader5
    restart: unless-stopped

  bot-service:
    build: ./bot
    depends_on:
      - mt5-service
    env_file: .env
    volumes:
      - ./bot:/app
    restart: unless-stopped

volumes:
  mt5-data:
```

- [ ] **Step 3: Buat `.env.example`**

```env
# MT5 Credentials (Exness)
MT5_LOGIN=123456789
MT5_PASSWORD=your_password
MT5_SERVER=Exness-MT5Real

# MT5 Connection
MT5_HOST=mt5-service
MT5_PORT=8001

# Telegram
TELEGRAM_TOKEN=your_bot_token_from_botfather
TELEGRAM_CHAT_ID=your_chat_id

# Money Management
BALANCE_AWAL=100
RISK_PER_TRADE=1.0
TARGET_RR=2.0
MAX_LOSS_PER_DAY=3.0
MAX_DRAWDOWN=15.0
MAX_OPEN_TRADES=2
MIN_LOT=0.01
MAX_LOT=0.05
SPREAD_FILTER=80
```

- [ ] **Step 4: Salin `.env.example` ke `.env` dan isi kredensial nyata**

```bash
copy .env.example .env
```

- [ ] **Step 5: Buat `bot/Dockerfile`**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

- [ ] **Step 6: Buat `bot/requirements.txt`**

```
mt5linux==0.3.4
python-telegram-bot==20.7
python-dotenv==1.0.0
pytz==2024.1
pytest==7.4.4
pytest-asyncio==0.23.3
```

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml .env.example .gitignore bot/Dockerfile bot/requirements.txt
git commit -m "feat: add docker infrastructure and requirements"
```

---

## Task 2: Config & Logger

**Files:**
- Create: `bot/config.py`
- Create: `bot/logger.py`
- Create: `bot/tests/__init__.py`
- Create: `bot/tests/conftest.py`

- [ ] **Step 1: Buat `bot/config.py`**

```python
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

# (start_hour, start_min, end_hour, end_min) — WIB
ACTIVE_HOURS = [
    (14, 0, 17, 0),
    (19, 0, 23, 0),
]
```

- [ ] **Step 2: Buat `bot/logger.py`**

```python
import logging
import sys

def setup_logger(log_file: str = "bot.log"):
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file),
        ],
    )
```

- [ ] **Step 3: Buat `bot/tests/__init__.py`** (kosong)

- [ ] **Step 4: Buat `bot/tests/conftest.py`**

```python
import os
import pytest

@pytest.fixture(autouse=True)
def set_test_env(monkeypatch):
    monkeypatch.setenv("MT5_HOST", "localhost")
    monkeypatch.setenv("MT5_PORT", "8001")
    monkeypatch.setenv("BALANCE_AWAL", "100")
    monkeypatch.setenv("RISK_PER_TRADE", "1.0")
    monkeypatch.setenv("TARGET_RR", "2.0")
    monkeypatch.setenv("MAX_LOSS_PER_DAY", "3.0")
    monkeypatch.setenv("MAX_DRAWDOWN", "15.0")
    monkeypatch.setenv("MAX_OPEN_TRADES", "2")
    monkeypatch.setenv("MIN_LOT", "0.01")
    monkeypatch.setenv("MAX_LOT", "0.05")
    monkeypatch.setenv("SPREAD_FILTER", "80")
    monkeypatch.setenv("TELEGRAM_TOKEN", "test_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
```

- [ ] **Step 5: Commit**

```bash
git add bot/config.py bot/logger.py bot/tests/
git commit -m "feat: add config, logger, and test scaffold"
```

---

## Task 3: Money Management

**Files:**
- Create: `bot/money_management.py`
- Create: `bot/tests/test_money_management.py`

- [ ] **Step 1: Tulis test yang gagal di `bot/tests/test_money_management.py`**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def reload_modules():
    import importlib
    import config
    importlib.reload(config)


def test_lot_size_floored_to_min():
    from money_management import calculate_lot_size
    # balance=$100, risk=1% → risk_usd=$1, SL=150pts, tick_val=$1/lot
    # lot = 1/(150*1) = 0.0067 → capped to MIN_LOT=0.01
    lot = calculate_lot_size(balance=100.0, sl_points=150, tick_value_per_lot=1.0)
    assert lot == 0.01


def test_lot_size_normal_range():
    from money_management import calculate_lot_size
    # balance=$100, risk=1% → risk_usd=$1, SL=30pts, tick_val=$1/lot
    # lot = 1/(30*1) = 0.033 → rounded to 0.03
    lot = calculate_lot_size(balance=100.0, sl_points=30, tick_value_per_lot=1.0)
    assert lot == 0.03


def test_lot_size_capped_at_max():
    from money_management import calculate_lot_size
    lot = calculate_lot_size(balance=10000.0, sl_points=1, tick_value_per_lot=0.1)
    assert lot == 0.05


def test_lot_size_zero_sl_returns_min():
    from money_management import calculate_lot_size
    lot = calculate_lot_size(balance=100.0, sl_points=0, tick_value_per_lot=1.0)
    assert lot == 0.01


def test_tp_buy_is_above_entry():
    from money_management import calculate_tp_price
    # entry=2000, sl=1990 → sl_dist=10, tp_dist=20 (RR 1:2), tp=2020
    tp = calculate_tp_price(entry_price=2000.0, sl_price=1990.0, order_type=0)
    assert tp == pytest.approx(2020.0, abs=0.01)


def test_tp_sell_is_below_entry():
    from money_management import calculate_tp_price
    # entry=2000, sl=2010 → sl_dist=10, tp_dist=20, tp=1980
    tp = calculate_tp_price(entry_price=2000.0, sl_price=2010.0, order_type=1)
    assert tp == pytest.approx(1980.0, abs=0.01)


def test_daily_loss_not_reached():
    from money_management import is_daily_loss_limit_reached
    assert is_daily_loss_limit_reached(2.9) is False


def test_daily_loss_reached():
    from money_management import is_daily_loss_limit_reached
    assert is_daily_loss_limit_reached(3.0) is True


def test_drawdown_not_reached():
    from money_management import is_drawdown_limit_reached
    # 10% drawdown, limit 15% → tidak tercapai
    assert is_drawdown_limit_reached(current_balance=90.0, peak_balance=100.0) is False


def test_drawdown_reached():
    from money_management import is_drawdown_limit_reached
    # 16% drawdown, limit 15% → tercapai
    assert is_drawdown_limit_reached(current_balance=84.0, peak_balance=100.0) is True
```

- [ ] **Step 2: Jalankan test — pastikan GAGAL**

```bash
cd bot
python -m pytest tests/test_money_management.py -v
```

Expected: `ImportError` atau `ModuleNotFoundError: No module named 'money_management'`

- [ ] **Step 3: Buat `bot/money_management.py`**

```python
import config


def calculate_lot_size(balance: float, sl_points: int, tick_value_per_lot: float) -> float:
    if sl_points <= 0 or tick_value_per_lot <= 0:
        return config.MIN_LOT
    risk_usd = balance * config.RISK_PER_TRADE / 100
    lot = risk_usd / (sl_points * tick_value_per_lot)
    lot = round(lot, 2)
    return max(config.MIN_LOT, min(config.MAX_LOT, lot))


def calculate_tp_price(entry_price: float, sl_price: float, order_type: int) -> float:
    sl_distance = abs(entry_price - sl_price)
    tp_distance = sl_distance * config.TARGET_RR
    if order_type == 0:  # BUY
        return round(entry_price + tp_distance, 2)
    return round(entry_price - tp_distance, 2)


def is_daily_loss_limit_reached(daily_loss_pct: float) -> bool:
    return daily_loss_pct >= config.MAX_LOSS_PER_DAY


def is_drawdown_limit_reached(current_balance: float, peak_balance: float) -> bool:
    if peak_balance <= 0:
        return False
    drawdown_pct = (peak_balance - current_balance) / peak_balance * 100
    return drawdown_pct >= config.MAX_DRAWDOWN
```

- [ ] **Step 4: Jalankan test — pastikan LULUS**

```bash
python -m pytest tests/test_money_management.py -v
```

Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add bot/money_management.py bot/tests/test_money_management.py
git commit -m "feat: add money management module with tests"
```

---

## Task 4: Trade Filter

**Files:**
- Create: `bot/trade_filter.py`
- Create: `bot/tests/test_trade_filter.py`

- [ ] **Step 1: Tulis test yang gagal di `bot/tests/test_trade_filter.py`**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime
from unittest.mock import MagicMock
import pytz

WIB = pytz.timezone("Asia/Jakarta")


def wib(hour, minute):
    return WIB.localize(datetime(2026, 5, 19, hour, minute))


# --- is_active_trading_hour ---

def test_within_first_window():
    from trade_filter import is_active_trading_hour
    assert is_active_trading_hour(wib(15, 30)) is True


def test_within_second_window():
    from trade_filter import is_active_trading_hour
    assert is_active_trading_hour(wib(21, 0)) is True


def test_outside_windows():
    from trade_filter import is_active_trading_hour
    assert is_active_trading_hour(wib(10, 0)) is False


def test_boundary_start_first_window():
    from trade_filter import is_active_trading_hour
    assert is_active_trading_hour(wib(14, 0)) is True


def test_boundary_end_second_window():
    from trade_filter import is_active_trading_hour
    assert is_active_trading_hour(wib(23, 0)) is True


def test_between_windows():
    from trade_filter import is_active_trading_hour
    assert is_active_trading_hour(wib(18, 0)) is False


# --- is_spread_acceptable ---

def test_spread_ok():
    from trade_filter import is_spread_acceptable
    assert is_spread_acceptable(79) is True


def test_spread_at_limit():
    from trade_filter import is_spread_acceptable
    assert is_spread_acceptable(80) is True


def test_spread_too_wide():
    from trade_filter import is_spread_acceptable
    assert is_spread_acceptable(81) is False


# --- is_trade_valid ---

def test_trade_with_sl():
    from trade_filter import is_trade_valid
    pos = MagicMock(sl=1990.0)
    valid, reason = is_trade_valid(pos)
    assert valid is True


def test_trade_without_sl():
    from trade_filter import is_trade_valid
    pos = MagicMock(sl=0)
    valid, reason = is_trade_valid(pos)
    assert valid is False
    assert "SL" in reason


# --- can_open_trade ---

def test_all_conditions_pass():
    from trade_filter import can_open_trade
    allowed, reason = can_open_trade(
        open_positions_count=1, daily_loss_pct=1.0, spread_points=50, now=wib(15, 0)
    )
    assert allowed is True
    assert reason == ""


def test_blocked_outside_hours():
    from trade_filter import can_open_trade
    allowed, reason = can_open_trade(0, 0.0, 50, wib(10, 0))
    assert allowed is False
    assert "jam trading" in reason


def test_blocked_max_trades():
    from trade_filter import can_open_trade
    allowed, reason = can_open_trade(2, 0.0, 50, wib(15, 0))
    assert allowed is False
    assert "trade terbuka" in reason


def test_blocked_high_spread():
    from trade_filter import can_open_trade
    allowed, reason = can_open_trade(0, 0.0, 100, wib(15, 0))
    assert allowed is False
    assert "Spread" in reason


def test_blocked_daily_loss():
    from trade_filter import can_open_trade
    allowed, reason = can_open_trade(0, 3.0, 50, wib(15, 0))
    assert allowed is False
    assert "Loss" in reason
```

- [ ] **Step 2: Jalankan test — pastikan GAGAL**

```bash
python -m pytest tests/test_trade_filter.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Buat `bot/trade_filter.py`**

```python
from datetime import datetime, time
import pytz
import config
from money_management import is_daily_loss_limit_reached

WIB = pytz.timezone("Asia/Jakarta")


def is_active_trading_hour(now: datetime = None) -> bool:
    if now is None:
        now = datetime.now(WIB)
    elif now.tzinfo is None:
        now = WIB.localize(now)
    t = now.time()
    for sh, sm, eh, em in config.ACTIVE_HOURS:
        if time(sh, sm) <= t <= time(eh, em):
            return True
    return False


def is_spread_acceptable(spread_points: int) -> bool:
    return spread_points <= config.SPREAD_FILTER


def is_trade_valid(position) -> tuple[bool, str]:
    sl = getattr(position, "sl", None) or position.get("sl", 0) if isinstance(position, dict) else getattr(position, "sl", 0)
    if not sl:
        return False, "SL tidak terpasang"
    return True, ""


def can_open_trade(
    open_positions_count: int,
    daily_loss_pct: float,
    spread_points: int,
    now: datetime = None,
) -> tuple[bool, str]:
    if not is_active_trading_hour(now):
        return False, "Di luar jam trading aktif"
    if open_positions_count >= config.MAX_OPEN_TRADES:
        return False, f"Sudah ada {open_positions_count} trade terbuka (max {config.MAX_OPEN_TRADES})"
    if not is_spread_acceptable(spread_points):
        return False, f"Spread {spread_points} pts terlalu lebar (max {config.SPREAD_FILTER})"
    if is_daily_loss_limit_reached(daily_loss_pct):
        return False, f"Loss harian {daily_loss_pct:.1f}% sudah tercapai (max {config.MAX_LOSS_PER_DAY}%)"
    return True, ""
```

- [ ] **Step 4: Jalankan test — pastikan LULUS**

```bash
python -m pytest tests/test_trade_filter.py -v
```

Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add bot/trade_filter.py bot/tests/test_trade_filter.py
git commit -m "feat: add trade filter module with tests"
```

---

## Task 5: MT5 Connector

**Files:**
- Create: `bot/mt5_connector.py`
- Create: `bot/tests/test_mt5_connector.py`

- [ ] **Step 1: Tulis test yang gagal di `bot/tests/test_mt5_connector.py`**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_mt5_lib():
    mock = MagicMock()
    mock.initialize.return_value = True
    mock.account_info.return_value = MagicMock(balance=150.0, equity=148.0)
    mock.symbol_info.return_value = MagicMock(spread=45)
    mock.symbol_info_tick.return_value = MagicMock(bid=2000.0, ask=2000.5)
    mock.positions_get.return_value = [
        MagicMock(ticket=1001, symbol="XAUUSD", volume=0.01, type=0, sl=1990.0, tp=2020.0, price_open=2000.0)
    ]
    mock.TRADE_RETCODE_DONE = 10009
    mock.TRADE_ACTION_DEAL = 1
    mock.TRADE_ACTION_SLTP = 6
    mock.ORDER_TYPE_SELL = 1
    mock.ORDER_TYPE_BUY = 0
    mock.ORDER_TIME_GTC = 1
    mock.ORDER_FILLING_IOC = 1
    return mock


def test_connect_success(mock_mt5_lib):
    with patch("mt5_connector.MetaTrader5", return_value=mock_mt5_lib):
        from mt5_connector import MT5Connector
        conn = MT5Connector(host="localhost", port=8001)
        assert conn.connect() is True
        assert conn.is_connected is True


def test_connect_failure(mock_mt5_lib):
    mock_mt5_lib.initialize.return_value = False
    mock_mt5_lib.last_error.return_value = (1, "Connection refused")
    with patch("mt5_connector.MetaTrader5", return_value=mock_mt5_lib):
        from mt5_connector import MT5Connector
        conn = MT5Connector(host="localhost", port=8001)
        assert conn.connect() is False
        assert conn.is_connected is False


def test_get_balance(mock_mt5_lib):
    with patch("mt5_connector.MetaTrader5", return_value=mock_mt5_lib):
        from mt5_connector import MT5Connector
        conn = MT5Connector()
        conn.connect()
        assert conn.get_balance() == 150.0


def test_get_spread(mock_mt5_lib):
    with patch("mt5_connector.MetaTrader5", return_value=mock_mt5_lib):
        from mt5_connector import MT5Connector
        conn = MT5Connector()
        conn.connect()
        assert conn.get_spread("XAUUSD") == 45


def test_get_positions(mock_mt5_lib):
    with patch("mt5_connector.MetaTrader5", return_value=mock_mt5_lib):
        from mt5_connector import MT5Connector
        conn = MT5Connector()
        conn.connect()
        positions = conn.get_positions("XAUUSD")
        assert len(positions) == 1
        assert positions[0].ticket == 1001


def test_get_positions_disconnected():
    from importlib import reload
    import mt5_connector
    reload(mt5_connector)
    conn = mt5_connector.MT5Connector()
    assert conn.get_positions() == []


def test_close_position_success(mock_mt5_lib):
    mock_mt5_lib.order_send.return_value = MagicMock(retcode=10009)
    with patch("mt5_connector.MetaTrader5", return_value=mock_mt5_lib):
        from mt5_connector import MT5Connector
        conn = MT5Connector()
        conn.connect()
        pos = MagicMock(ticket=1001, symbol="XAUUSD", volume=0.01, type=0)
        assert conn.close_position(pos) is True


def test_modify_tp_success(mock_mt5_lib):
    mock_mt5_lib.order_send.return_value = MagicMock(retcode=10009)
    with patch("mt5_connector.MetaTrader5", return_value=mock_mt5_lib):
        from mt5_connector import MT5Connector
        conn = MT5Connector()
        conn.connect()
        pos = MagicMock(ticket=1001, symbol="XAUUSD", sl=1990.0)
        assert conn.modify_position_tp(pos, new_tp=2020.0) is True
```

- [ ] **Step 2: Jalankan test — pastikan GAGAL**

```bash
python -m pytest tests/test_mt5_connector.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Buat `bot/mt5_connector.py`**

```python
import logging
import config

logger = logging.getLogger(__name__)

try:
    from mt5linux import MetaTrader5
except ImportError:
    MetaTrader5 = None


class MT5Connector:
    def __init__(self, host: str = None, port: int = None):
        self.host = host or config.MT5_HOST
        self.port = port or config.MT5_PORT
        self._mt5 = None
        self._connected = False

    def connect(self) -> bool:
        try:
            self._mt5 = MetaTrader5(host=self.host, port=self.port)
            if self._mt5.initialize():
                self._connected = True
                logger.info(f"MT5 connected: {self.host}:{self.port}")
                return True
            logger.error(f"MT5 init failed: {self._mt5.last_error()}")
            return False
        except Exception as e:
            logger.error(f"MT5 connection error: {e}")
            return False

    def disconnect(self):
        if self._mt5 and self._connected:
            self._mt5.shutdown()
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def get_account_info(self):
        if not self._connected:
            return None
        return self._mt5.account_info()

    def get_balance(self) -> float:
        info = self.get_account_info()
        return info.balance if info else 0.0

    def get_equity(self) -> float:
        info = self.get_account_info()
        return info.equity if info else 0.0

    def get_positions(self, symbol: str = None):
        if not self._connected:
            return []
        result = self._mt5.positions_get(symbol=symbol) if symbol else self._mt5.positions_get()
        return list(result) if result else []

    def get_symbol_info(self, symbol: str):
        if not self._connected:
            return None
        return self._mt5.symbol_info(symbol)

    def get_tick(self, symbol: str):
        if not self._connected:
            return None
        return self._mt5.symbol_info_tick(symbol)

    def get_spread(self, symbol: str) -> int:
        info = self.get_symbol_info(symbol)
        return info.spread if info else 999

    def close_position(self, position) -> bool:
        if not self._connected:
            return False
        tick = self.get_tick(position.symbol)
        if not tick:
            return False
        close_type = self._mt5.ORDER_TYPE_SELL if position.type == 0 else self._mt5.ORDER_TYPE_BUY
        price = tick.bid if position.type == 0 else tick.ask
        request = {
            "action": self._mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": close_type,
            "position": position.ticket,
            "price": price,
            "deviation": 20,
            "magic": 12345,
            "comment": "Bot close",
            "type_time": self._mt5.ORDER_TIME_GTC,
            "type_filling": self._mt5.ORDER_FILLING_IOC,
        }
        result = self._mt5.order_send(request)
        if result and result.retcode == self._mt5.TRADE_RETCODE_DONE:
            logger.info(f"Position {position.ticket} closed")
            return True
        logger.error(f"Close failed: {result}")
        return False

    def modify_position_tp(self, position, new_tp: float) -> bool:
        if not self._connected:
            return False
        request = {
            "action": self._mt5.TRADE_ACTION_SLTP,
            "symbol": position.symbol,
            "position": position.ticket,
            "sl": position.sl,
            "tp": new_tp,
        }
        result = self._mt5.order_send(request)
        return bool(result and result.retcode == self._mt5.TRADE_RETCODE_DONE)
```

- [ ] **Step 4: Jalankan test — pastikan LULUS**

```bash
python -m pytest tests/test_mt5_connector.py -v
```

Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add bot/mt5_connector.py bot/tests/test_mt5_connector.py
git commit -m "feat: add MT5 connector with mocked tests"
```

---

## Task 6: Signal Watcher

**Files:**
- Create: `bot/signal_watcher.py`
- Create: `bot/tests/test_signal_watcher.py`

- [ ] **Step 1: Tulis test yang gagal di `bot/tests/test_signal_watcher.py`**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
import pytz

WIB = pytz.timezone("Asia/Jakarta")


def make_mt5(balance=100.0, equity=100.0, positions=None, spread=50):
    mt5 = MagicMock()
    mt5.is_connected = True
    mt5.get_balance.return_value = balance
    mt5.get_equity.return_value = equity
    mt5.get_positions.return_value = positions or []
    mt5.get_spread.return_value = spread
    mt5.close_position.return_value = True
    mt5.modify_position_tp.return_value = True
    return mt5


def make_position(ticket=1001, sl=1990.0, tp=2020.0, price_open=2000.0, pos_type=0, volume=0.01):
    p = MagicMock()
    p.ticket = ticket
    p.sl = sl
    p.tp = tp
    p.price_open = price_open
    p.type = pos_type
    p.volume = volume
    p.symbol = "XAUUSD"
    return p


def test_initialize_sets_known_tickets():
    from signal_watcher import SignalWatcher
    pos = make_position(ticket=1001)
    mt5 = make_mt5(balance=100.0, positions=[pos])
    watcher = SignalWatcher(mt5)
    watcher.initialize()
    assert 1001 in watcher._known_tickets


def test_drawdown_not_reached():
    from signal_watcher import SignalWatcher
    mt5 = make_mt5(balance=90.0)
    alerts = []
    watcher = SignalWatcher(mt5, on_alert=alerts.append)
    watcher._peak_balance = 100.0
    assert watcher.check_drawdown() is False
    assert len(alerts) == 0


def test_drawdown_reached_triggers_alert():
    from signal_watcher import SignalWatcher
    mt5 = make_mt5(balance=84.0)
    alerts = []
    watcher = SignalWatcher(mt5, on_alert=alerts.append)
    watcher._peak_balance = 100.0
    assert watcher.check_drawdown() is True
    assert len(alerts) == 1


def test_daily_loss_triggers_pause():
    from signal_watcher import SignalWatcher
    mt5 = make_mt5(balance=96.5)
    watcher = SignalWatcher(mt5)
    watcher._day_start_balance = 100.0
    watcher.check_daily_loss()
    assert watcher.is_paused is True


def test_new_position_accepted_in_trading_hours():
    from signal_watcher import SignalWatcher
    pos = make_position(ticket=1002)
    mt5 = make_mt5(balance=100.0, positions=[pos], spread=50)
    new_trades = []
    watcher = SignalWatcher(mt5, on_new_trade=new_trades.append)
    watcher._known_tickets = set()
    watcher._day_start_balance = 100.0

    active_time = WIB.localize(datetime(2026, 5, 19, 15, 0))
    with patch("signal_watcher.datetime") as mock_dt:
        mock_dt.now.return_value = active_time
        with patch("signal_watcher.can_open_trade", return_value=(True, "")):
            with patch("signal_watcher.is_trade_valid", return_value=(True, "")):
                with patch("signal_watcher.calculate_tp_price", return_value=2020.0):
                    watcher.tick()

    assert len(new_trades) == 1


def test_new_position_closed_if_filter_fails():
    from signal_watcher import SignalWatcher
    pos = make_position(ticket=1003)
    mt5 = make_mt5(balance=100.0, positions=[pos], spread=50)
    new_trades = []
    watcher = SignalWatcher(mt5, on_new_trade=new_trades.append)
    watcher._known_tickets = set()
    watcher._day_start_balance = 100.0

    with patch("signal_watcher.can_open_trade", return_value=(False, "Di luar jam trading aktif")):
        watcher.tick()

    mt5.close_position.assert_called_once_with(pos)
    assert len(new_trades) == 0


def test_paused_bot_closes_new_position():
    from signal_watcher import SignalWatcher
    pos = make_position(ticket=1004)
    mt5 = make_mt5(balance=100.0, positions=[pos])
    watcher = SignalWatcher(mt5)
    watcher._known_tickets = set()
    watcher._paused = True
    watcher._day_start_balance = 100.0
    watcher.tick()
    mt5.close_position.assert_called_once_with(pos)
```

- [ ] **Step 2: Jalankan test — pastikan GAGAL**

```bash
python -m pytest tests/test_signal_watcher.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Buat `bot/signal_watcher.py`**

```python
import logging
from datetime import datetime
from typing import Callable
import pytz
import config
from money_management import is_drawdown_limit_reached, calculate_tp_price
from trade_filter import can_open_trade, is_trade_valid

logger = logging.getLogger(__name__)
WIB = pytz.timezone("Asia/Jakarta")


class SignalWatcher:
    def __init__(self, mt5, on_new_trade: Callable = None, on_trade_closed: Callable = None, on_alert: Callable = None):
        self.mt5 = mt5
        self.on_new_trade = on_new_trade or (lambda p: None)
        self.on_trade_closed = on_trade_closed or (lambda ticket, profit: None)
        self.on_alert = on_alert or (lambda msg: None)
        self._known_tickets: set[int] = set()
        self._paused: bool = False
        self._peak_balance: float = 0.0
        self._day_start_balance: float = 0.0

    def initialize(self):
        balance = self.mt5.get_balance()
        self._peak_balance = balance
        self._day_start_balance = balance
        self._known_tickets = {p.ticket for p in self.mt5.get_positions(config.SYMBOL)}
        logger.info(f"Watcher init: balance={balance}, positions={len(self._known_tickets)}")

    @property
    def is_paused(self) -> bool:
        return self._paused

    def pause(self):
        self._paused = True
        logger.info("Bot paused")

    def resume(self):
        self._paused = False
        logger.info("Bot resumed")

    def check_drawdown(self) -> bool:
        balance = self.mt5.get_balance()
        if balance > self._peak_balance:
            self._peak_balance = balance
        if is_drawdown_limit_reached(balance, self._peak_balance):
            msg = f"DRAWDOWN LIMIT! Balance={balance:.2f}, Peak={self._peak_balance:.2f}"
            logger.critical(msg)
            self.on_alert(f"🚨 {msg} — Bot berhenti total!")
            return True
        return False

    def check_daily_loss(self) -> bool:
        balance = self.mt5.get_balance()
        if self._day_start_balance <= 0:
            return False
        daily_loss_pct = (self._day_start_balance - balance) / self._day_start_balance * 100
        if daily_loss_pct >= config.MAX_LOSS_PER_DAY:
            self.on_alert(f"⚠️ Loss harian {daily_loss_pct:.1f}% tercapai — Bot pause sampai besok")
            self.pause()
            return True
        return False

    def tick(self):
        if not self.mt5.is_connected:
            self.on_alert("⚠️ Koneksi MT5 terputus!")
            return

        if self.check_drawdown():
            return

        self.check_daily_loss()

        current_positions = self.mt5.get_positions(config.SYMBOL)
        current_tickets = {p.ticket for p in current_positions}
        new_tickets = current_tickets - self._known_tickets

        for position in current_positions:
            if position.ticket not in new_tickets:
                continue
            if self._paused:
                logger.info(f"Bot paused — closing {position.ticket}")
                self.mt5.close_position(position)
                continue
            self._handle_new_position(position)

        self._known_tickets = current_tickets

    def _handle_new_position(self, position):
        spread = self.mt5.get_spread(config.SYMBOL)
        open_count = len(self._known_tickets)
        balance = self.mt5.get_balance()
        daily_loss_pct = max(0.0, (self._day_start_balance - balance) / max(self._day_start_balance, 1) * 100)

        allowed, reason = can_open_trade(open_count, daily_loss_pct, spread)
        if not allowed:
            logger.info(f"Filter blocked {position.ticket}: {reason}")
            self.mt5.close_position(position)
            return

        valid, reason = is_trade_valid(position)
        if not valid:
            logger.info(f"Invalid trade {position.ticket}: {reason}")
            self.mt5.close_position(position)
            return

        new_tp = calculate_tp_price(position.price_open, position.sl, position.type)
        self.mt5.modify_position_tp(position, new_tp)
        logger.info(f"Position {position.ticket} accepted, TP → {new_tp}")
        self.on_new_trade(position)
```

- [ ] **Step 4: Jalankan test — pastikan LULUS**

```bash
python -m pytest tests/test_signal_watcher.py -v
```

Expected: 8 passed

- [ ] **Step 5: Jalankan semua test — pastikan tidak ada regresi**

```bash
python -m pytest tests/ -v
```

Expected: 31 passed

- [ ] **Step 6: Commit**

```bash
git add bot/signal_watcher.py bot/tests/test_signal_watcher.py
git commit -m "feat: add signal watcher with position monitoring and filters"
```

---

## Task 7: Telegram Alert

**Files:**
- Create: `bot/telegram_alert.py`

> Telegram menggunakan async I/O — test hanya verifikasi format pesan, bukan koneksi nyata.

- [ ] **Step 1: Buat `bot/telegram_alert.py`**

```python
import asyncio
import logging
from typing import Callable
import config

logger = logging.getLogger(__name__)


class TelegramAlert:
    def __init__(self, token: str = None, chat_id: str = None):
        self.token = token or config.TELEGRAM_TOKEN
        self.chat_id = chat_id or config.TELEGRAM_CHAT_ID
        self._bot = None
        self._app = None
        self._get_status: Callable = None
        self._pause: Callable = None
        self._resume: Callable = None
        self._get_trades: Callable = None
        self._get_laporan: Callable = None

    def set_callbacks(self, get_status=None, pause=None, resume=None, get_trades=None, get_laporan=None):
        self._get_status = get_status
        self._pause = pause
        self._resume = resume
        self._get_trades = get_trades
        self._get_laporan = get_laporan

    async def send(self, text: str):
        if not self._bot:
            logger.warning(f"[Telegram not connected] {text}")
            return
        try:
            await self._bot.send_message(chat_id=self.chat_id, text=text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Telegram send error: {e}")

    def send_sync(self, text: str):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.send(text))
            else:
                loop.run_until_complete(self.send(text))
        except Exception as e:
            logger.error(f"send_sync error: {e}")

    def format_trade_open(self, position) -> str:
        direction = "BUY 📈" if position.type == 0 else "SELL 📉"
        return (
            f"<b>Trade Baru — {config.SYMBOL}</b>\n"
            f"Arah: {direction}\n"
            f"Lot: {position.volume}\n"
            f"Entry: {position.price_open}\n"
            f"SL: {position.sl}\n"
            f"TP: {position.tp}\n"
        )

    def format_trade_close(self, ticket: int, profit: float, balance: float) -> str:
        emoji = "✅" if profit >= 0 else "❌"
        sign = "+" if profit >= 0 else ""
        return (
            f"{emoji} <b>Trade Ditutup #{ticket}</b>\n"
            f"P&L: {sign}{profit:.2f} USD\n"
            f"Balance: {balance:.2f} USD\n"
        )

    def format_daily_report(self, total_trades: int, win_trades: int, total_profit: float, balance: float) -> str:
        win_rate = win_trades / total_trades * 100 if total_trades > 0 else 0
        sign = "+" if total_profit >= 0 else ""
        return (
            f"📊 <b>Laporan Harian</b>\n"
            f"Total Trade: {total_trades}\n"
            f"Win Rate: {win_rate:.1f}%\n"
            f"Total P&L: {sign}{total_profit:.2f} USD\n"
            f"Balance: {balance:.2f} USD\n"
        )

    async def start_polling(self):
        from telegram import Update
        from telegram.ext import Application, CommandHandler, ContextTypes

        async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            text = self._get_status() if self._get_status else "Status tidak tersedia"
            await update.message.reply_text(text)

        async def cmd_pause(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            if self._pause:
                self._pause()
            await update.message.reply_text("⏸ Bot di-pause")

        async def cmd_resume(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            if self._resume:
                self._resume()
            await update.message.reply_text("▶️ Bot dilanjutkan")

        async def cmd_laporan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            text = self._get_laporan() if self._get_laporan else "Laporan tidak tersedia"
            await update.message.reply_text(text, parse_mode="HTML")

        async def cmd_trades(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            text = self._get_trades() if self._get_trades else "Tidak ada trade terbuka"
            await update.message.reply_text(text, parse_mode="HTML")

        self._app = Application.builder().token(self.token).build()
        self._bot = self._app.bot
        self._app.add_handler(CommandHandler("status", cmd_status))
        self._app.add_handler(CommandHandler("pause", cmd_pause))
        self._app.add_handler(CommandHandler("resume", cmd_resume))
        self._app.add_handler(CommandHandler("laporan", cmd_laporan))
        self._app.add_handler(CommandHandler("trades", cmd_trades))
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()
```

- [ ] **Step 2: Verifikasi format pesan (tidak butuh koneksi)**

```bash
cd bot
python -c "
from unittest.mock import MagicMock
import os; os.environ['TELEGRAM_TOKEN']='x'; os.environ['TELEGRAM_CHAT_ID']='1'
from telegram_alert import TelegramAlert
t = TelegramAlert()
pos = MagicMock(type=0, volume=0.01, price_open=2000.0, sl=1990.0, tp=2020.0)
print(t.format_trade_open(pos))
print(t.format_trade_close(1001, 2.50, 102.50))
print(t.format_daily_report(5, 3, 4.20, 104.20))
"
```

Expected: Output berformat HTML tanpa error

- [ ] **Step 3: Commit**

```bash
git add bot/telegram_alert.py
git commit -m "feat: add telegram alert and bot commands"
```

---

## Task 8: Main Orchestrator

**Files:**
- Create: `bot/main.py`

- [ ] **Step 1: Buat `bot/main.py`**

```python
import asyncio
import logging
from datetime import datetime
import pytz
import config
from logger import setup_logger
from mt5_connector import MT5Connector
from signal_watcher import SignalWatcher
from telegram_alert import TelegramAlert

setup_logger()
logger = logging.getLogger(__name__)
WIB = pytz.timezone("Asia/Jakarta")


class TradingBot:
    def __init__(self):
        self.mt5 = MT5Connector()
        self.telegram = TelegramAlert()
        self.watcher = SignalWatcher(
            mt5=self.mt5,
            on_new_trade=self._on_new_trade,
            on_trade_closed=self._on_trade_closed,
            on_alert=self._on_alert,
        )
        self._running = False
        self._daily_profits: list[float] = []
        self._daily_profit_total: float = 0.0

    def _on_new_trade(self, position):
        self.telegram.send_sync(self.telegram.format_trade_open(position))

    def _on_trade_closed(self, ticket: int, profit: float):
        balance = self.mt5.get_balance()
        self.telegram.send_sync(self.telegram.format_trade_close(ticket, profit, balance))
        self._daily_profits.append(profit)
        self._daily_profit_total += profit

    def _on_alert(self, message: str):
        self.telegram.send_sync(message)

    def _get_status(self) -> str:
        balance = self.mt5.get_balance()
        equity = self.mt5.get_equity()
        status = "⏸ Pause" if self.watcher.is_paused else "▶️ Aktif"
        n_pos = len(self.mt5.get_positions(config.SYMBOL))
        return (
            f"Status: {status}\n"
            f"Balance: {balance:.2f} USD\n"
            f"Equity: {equity:.2f} USD\n"
            f"Open Trades: {n_pos}\n"
        )

    def _get_trades_text(self) -> str:
        positions = self.mt5.get_positions(config.SYMBOL)
        if not positions:
            return "Tidak ada trade terbuka"
        lines = ["<b>Trade Terbuka:</b>"]
        for p in positions:
            direction = "BUY" if p.type == 0 else "SELL"
            lines.append(f"#{p.ticket} {direction} {p.volume}lot @ {p.price_open:.2f} | P&L: {p.profit:.2f}")
        return "\n".join(lines)

    def _get_laporan(self) -> str:
        wins = sum(1 for p in self._daily_profits if p > 0)
        return self.telegram.format_daily_report(
            total_trades=len(self._daily_profits),
            win_trades=wins,
            total_profit=self._daily_profit_total,
            balance=self.mt5.get_balance(),
        )

    def _reset_daily(self):
        self._daily_profits = []
        self._daily_profit_total = 0.0
        self.watcher._day_start_balance = self.mt5.get_balance()
        if self.watcher.is_paused:
            self.watcher.resume()
            self.telegram.send_sync("🌅 Hari baru — bot dilanjutkan otomatis")

    async def run(self):
        logger.info("Bot starting...")
        if not self.mt5.connect():
            logger.error("Cannot connect to MT5. Exiting.")
            return

        self.telegram.set_callbacks(
            get_status=self._get_status,
            pause=self.watcher.pause,
            resume=self.watcher.resume,
            get_trades=self._get_trades_text,
            get_laporan=self._get_laporan,
        )

        self.watcher.initialize()
        await self.telegram.start_polling()
        await self.telegram.send(f"🤖 Bot XAU/USD aktif! Balance: {self.mt5.get_balance():.2f} USD")

        self._running = True
        today = datetime.now(WIB).date()
        last_report_date = None

        try:
            while self._running:
                now = datetime.now(WIB)

                if now.date() != today:
                    self._reset_daily()
                    today = now.date()

                if now.hour == 23 and now.minute == 59 and last_report_date != now.date():
                    await self.telegram.send(self._get_laporan())
                    last_report_date = now.date()

                self.watcher.tick()
                await asyncio.sleep(config.POLL_INTERVAL_SECONDS)

        except asyncio.CancelledError:
            pass
        finally:
            await self.telegram.send("🔴 Bot berhenti.")
            self.mt5.disconnect()


if __name__ == "__main__":
    bot = TradingBot()
    asyncio.run(bot.run())
```

- [ ] **Step 2: Jalankan seluruh test suite**

```bash
cd bot
python -m pytest tests/ -v
```

Expected: 31 passed, 0 failed

- [ ] **Step 3: Verifikasi import main berjalan tanpa error**

```bash
python -c "import main; print('Import OK')"
```

Expected: `Import OK`

- [ ] **Step 4: Commit final**

```bash
git add bot/main.py
git commit -m "feat: add main orchestrator - bot ready for Docker deployment"
```

---

## Checklist Deploy ke VPS

Setelah semua task selesai, deploy ke IDCloudHost VPS:

```bash
# 1. Copy project ke VPS
scp -r bot-trading/ user@vps-ip:~/

# 2. SSH ke VPS
ssh user@vps-ip

# 3. Install Docker
curl -fsSL https://get.docker.com | sh

# 4. Jalankan
cd bot-trading
cp .env.example .env
nano .env  # isi MT5_LOGIN, PASSWORD, SERVER, TELEGRAM_TOKEN, CHAT_ID
docker compose up -d

# 5. Cek log
docker compose logs -f bot-service

# 6. Akses MT5 GUI via browser untuk subscribe signal
# buka http://vps-ip:3000 di browser
```

---

## Self-Review: Spec Coverage

| Requirement dari Spec | Task |
|---|---|
| Docker Compose 2 container (mt5-service, bot-service) | Task 1 |
| Money management: lot otomatis, RR 1:2, daily loss 3%, drawdown 15% | Task 3 |
| Trade filter: jam WIB, spread < 80 pts, SL wajib, max 2 trades | Task 4 |
| MT5 connector via mt5linux | Task 5 |
| Pantau posisi baru, tutup jika tidak lolos filter | Task 6 |
| Telegram alert: trade open/close, laporan harian, drawdown alert | Task 7 |
| Commands /status /pause /resume /laporan /trades | Task 7 |
| Main loop 5 detik, reset harian, laporan 23:59 | Task 8 |

**Gap:** Filter berita (NFP, FOMC, CPI, GDP) tidak diimplementasi di MVP ini karena membutuhkan external news API. User harus pause bot manual sebelum berita besar menggunakan `/pause`.
