# London Breakout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the EMA 4-phase `SignalStateMachine` with a London Session Breakout strategy that places pending stop orders at London open based on the Asian session high/low range.

**Architecture:** `LondonBreakoutStrategy` in `signal_generator.py` tracks running Asian high/low. `SignalWatcher` drives a time-based state machine (IDLE → COLLECTING → ORDERS_SET → EXPIRED) and calls the strategy. Two new `MT5Connector` methods handle pending stop orders. All old 4-phase code is deleted.

**Tech Stack:** Python 3.11, mt5linux, pytz, pytest, unittest.mock

---

## File Map

| File | Action | What changes |
|------|--------|--------------|
| `bot/config.py` | Modify | Add London Breakout params; replace ACTIVE_HOURS |
| `bot/signal_generator.py` | **Rewrite** | Delete SignalStateMachine, add LondonBreakoutStrategy |
| `bot/signal_watcher.py` | **Rewrite** | Delete 4-phase tick logic, add time-based London state machine |
| `bot/mt5_connector.py` | Modify | Add `place_stop_order()`, `cancel_order()`, `get_pending_orders()` |
| `bot/tests/test_signal_generator.py` | **Rewrite** | Delete old SM tests, add LondonBreakoutStrategy tests |
| `bot/tests/test_signal_watcher.py` | Modify | Add London Breakout watcher tests |
| `bot/tests/test_mt5_connector.py` | Modify | Add tests for 3 new methods |

---

## Task 1: Update config.py

**Files:**
- Modify: `bot/config.py`

- [ ] **Step 1: Add London Breakout parameters after the ACTIVE_HOURS block**

Open `bot/config.py`. Replace the entire `ACTIVE_HOURS` block and add new config below it:

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add bot/config.py
git commit -m "feat: add London Breakout config params and update ACTIVE_HOURS"
```

---

## Task 2: Replace SignalStateMachine with LondonBreakoutStrategy (TDD)

**Files:**
- Rewrite: `bot/signal_generator.py`
- Rewrite: `bot/tests/test_signal_generator.py`

- [ ] **Step 1: Overwrite test file with LondonBreakoutStrategy tests**

Replace the entire contents of `bot/tests/test_signal_generator.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


def make_strategy():
    from signal_generator import LondonBreakoutStrategy
    return LondonBreakoutStrategy()


# --- update_asian_range ---

def test_update_asian_range_tracks_running_max_high():
    s = make_strategy()
    s.update_asian_range(2310.0, 2305.0)
    s.update_asian_range(2315.0, 2303.0)
    assert s.asian_high == 2315.0


def test_update_asian_range_tracks_running_min_low():
    s = make_strategy()
    s.update_asian_range(2310.0, 2305.0)
    s.update_asian_range(2315.0, 2303.0)
    assert s.asian_low == 2303.0


def test_update_asian_range_first_call_sets_both():
    s = make_strategy()
    s.update_asian_range(2310.0, 2305.0)
    assert s.asian_high == 2310.0
    assert s.asian_low == 2305.0


# --- range_size ---

def test_range_size_is_none_before_any_update():
    s = make_strategy()
    assert s.range_size is None


def test_range_size_returns_high_minus_low():
    s = make_strategy()
    s.update_asian_range(2320.0, 2310.0)
    assert s.range_size == pytest.approx(10.0, abs=0.01)


# --- is_range_valid ---

def test_is_range_valid_false_when_no_range():
    s = make_strategy()
    assert s.is_range_valid() is False


def test_is_range_valid_false_when_range_too_small():
    # range = 2.0, below RANGE_MIN_USD = 5.0
    s = make_strategy()
    s.update_asian_range(2310.0, 2308.0)
    assert s.is_range_valid() is False


def test_is_range_valid_false_when_range_too_large():
    # range = 30.0, above RANGE_MAX_USD = 25.0
    s = make_strategy()
    s.update_asian_range(2340.0, 2310.0)
    assert s.is_range_valid() is False


def test_is_range_valid_true_within_bounds():
    # range = 10.0 — within [5, 25]
    s = make_strategy()
    s.update_asian_range(2320.0, 2310.0)
    assert s.is_range_valid() is True


# --- get_pending_orders ---

def test_get_pending_orders_none_when_range_invalid():
    s = make_strategy()
    s.update_asian_range(2310.0, 2308.0)  # range too small
    assert s.get_pending_orders() is None


def test_get_pending_orders_buy_price_above_high():
    # buy_price = asian_high + BREAKOUT_BUFFER_USD (0.5)
    s = make_strategy()
    s.update_asian_range(2320.0, 2310.0)
    orders = s.get_pending_orders()
    assert orders['buy_price'] == pytest.approx(2320.5, abs=0.01)


def test_get_pending_orders_sell_price_below_low():
    # sell_price = asian_low - BREAKOUT_BUFFER_USD (0.5)
    s = make_strategy()
    s.update_asian_range(2320.0, 2310.0)
    orders = s.get_pending_orders()
    assert orders['sell_price'] == pytest.approx(2309.5, abs=0.01)


def test_get_pending_orders_sl_buy_below_asian_low():
    # sl_buy = asian_low - SL_BUFFER_USD (0.3)
    s = make_strategy()
    s.update_asian_range(2320.0, 2310.0)
    orders = s.get_pending_orders()
    assert orders['sl_buy'] == pytest.approx(2309.7, abs=0.01)


def test_get_pending_orders_sl_sell_above_asian_high():
    # sl_sell = asian_high + SL_BUFFER_USD (0.3)
    s = make_strategy()
    s.update_asian_range(2320.0, 2310.0)
    orders = s.get_pending_orders()
    assert orders['sl_sell'] == pytest.approx(2320.3, abs=0.01)


def test_get_pending_orders_tp_buy_is_range_times_rr_from_entry():
    # range=10, buy_price=2320.5, tp_buy = 2320.5 + 10*1.5 = 2335.5
    s = make_strategy()
    s.update_asian_range(2320.0, 2310.0)
    orders = s.get_pending_orders()
    assert orders['tp_buy'] == pytest.approx(2335.5, abs=0.01)


def test_get_pending_orders_tp_sell_is_range_times_rr_from_entry():
    # range=10, sell_price=2309.5, tp_sell = 2309.5 - 10*1.5 = 2294.5
    s = make_strategy()
    s.update_asian_range(2320.0, 2310.0)
    orders = s.get_pending_orders()
    assert orders['tp_sell'] == pytest.approx(2294.5, abs=0.01)


def test_get_pending_orders_includes_range_size():
    s = make_strategy()
    s.update_asian_range(2320.0, 2310.0)
    orders = s.get_pending_orders()
    assert orders['range_size'] == pytest.approx(10.0, abs=0.01)


# --- reset ---

def test_reset_clears_asian_high_and_low():
    s = make_strategy()
    s.update_asian_range(2320.0, 2310.0)
    s.reset()
    assert s.asian_high is None
    assert s.asian_low is None


def test_reset_makes_range_invalid():
    s = make_strategy()
    s.update_asian_range(2320.0, 2310.0)
    s.reset()
    assert s.is_range_valid() is False
```

- [ ] **Step 2: Run tests — expect ImportError (class belum ada)**

```bash
cd bot && pytest tests/test_signal_generator.py -v
```

Expected output: `ImportError: cannot import name 'LondonBreakoutStrategy' from 'signal_generator'`

- [ ] **Step 3: Rewrite signal_generator.py**

Replace the entire contents of `bot/signal_generator.py`:

```python
import logging
import config

logger = logging.getLogger(__name__)


class LondonBreakoutStrategy:

    def __init__(self):
        self._asian_high: float | None = None
        self._asian_low:  float | None = None

    def update_asian_range(self, high: float, low: float) -> None:
        if self._asian_high is None or high > self._asian_high:
            self._asian_high = high
        if self._asian_low is None or low < self._asian_low:
            self._asian_low = low

    @property
    def asian_high(self) -> float | None:
        return self._asian_high

    @property
    def asian_low(self) -> float | None:
        return self._asian_low

    @property
    def range_size(self) -> float | None:
        if self._asian_high is None or self._asian_low is None:
            return None
        return round(self._asian_high - self._asian_low, 2)

    def is_range_valid(self) -> bool:
        r = self.range_size
        if r is None:
            return False
        return config.RANGE_MIN_USD <= r <= config.RANGE_MAX_USD

    def get_pending_orders(self) -> dict | None:
        if not self.is_range_valid():
            return None
        r          = self.range_size
        buy_price  = round(self._asian_high + config.BREAKOUT_BUFFER_USD, 2)
        sell_price = round(self._asian_low  - config.BREAKOUT_BUFFER_USD, 2)
        sl_buy     = round(self._asian_low  - config.SL_BUFFER_USD, 2)
        sl_sell    = round(self._asian_high + config.SL_BUFFER_USD, 2)
        tp_buy     = round(buy_price  + r * config.TP_RR_BREAKOUT, 2)
        tp_sell    = round(sell_price - r * config.TP_RR_BREAKOUT, 2)
        return {
            'buy_price':  buy_price,
            'sell_price': sell_price,
            'sl_buy':     sl_buy,
            'sl_sell':    sl_sell,
            'tp_buy':     tp_buy,
            'tp_sell':    tp_sell,
            'range_size': r,
        }

    def reset(self) -> None:
        self._asian_high = None
        self._asian_low  = None
```

- [ ] **Step 4: Run tests — semua harus PASS**

```bash
cd bot && pytest tests/test_signal_generator.py -v
```

Expected: All 18 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/signal_generator.py bot/tests/test_signal_generator.py
git commit -m "feat: replace SignalStateMachine with LondonBreakoutStrategy"
```

---

## Task 3: Tambah stop order methods ke MT5Connector (TDD)

**Files:**
- Modify: `bot/mt5_connector.py`
- Modify: `bot/tests/test_mt5_connector.py`

- [ ] **Step 1: Tambah tests ke akhir test_mt5_connector.py**

Buka `bot/tests/test_mt5_connector.py`, append di akhir file:

```python
# --- place_stop_order ---

def _make_conn(connected=True):
    from mt5_connector import MT5Connector
    conn = MT5Connector.__new__(MT5Connector)
    conn._connected = connected
    conn.last_order_error = None
    mt5 = MagicMock()
    mt5.ORDER_TYPE_BUY_STOP  = 4
    mt5.ORDER_TYPE_SELL_STOP = 5
    mt5.ORDER_TIME_DAY       = 1
    mt5.TRADE_ACTION_PENDING = 5
    mt5.TRADE_ACTION_REMOVE  = 8
    mt5.TRADE_RETCODE_DONE   = 10009
    mt5.symbol_info.return_value = MagicMock(filling_mode=1)
    conn._mt5 = mt5
    return conn, mt5


def test_place_stop_order_buy_stop_returns_ticket():
    conn, mt5 = _make_conn()
    result_mock = MagicMock(retcode=10009, order=9999)
    mt5.order_send.return_value = result_mock
    ticket = conn.place_stop_order('XAUUSD', 0, 0.01, 2320.5, 2309.7, 2335.5)
    assert ticket == 9999
    sent = mt5.order_send.call_args[0][0]
    assert sent['type'] == 4   # ORDER_TYPE_BUY_STOP
    assert sent['price'] == 2320.5


def test_place_stop_order_sell_stop_uses_correct_type():
    conn, mt5 = _make_conn()
    result_mock = MagicMock(retcode=10009, order=8888)
    mt5.order_send.return_value = result_mock
    ticket = conn.place_stop_order('XAUUSD', 1, 0.01, 2309.5, 2320.3, 2294.5)
    assert ticket == 8888
    sent = mt5.order_send.call_args[0][0]
    assert sent['type'] == 5   # ORDER_TYPE_SELL_STOP


def test_place_stop_order_returns_none_on_failure():
    conn, mt5 = _make_conn()
    mt5.order_send.return_value = MagicMock(retcode=10006, comment='rejected')
    ticket = conn.place_stop_order('XAUUSD', 0, 0.01, 2320.5, 2309.7, 2335.5)
    assert ticket is None


def test_place_stop_order_returns_none_when_disconnected():
    conn, _ = _make_conn(connected=False)
    ticket = conn.place_stop_order('XAUUSD', 0, 0.01, 2320.5, 2309.7, 2335.5)
    assert ticket is None


# --- cancel_order ---

def test_cancel_order_sends_remove_action():
    conn, mt5 = _make_conn()
    mt5.order_send.return_value = MagicMock(retcode=10009)
    result = conn.cancel_order(12345)
    assert result is True
    sent = mt5.order_send.call_args[0][0]
    assert sent['action'] == 8   # TRADE_ACTION_REMOVE
    assert sent['order']  == 12345


def test_cancel_order_returns_false_on_failure():
    conn, mt5 = _make_conn()
    mt5.order_send.return_value = MagicMock(retcode=10006)
    result = conn.cancel_order(12345)
    assert result is False


def test_cancel_order_returns_false_when_disconnected():
    conn, _ = _make_conn(connected=False)
    assert conn.cancel_order(12345) is False


# --- get_pending_orders ---

def test_get_pending_orders_returns_list():
    conn, mt5 = _make_conn()
    order = MagicMock()
    mt5.orders_get.return_value = [order]
    result = conn.get_pending_orders('XAUUSD')
    assert result == [order]
    mt5.orders_get.assert_called_once_with(symbol='XAUUSD')


def test_get_pending_orders_returns_empty_when_none():
    conn, mt5 = _make_conn()
    mt5.orders_get.return_value = None
    assert conn.get_pending_orders('XAUUSD') == []


def test_get_pending_orders_returns_empty_when_disconnected():
    conn, _ = _make_conn(connected=False)
    assert conn.get_pending_orders('XAUUSD') == []
```

- [ ] **Step 2: Jalankan tests baru — harus FAIL**

```bash
cd bot && pytest tests/test_mt5_connector.py -v -k "stop_order or cancel_order or get_pending"
```

Expected: `AttributeError: 'MT5Connector' object has no attribute 'place_stop_order'`

- [ ] **Step 3: Tambah 3 method ke MT5Connector**

Buka `bot/mt5_connector.py`, tambahkan di akhir class (setelah `modify_position_tp`):

```python
    def place_stop_order(self, symbol: str, order_type: int, lot: float, price: float, sl: float, tp: float, comment: str = "bot_stop") -> int | None:
        """Place pending stop order. order_type: 0=BUY_STOP, 1=SELL_STOP. Returns ticket or None."""
        if not self._connected:
            return None
        mt5_type = self._mt5.ORDER_TYPE_BUY_STOP if order_type == 0 else self._mt5.ORDER_TYPE_SELL_STOP
        request = {
            "action":       self._mt5.TRADE_ACTION_PENDING,
            "symbol":       symbol,
            "volume":       float(lot),
            "type":         mt5_type,
            "price":        float(price),
            "sl":           float(sl),
            "tp":           float(tp),
            "deviation":    config.MT5_DEVIATION,
            "magic":        config.MT5_MAGIC,
            "comment":      comment,
            "type_time":    self._mt5.ORDER_TIME_DAY,
            "type_filling": self._get_filling_type(symbol),
        }
        result = self._mt5.order_send(request)
        if result and result.retcode == self._mt5.TRADE_RETCODE_DONE:
            logger.info(f"Stop order placed: ticket={result.order}, {symbol} {'BUY_STOP' if order_type == 0 else 'SELL_STOP'} @ {price}")
            return result.order
        retcode      = getattr(result, 'retcode',  None)
        err_comment  = getattr(result, 'comment',  '')
        logger.error(f"place_stop_order failed: retcode={retcode}, comment={err_comment}")
        self.last_order_error = (retcode, err_comment)
        return None

    def cancel_order(self, ticket: int) -> bool:
        """Cancel a pending order by ticket number."""
        if not self._connected:
            return False
        request = {
            "action": self._mt5.TRADE_ACTION_REMOVE,
            "order":  ticket,
        }
        result = self._mt5.order_send(request)
        if result and result.retcode == self._mt5.TRADE_RETCODE_DONE:
            logger.info(f"Order {ticket} cancelled")
            return True
        logger.error(f"Cancel order {ticket} failed: retcode={getattr(result, 'retcode', None)}")
        return False

    def get_pending_orders(self, symbol: str = None) -> list:
        """Return list of pending orders, optionally filtered by symbol."""
        if not self._connected:
            return []
        result = self._mt5.orders_get(symbol=symbol) if symbol else self._mt5.orders_get()
        return list(result) if result else []
```

- [ ] **Step 4: Jalankan tests baru — semua harus PASS**

```bash
cd bot && pytest tests/test_mt5_connector.py -v -k "stop_order or cancel_order or get_pending"
```

Expected: All 10 new tests PASS.

- [ ] **Step 5: Jalankan full test suite mt5_connector**

```bash
cd bot && pytest tests/test_mt5_connector.py -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add bot/mt5_connector.py bot/tests/test_mt5_connector.py
git commit -m "feat: add place_stop_order, cancel_order, get_pending_orders to MT5Connector"
```

---

## Task 4: Rewrite SignalWatcher untuk London Breakout (TDD)

**Files:**
- Rewrite: `bot/signal_watcher.py`
- Modify: `bot/tests/test_signal_watcher.py`

- [ ] **Step 1: Tambah tests London Breakout ke test_signal_watcher.py**

Append di akhir `bot/tests/test_signal_watcher.py`:

```python
from datetime import datetime, time as time_type
import pytz as _pytz

_WIB = _pytz.timezone("Asia/Jakarta")


def make_watcher_lb(balance=100.0, positions=None, spread=50):
    from signal_watcher import SignalWatcher
    mt5 = make_mt5(balance=balance, positions=positions or [], spread=spread)
    mt5.get_tick.return_value = MagicMock(bid=2315.0, ask=2315.5)
    mt5.is_algo_trading_enabled.return_value = True
    mt5.get_symbol_info.return_value = MagicMock(point=0.01, trade_tick_value=1.0)
    mt5.place_stop_order.return_value = None
    mt5.cancel_order.return_value = True
    mt5.get_pending_orders.return_value = []
    alerts = []
    watcher = SignalWatcher(mt5, on_alert=alerts.append)
    watcher._peak_balance = balance
    watcher._day_start_balance = balance
    return watcher, mt5, alerts


def _wib(hour, minute):
    return datetime.now(_WIB).replace(hour=hour, minute=minute, second=0, microsecond=0)


def test_collecting_updates_asian_range_from_tick():
    watcher, mt5, _ = make_watcher_lb()
    mt5.get_tick.return_value = MagicMock(bid=2310.0, ask=2311.0)
    watcher._london_state = 'COLLECTING'
    watcher._update_london_breakout(_wib(10, 0))
    assert watcher._strategy.asian_high == 2311.0
    assert watcher._strategy.asian_low  == 2310.0


def test_collecting_does_not_run_outside_asian_window():
    watcher, mt5, _ = make_watcher_lb()
    mt5.get_tick.return_value = MagicMock(bid=2310.0, ask=2311.0)
    watcher._london_state = 'IDLE'
    watcher._update_london_breakout(_wib(15, 30))  # outside 07:00-14:00 WIB
    assert watcher._strategy.asian_high is None


def test_places_orders_at_14_50_when_collecting():
    watcher, mt5, alerts = make_watcher_lb()
    watcher._strategy.update_asian_range(2320.0, 2310.0)  # valid $10 range
    watcher._london_state = 'COLLECTING'
    mt5.place_stop_order.return_value = 1001
    watcher._update_london_breakout(_wib(14, 50))
    assert mt5.place_stop_order.call_count == 2
    assert watcher._london_state == 'ORDERS_SET'
    assert any("dipasang" in a for a in alerts)


def test_skips_order_placement_if_range_invalid():
    watcher, mt5, alerts = make_watcher_lb()
    watcher._strategy.update_asian_range(2310.5, 2310.0)  # $0.5 — too small
    watcher._london_state = 'COLLECTING'
    watcher._update_london_breakout(_wib(14, 50))
    mt5.place_stop_order.assert_not_called()
    assert any("Skip" in a or "tidak valid" in a for a in alerts)


def test_cancels_pending_orders_at_expiry():
    watcher, mt5, alerts = make_watcher_lb()
    watcher._london_state = 'ORDERS_SET'
    watcher._pending_buy_ticket  = 1001
    watcher._pending_sell_ticket = 1002
    mt5.cancel_order.return_value = True
    watcher._update_london_breakout(_wib(17, 0))
    assert mt5.cancel_order.call_count == 2
    assert watcher._london_state == 'EXPIRED'
    assert any("dihapus" in a or "Expired" in a for a in alerts)


def test_oco_cancels_sell_when_buy_triggers():
    watcher, mt5, _ = make_watcher_lb()
    watcher._london_state        = 'ORDERS_SET'
    watcher._pending_buy_ticket  = 1001
    watcher._pending_sell_ticket = 1002
    # 1001 gone from pending → buy triggered
    mt5.get_pending_orders.return_value = [MagicMock(ticket=1002)]
    watcher._update_london_breakout(_wib(15, 30))
    mt5.cancel_order.assert_called_once_with(1002)


def test_oco_cancels_buy_when_sell_triggers():
    watcher, mt5, _ = make_watcher_lb()
    watcher._london_state        = 'ORDERS_SET'
    watcher._pending_buy_ticket  = 1001
    watcher._pending_sell_ticket = 1002
    # 1002 gone from pending → sell triggered
    mt5.get_pending_orders.return_value = [MagicMock(ticket=1001)]
    watcher._update_london_breakout(_wib(15, 30))
    mt5.cancel_order.assert_called_once_with(1001)


def test_reset_day_clears_strategy_and_london_state():
    watcher, _, _ = make_watcher_lb()
    watcher._strategy.update_asian_range(2320.0, 2310.0)
    watcher._london_state = 'ORDERS_SET'
    watcher.reset_day(100.0)
    assert watcher._strategy.asian_high is None
    assert watcher._london_state == 'IDLE'
```

- [ ] **Step 2: Jalankan tests baru — harus FAIL**

```bash
cd bot && pytest tests/test_signal_watcher.py -v -k "collecting or places_orders or skips_order or cancels_pending or oco or reset_day_clears"
```

Expected: `AttributeError: 'SignalWatcher' object has no attribute '_update_london_breakout'`

- [ ] **Step 3: Rewrite signal_watcher.py**

Replace the entire contents of `bot/signal_watcher.py`:

```python
import logging
import time as time_module
from dataclasses import dataclass
from datetime import datetime, time
from typing import Callable
import pytz
import config
from money_management import is_drawdown_limit_reached, calculate_lot_size
from trade_filter import can_open_trade, is_active_trading_hour
from signal_generator import LondonBreakoutStrategy

logger = logging.getLogger(__name__)
WIB = pytz.timezone("Asia/Jakarta")


@dataclass
class TradeInfo:
    ticket: int
    type: int
    volume: float
    price_open: float
    sl: float
    tp: float


class SignalWatcher:
    def __init__(self, mt5, on_new_trade: Callable = None, on_trade_closed: Callable = None, on_alert: Callable = None):
        self.mt5 = mt5
        self.on_new_trade   = on_new_trade   or (lambda p: None)
        self.on_trade_closed = on_trade_closed or (lambda ticket, profit: None)
        self.on_alert       = on_alert       or (lambda msg: None)
        self._known_tickets:      set[int]        = set()
        self._last_known_profits: dict[int, float] = {}
        self._paused:      bool  = False
        self._peak_balance: float = 0.0
        self._day_start_balance: float = 0.0
        self._tick_count:  int   = 0
        self._in_news_blackout:  bool = False
        self._in_active_hours:   bool = False
        self._algo_trading_disabled: bool = False
        self._strategy:  LondonBreakoutStrategy = LondonBreakoutStrategy()
        self._london_state:         str       = 'IDLE'  # IDLE|COLLECTING|ORDERS_SET|EXPIRED
        self._pending_buy_ticket:   int | None = None
        self._pending_sell_ticket:  int | None = None
        self._managed_trades: dict[int, dict] = {}

    def initialize(self):
        balance = self.mt5.get_balance()
        self._peak_balance       = balance
        self._day_start_balance  = balance
        positions = self.mt5.get_positions(config.SYMBOL)
        self._known_tickets      = {p.ticket for p in positions}
        self._last_known_profits = {p.ticket: p.profit for p in positions}
        logger.info(f"Watcher init: balance={balance}, positions={len(self._known_tickets)}")
        if not self.mt5.is_algo_trading_enabled():
            self._algo_trading_disabled = True
            logger.warning("AutoTrading disabled in MT5 terminal at startup")
            self.on_alert(
                "⚠️ <b>AutoTrading MT5 nonaktif!</b>\n"
                "Buka VNC terminal MT5 → klik tombol 'Algo Trading' (hijau di toolbar).\n"
                "Bot tidak bisa buka order sampai diaktifkan."
            )

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
        if balance <= 0:
            return False
        if balance > self._peak_balance:
            self._peak_balance = balance
        if is_drawdown_limit_reached(balance, self._peak_balance):
            msg = f"DRAWDOWN LIMIT! Balance={balance:.2f}, Peak={self._peak_balance:.2f}"
            logger.critical(msg)
            self.on_alert(f"🚨 {msg} — Bot berhenti total!")
            self.pause()
            return True
        return False

    def check_daily_loss(self) -> bool:
        balance = self.mt5.get_balance()
        if balance <= 0:
            return False
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
        if self.check_daily_loss():
            return

        now = datetime.now(WIB)

        active_now = is_active_trading_hour(now)
        if active_now and not self._in_active_hours:
            self._in_active_hours = True
            self.on_alert("🟢 Window London Breakout dimulai — bot aktif memantau")
        elif not active_now and self._in_active_hours:
            self._in_active_hours = False
            self.on_alert("🔴 Window London Breakout selesai — bot standby")

        current_positions = self.mt5.get_positions(config.SYMBOL)
        current_tickets   = {p.ticket for p in current_positions}
        position_profits  = {p.ticket: p.profit for p in current_positions}

        closed_tickets = self._known_tickets - current_tickets
        for ticket in closed_tickets:
            profit = self._last_known_profits.get(ticket, 0.0)
            logger.info(f"Position {ticket} closed, profit={profit:.2f}")
            self.on_trade_closed(ticket, profit)
            self._managed_trades.pop(ticket, None)

        new_tickets = current_tickets - self._known_tickets
        for ticket in new_tickets:
            pos = next((p for p in current_positions if p.ticket == ticket), None)
            if pos:
                self._on_position_opened(pos)

        self._check_tp1(current_positions)

        if not self._paused:
            self._update_london_breakout(now)

        self._known_tickets      = current_tickets
        self._last_known_profits = position_profits

        self._tick_count += 1
        if self._tick_count % 150 == 0:
            algo_on = self.mt5.is_algo_trading_enabled()
            if not algo_on and not self._algo_trading_disabled:
                self._algo_trading_disabled = True
                self.on_alert(
                    "⚠️ <b>AutoTrading MT5 nonaktif!</b>\n"
                    "Buka VNC terminal MT5 → klik tombol 'Algo Trading' (hijau di toolbar).\n"
                    "Bot tidak bisa buka order sampai diaktifkan."
                )
            elif algo_on and self._algo_trading_disabled:
                self._algo_trading_disabled = False
                self.on_alert("✅ AutoTrading MT5 aktif kembali — bot siap buka order.")
        if self._tick_count % 60 == 0:
            balance = self.mt5.get_balance()
            logger.info(
                f"Heartbeat: balance={balance:.2f}, positions={len(current_positions)}, "
                f"paused={self._paused}, london_state={self._london_state}"
            )

    def reset_day(self, balance: float):
        self._day_start_balance = balance
        if balance > self._peak_balance:
            self._peak_balance = balance
        self._strategy.reset()
        self._london_state        = 'IDLE'
        self._pending_buy_ticket  = None
        self._pending_sell_ticket = None
        logger.info("Daily reset: London Breakout state cleared")

    # ------------------------------------------------------------------
    # London Breakout time-based state machine
    # ------------------------------------------------------------------

    def _update_london_breakout(self, now: datetime):
        t            = now.time()
        asian_start  = time(*config.ASIAN_RANGE_START)
        asian_end    = time(*config.ASIAN_RANGE_END)
        place_time   = time(*config.ORDERS_PLACE_TIME)
        expiry_time  = time(*config.ORDERS_EXPIRY_TIME)

        # COLLECTING: accumulate Asian range from live tick
        if asian_start <= t < asian_end:
            if self._london_state == 'IDLE':
                self._london_state = 'COLLECTING'
            tick = self.mt5.get_tick(config.SYMBOL)
            if tick:
                self._strategy.update_asian_range(float(tick.ask), float(tick.bid))
            return

        # ORDER PLACEMENT: once when entering the placement window
        if place_time <= t < expiry_time and self._london_state == 'COLLECTING':
            self._place_london_orders(now)
            return

        # OCO MONITORING: check if one order triggered and cancel the other
        if place_time <= t < expiry_time and self._london_state == 'ORDERS_SET':
            self._check_oco()
            return

        # EXPIRY: cancel any remaining pending orders at 17:00 WIB
        if t >= expiry_time and self._london_state == 'ORDERS_SET':
            self._expire_pending_orders()

    def _place_london_orders(self, now: datetime):
        orders = self._strategy.get_pending_orders()
        if orders is None:
            r = self._strategy.range_size
            label = 'tidak ada data' if r is None else f'{r:.2f} USD'
            self.on_alert(f"⚠️ Skip London Breakout hari ini — range Asian tidak valid ({label})")
            self._london_state = 'EXPIRED'
            return

        balance       = self.mt5.get_balance()
        daily_loss_pct = max(0.0, (self._day_start_balance - balance) / max(self._day_start_balance, 1) * 100)
        spread        = self.mt5.get_spread(config.SYMBOL)
        open_count    = len(self.mt5.get_positions(config.SYMBOL))

        allowed, reason = can_open_trade(open_count, daily_loss_pct, spread, now)
        if not allowed:
            self.on_alert(f"⚠️ London Breakout skip — {reason}")
            self._london_state = 'EXPIRED'
            return

        if not self.mt5.is_algo_trading_enabled():
            self.on_alert("⚠️ AutoTrading nonaktif — tidak bisa pasang pending orders")
            self._london_state = 'EXPIRED'
            return

        symbol_info = self.mt5.get_symbol_info(config.SYMBOL)
        if not symbol_info or not getattr(symbol_info, 'trade_tick_value', None):
            return

        point = getattr(symbol_info, 'point', 0.01) or 0.01

        sl_dist_buy  = abs(orders['buy_price']  - orders['sl_buy'])
        sl_dist_sell = abs(orders['sell_price'] - orders['sl_sell'])
        sl_pts_buy   = round(sl_dist_buy  / point)
        sl_pts_sell  = round(sl_dist_sell / point)
        lot_buy  = calculate_lot_size(balance, sl_pts_buy,  symbol_info.trade_tick_value)
        lot_sell = calculate_lot_size(balance, sl_pts_sell, symbol_info.trade_tick_value)

        buy_ticket  = self.mt5.place_stop_order(
            config.SYMBOL, 0, lot_buy,
            orders['buy_price'], orders['sl_buy'], orders['tp_buy'],
        )
        sell_ticket = self.mt5.place_stop_order(
            config.SYMBOL, 1, lot_sell,
            orders['sell_price'], orders['sl_sell'], orders['tp_sell'],
        )

        if buy_ticket and sell_ticket:
            self._pending_buy_ticket  = buy_ticket
            self._pending_sell_ticket = sell_ticket
            self._london_state = 'ORDERS_SET'
            self.on_alert(
                f"📊 <b>Asian Range Terkunci — XAUUSD</b>\n"
                f"High: {self._strategy.asian_high:.2f} | Low: {self._strategy.asian_low:.2f}\n"
                f"Range: {orders['range_size']:.2f} USD\n"
                f"Buy Stop:  {orders['buy_price']:.2f}  | SL: {orders['sl_buy']:.2f}  | TP: {orders['tp_buy']:.2f}\n"
                f"Sell Stop: {orders['sell_price']:.2f} | SL: {orders['sl_sell']:.2f} | TP: {orders['tp_sell']:.2f}\n"
                f"Orders dipasang — menunggu breakout sampai 17:00 WIB"
            )
        else:
            # Cancel whichever order was placed if only one succeeded
            if buy_ticket:
                self.mt5.cancel_order(buy_ticket)
            if sell_ticket:
                self.mt5.cancel_order(sell_ticket)
            retcode, comment = self.mt5.last_order_error or (None, '')
            self.on_alert(f"🚨 Gagal pasang pending orders: retcode={retcode}, {comment}")

    def _check_oco(self):
        pending_tickets = {o.ticket for o in self.mt5.get_pending_orders(config.SYMBOL)}
        buy_pending  = self._pending_buy_ticket  in pending_tickets if self._pending_buy_ticket  else False
        sell_pending = self._pending_sell_ticket in pending_tickets if self._pending_sell_ticket else False

        if not buy_pending and sell_pending:
            self.mt5.cancel_order(self._pending_sell_ticket)
            self._london_state = 'EXPIRED'
            logger.info(f"OCO: Buy triggered, cancelled Sell Stop {self._pending_sell_ticket}")

        elif not sell_pending and buy_pending:
            self.mt5.cancel_order(self._pending_buy_ticket)
            self._london_state = 'EXPIRED'
            logger.info(f"OCO: Sell triggered, cancelled Buy Stop {self._pending_buy_ticket}")

    def _expire_pending_orders(self):
        cancelled = 0
        for ticket in [self._pending_buy_ticket, self._pending_sell_ticket]:
            if ticket and self.mt5.cancel_order(ticket):
                cancelled += 1
        self._london_state = 'EXPIRED'
        self.on_alert(
            f"⏱ <b>London Breakout Expired — XAUUSD</b>\n"
            f"Tidak ada breakout dalam window 14:50–17:00 WIB.\n"
            f"{cancelled} pending order dihapus."
        )

    # ------------------------------------------------------------------
    # Position management (TP1 / breakeven) — unchanged from before
    # ------------------------------------------------------------------

    def _on_position_opened(self, pos):
        direction   = "BUY" if pos.type == 0 else "SELL"
        sl_distance = abs(pos.price_open - pos.sl) if getattr(pos, 'sl', 0) else 0
        tp1_price   = round(
            pos.price_open + sl_distance * config.TP1_RR if pos.type == 0
            else pos.price_open - sl_distance * config.TP1_RR, 2
        ) if sl_distance > 0 else 0
        half_vol = max(config.MIN_LOT, round(pos.volume / 2, 2))
        self._managed_trades[pos.ticket] = {
            'tp1':      tp1_price,
            'entry':    pos.price_open,
            'type':     pos.type,
            'half_vol': half_vol,
            'tp1_hit':  False,
        }
        self.on_new_trade(TradeInfo(
            ticket=pos.ticket, type=pos.type, volume=pos.volume,
            price_open=pos.price_open, sl=pos.sl, tp=pos.tp,
        ))
        logger.info(f"New position: ticket={pos.ticket} {direction} @ {pos.price_open:.2f} SL={pos.sl:.2f} TP={pos.tp:.2f}")

    def _check_tp1(self, positions):
        for pos in positions:
            info = self._managed_trades.get(pos.ticket)
            if not info or info['tp1_hit'] or not info['tp1']:
                continue

            tp1 = info['tp1']
            tp1_reached = (
                (info['type'] == 0 and pos.price_current >= tp1) or
                (info['type'] == 1 and pos.price_current <= tp1)
            )
            if not tp1_reached:
                continue

            half_vol  = info['half_vol']
            direction = "BUY" if info['type'] == 0 else "SELL"

            if half_vol < config.MIN_LOT:
                info['tp1_hit'] = True
                logger.info(f"TP1 reached {pos.ticket} but volume too small — keeping full position")
                return

            success = self.mt5.partial_close_position(pos, half_vol)
            if success:
                info['tp1_hit'] = True
                self.mt5.modify_position_sl(pos, info['entry'])
                logger.info(f"TP1 hit {pos.ticket}: closed {half_vol}lot, SL → breakeven {info['entry']:.2f}")
                self.on_alert(
                    f"🎯 TP1 hit #{pos.ticket} ({direction})\n"
                    f"Closed {half_vol}lot — profit secured\n"
                    f"SL moved to breakeven {info['entry']:.2f}\n"
                    f"Remaining {half_vol}lot running to TP2"
                )
```

- [ ] **Step 4: Jalankan tests baru — semua harus PASS**

```bash
cd bot && pytest tests/test_signal_watcher.py -v -k "collecting or places_orders or skips_order or cancels_pending or oco or reset_day_clears"
```

Expected: All 8 new tests PASS.

- [ ] **Step 5: Jalankan full test suite**

```bash
cd bot && pytest tests/ -v
```

Expected: All tests PASS. Jika ada test lama di `test_signal_watcher.py` yang memeriksa `_state_machine` atau `_last_signal_time` (atribut yang sudah dihapus), hapus test tersebut — behavior-nya sudah tidak ada.

- [ ] **Step 6: Commit**

```bash
git add bot/signal_watcher.py bot/tests/test_signal_watcher.py
git commit -m "feat: rewrite SignalWatcher for London Breakout — replace 4-phase logic with time-based state machine"
```

---

## Verifikasi Akhir

- [ ] **Jalankan semua tests**

```bash
cd bot && pytest tests/ -v --tb=short
```

Expected: All tests PASS, 0 failures.

- [ ] **Periksa tidak ada import SignalStateMachine tersisa**

```bash
grep -r "SignalStateMachine" bot/
```

Expected: No output (hanya boleh ada di test file lama yang sudah diganti).

- [ ] **Final commit jika ada perubahan minor**

```bash
git add -A
git commit -m "chore: cleanup after London Breakout migration"
```
