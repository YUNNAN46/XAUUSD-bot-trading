# Signal Strategy V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ganti strategi sinyal V1 (RSI+BB yang terlalu ketat, 0 trade dalam 3 hari) dengan 4-phase EMA channel state machine yang menghasilkan 1–2 trade per hari.

**Architecture:** `SignalStateMachine` di `signal_generator.py` menggantikan fungsi `get_signal()`. State machine berjalan 4 fase (SCANNING → ARMED → WINDOW_OPEN → ENTRY) dan menyimpan state ke `/app/state.json` untuk recovery saat Docker restart. `signal_watcher.py` hanya butuh 1 baris ubahan untuk memakai state machine.

**Tech Stack:** Python 3.11, `ta` library (EMAIndicator, AverageTrueRange), pandas, pytest, json.

---

## File Map

| File | Aksi | Perubahan |
|---|---|---|
| `bot/config.py` | Modify | Tambah `TP1_RR=1.5`, ubah default `TARGET_RR` 3.0→4.0 |
| `bot/tests/conftest.py` | Modify | Tambah `TP1_RR`, ubah `TARGET_RR` 2.0→4.0 |
| `bot/tests/test_money_management.py` | Modify | Update expected TP values (RR 2→4) |
| `bot/signal_generator.py` | Rewrite | Hapus `get_signal()`, tambah `SignalStateMachine` class |
| `bot/tests/test_signal_generator.py` | Rewrite | Test untuk state machine (4 fase, filters, persistence) |
| `bot/signal_watcher.py` | Modify | Wire `SignalStateMachine`, update TP1 calc ke `config.TP1_RR` |
| `bot/tests/test_signal_watcher.py` | Modify | Update patching dari `get_signal` ke `state_machine.tick` |

---

## Task 1: config.py — Tambah TP1_RR, Update TARGET_RR

**Files:**
- Modify: `bot/config.py`
- Modify: `bot/tests/conftest.py`
- Modify: `bot/tests/test_money_management.py`

- [ ] **Step 1: Update config.py**

Buka `bot/config.py`. Ubah baris TARGET_RR dan tambah TP1_RR setelah TARGET_RR:

```python
TARGET_RR = float(os.getenv("TARGET_RR") or "4.0")   # diubah dari 3.0
TP1_RR    = float(os.getenv("TP1_RR") or "1.5")       # baris baru
```

- [ ] **Step 2: Update conftest.py**

Buka `bot/tests/conftest.py`. Ubah baris TARGET_RR dan tambah TP1_RR:

```python
monkeypatch.setenv("TARGET_RR", "4.0")    # diubah dari "2.0"
monkeypatch.setenv("TP1_RR", "1.5")       # baris baru, letakkan setelah TARGET_RR
```

- [ ] **Step 3: Update test_money_management.py — sesuaikan expected TP values**

Dengan `TARGET_RR=4.0`, tp_dist = sl_dist × 4. Ubah 2 test berikut di `bot/tests/test_money_management.py`:

```python
def test_tp_buy_is_above_entry():
    from money_management import calculate_tp_price
    # entry=2000, sl=1990 → sl_dist=10, RR=4 → tp_dist=40, tp=2040
    tp = calculate_tp_price(entry_price=2000.0, sl_price=1990.0, order_type=0)
    assert tp == pytest.approx(2040.0, abs=0.01)


def test_tp_sell_is_below_entry():
    from money_management import calculate_tp_price
    # entry=2000, sl=2010 → sl_dist=10, RR=4 → tp_dist=40, tp=1960
    tp = calculate_tp_price(entry_price=2000.0, sl_price=2010.0, order_type=1)
    assert tp == pytest.approx(1960.0, abs=0.01)
```

- [ ] **Step 4: Jalankan tests — verifikasi semua pass**

```bash
cd bot && pytest tests/test_money_management.py -v
```

Expected: semua 10 test PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/config.py bot/tests/conftest.py bot/tests/test_money_management.py
git commit -m "feat: add TP1_RR config, update TARGET_RR to 4.0"
```

---

## Task 2: signal_watcher.py — Update TP1 Calculation

**Files:**
- Modify: `bot/signal_watcher.py` (baris 223–226)

- [ ] **Step 1: Update TP1 price calculation di `_try_generate_signal`**

Di `bot/signal_watcher.py`, cari blok ini (sekitar baris 222–226):

```python
        # TP1: 1:1 RR — where we close 50% and move SL to breakeven
        tp1_price = round(
            entry_price + sl_distance if order_type == 0 else entry_price - sl_distance, 2
        )
```

Ganti dengan:

```python
        # TP1: partial close at TP1_RR, then move SL to breakeven
        tp1_price = round(
            entry_price + sl_distance * config.TP1_RR if order_type == 0
            else entry_price - sl_distance * config.TP1_RR, 2
        )
```

- [ ] **Step 2: Update komentar `_check_tp1`**

Di baris 143, ganti:

```python
    def _check_tp1(self, positions):
        """Partial close 50% at TP1 (1:1 RR) and move SL to breakeven."""
```

Dengan:

```python
    def _check_tp1(self, positions):
        """Partial close 50% at TP1 (TP1_RR from config) and move SL to breakeven."""
```

- [ ] **Step 3: Jalankan tests — verifikasi tidak ada regresi**

```bash
cd bot && pytest tests/test_signal_watcher.py -v
```

Expected: semua test PASS (TP1 calculation belum diuji langsung di test_signal_watcher, jadi tidak ada yang break).

- [ ] **Step 4: Commit**

```bash
git add bot/signal_watcher.py
git commit -m "feat: use config.TP1_RR (1.5x) for TP1 calculation"
```

---

## Task 3: Tulis Failing Tests untuk SignalStateMachine

**Files:**
- Rewrite: `bot/tests/test_signal_generator.py`

- [ ] **Step 1: Tulis seluruh file test baru**

Tulis ulang `bot/tests/test_signal_generator.py` dengan isi berikut:

```python
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pandas as pd
from unittest.mock import MagicMock, patch


# ---------- helpers ----------

def make_indicators(
    trend='BULLISH',
    slope=1.0,
    prev_ema14=2009.0, curr_ema14=2012.0,
    prev_ema24=2010.0, curr_ema24=2011.0,
    price=2015.0, open_=2012.0, high=2016.0, low=2011.0,
    atr_current=5.0, atr_avg=4.0,
):
    n = 100
    ema14_series = pd.Series([prev_ema14] * (n - 1) + [curr_ema14])
    ema24_series = pd.Series([prev_ema24] * (n - 1) + [curr_ema24])
    open_series  = pd.Series([2000.0] * (n - 1) + [open_])
    high_series  = pd.Series([2001.0] * (n - 1) + [high])
    low_series   = pd.Series([1999.0] * (n - 1) + [low])
    return {
        'trend': trend,
        'ema14': ema14_series,
        'ema24': ema24_series,
        'slope': slope,
        'open_m15': open_series,
        'high_m15': high_series,
        'low_m15': low_series,
        'price': price,
        'atr_current': atr_current,
        'atr_avg': atr_avg,
    }


def make_sm(tmp_path, initial_state=None):
    from signal_generator import SignalStateMachine
    f = str(tmp_path / "state.json")
    if initial_state:
        with open(f, 'w') as fp:
            json.dump(initial_state, fp)
    return SignalStateMachine(state_file=f)


def tick_with(sm, ind):
    with patch.object(sm, '_get_indicators', return_value=ind):
        return sm.tick(MagicMock(), 'XAUUSD')


# ---------- SCANNING phase ----------

def test_scanning_buy_crossover_transitions_to_armed(tmp_path):
    """EMA14 cross above EMA24 in BULLISH trend → phase ARMED, direction BUY."""
    sm = make_sm(tmp_path)
    # prev_ema14 < prev_ema24, curr_ema14 >= curr_ema24
    ind = make_indicators(trend='BULLISH', slope=1.5,
                          prev_ema14=2009.0, curr_ema14=2012.0,
                          prev_ema24=2010.0, curr_ema24=2011.0)
    result = tick_with(sm, ind)
    assert result == ('NONE', None)
    assert sm._state['phase'] == 'ARMED'
    assert sm._state['direction'] == 'BUY'


def test_scanning_sell_crossover_transitions_to_armed(tmp_path):
    """EMA14 cross below EMA24 in BEARISH trend → phase ARMED, direction SELL."""
    sm = make_sm(tmp_path)
    # prev_ema14 > prev_ema24, curr_ema14 <= curr_ema24
    ind = make_indicators(trend='BEARISH', slope=-1.5,
                          prev_ema14=2012.0, curr_ema14=2009.0,
                          prev_ema24=2010.0, curr_ema24=2011.0)
    result = tick_with(sm, ind)
    assert result == ('NONE', None)
    assert sm._state['phase'] == 'ARMED'
    assert sm._state['direction'] == 'SELL'


def test_scanning_no_crossover_stays_scanning(tmp_path):
    """EMA14 already above EMA24 (no fresh crossover) → stays SCANNING."""
    sm = make_sm(tmp_path)
    ind = make_indicators(trend='BULLISH', slope=1.0,
                          prev_ema14=2012.0, curr_ema14=2013.0,  # both above ema24
                          prev_ema24=2010.0, curr_ema24=2011.0)
    result = tick_with(sm, ind)
    assert result == ('NONE', None)
    assert sm._state['phase'] == 'SCANNING'


def test_scanning_slope_too_flat_blocks_crossover(tmp_path):
    """Slope < EMA_MIN_SLOPE (0.5) → crossover ignored."""
    sm = make_sm(tmp_path)
    ind = make_indicators(trend='BULLISH', slope=0.3,  # too flat
                          prev_ema14=2009.0, curr_ema14=2012.0,
                          prev_ema24=2010.0, curr_ema24=2011.0)
    tick_with(sm, ind)
    assert sm._state['phase'] == 'SCANNING'


def test_scanning_bearish_crossover_ignored_in_bullish_trend(tmp_path):
    """SELL crossover when trend is BULLISH → ignored."""
    sm = make_sm(tmp_path)
    ind = make_indicators(trend='BULLISH', slope=-1.5,
                          prev_ema14=2012.0, curr_ema14=2009.0,
                          prev_ema24=2010.0, curr_ema24=2011.0)
    tick_with(sm, ind)
    assert sm._state['phase'] == 'SCANNING'


# ---------- ARMED phase ----------

def test_armed_bearish_pullback_transitions_to_window_open(tmp_path):
    """Bearish candle (close < open) in BUY ARMED → transitions to WINDOW_OPEN."""
    state = {
        'phase': 'ARMED', 'direction': 'BUY',
        'pullback_count': 0, 'pullback_high': None, 'pullback_low': None,
        'breakout_level': None, 'armed_candles_elapsed': 0, 'window_candles_elapsed': 0,
    }
    sm = make_sm(tmp_path, initial_state=state)
    ind = make_indicators(trend='BULLISH', price=2008.0, open_=2010.0,  # bearish candle
                          high=2011.0, low=2007.0)
    tick_with(sm, ind)
    assert sm._state['phase'] == 'WINDOW_OPEN'
    assert sm._state['breakout_level'] == 2011.0  # highest high of pullback


def test_armed_bullish_pullback_transitions_to_window_open_sell(tmp_path):
    """Bullish candle (close > open) in SELL ARMED → transitions to WINDOW_OPEN."""
    state = {
        'phase': 'ARMED', 'direction': 'SELL',
        'pullback_count': 0, 'pullback_high': None, 'pullback_low': None,
        'breakout_level': None, 'armed_candles_elapsed': 0, 'window_candles_elapsed': 0,
    }
    sm = make_sm(tmp_path, initial_state=state)
    ind = make_indicators(trend='BEARISH', price=2012.0, open_=2010.0,  # bullish candle
                          high=2013.0, low=2009.0)
    tick_with(sm, ind)
    assert sm._state['phase'] == 'WINDOW_OPEN'
    assert sm._state['breakout_level'] == 2009.0  # lowest low of pullback


def test_armed_timeout_resets_to_scanning(tmp_path):
    """After ARMED_TIMEOUT_CANDLES (5) candles with no pullback → reset to SCANNING."""
    state = {
        'phase': 'ARMED', 'direction': 'BUY',
        'pullback_count': 0, 'pullback_high': None, 'pullback_low': None,
        'breakout_level': None, 'armed_candles_elapsed': 4, 'window_candles_elapsed': 0,
    }
    sm = make_sm(tmp_path, initial_state=state)
    # Bullish candle (not a pullback for BUY)
    ind = make_indicators(trend='BULLISH', price=2013.0, open_=2010.0)
    tick_with(sm, ind)
    assert sm._state['phase'] == 'SCANNING'


def test_armed_trend_reversal_resets_to_scanning(tmp_path):
    """Trend changes while ARMED → reset to SCANNING."""
    state = {
        'phase': 'ARMED', 'direction': 'BUY',
        'pullback_count': 0, 'pullback_high': None, 'pullback_low': None,
        'breakout_level': None, 'armed_candles_elapsed': 1, 'window_candles_elapsed': 0,
    }
    sm = make_sm(tmp_path, initial_state=state)
    ind = make_indicators(trend='BEARISH')  # trend flipped
    tick_with(sm, ind)
    assert sm._state['phase'] == 'SCANNING'


def test_armed_ema_crossback_resets_to_scanning(tmp_path):
    """EMA14 crosses back below EMA24 while BUY ARMED → reset."""
    state = {
        'phase': 'ARMED', 'direction': 'BUY',
        'pullback_count': 0, 'pullback_high': None, 'pullback_low': None,
        'breakout_level': None, 'armed_candles_elapsed': 1, 'window_candles_elapsed': 0,
    }
    sm = make_sm(tmp_path, initial_state=state)
    ind = make_indicators(trend='BULLISH',
                          prev_ema14=2009.0, curr_ema14=2009.0,  # ema14 < ema24
                          prev_ema24=2011.0, curr_ema24=2011.0)
    tick_with(sm, ind)
    assert sm._state['phase'] == 'SCANNING'


# ---------- WINDOW_OPEN phase ----------

def test_window_open_buy_breakout_returns_buy_signal(tmp_path):
    """Price closes above breakout_level in BUY setup → BUY signal returned."""
    state = {
        'phase': 'WINDOW_OPEN', 'direction': 'BUY',
        'pullback_count': 1, 'pullback_high': 2013.0, 'pullback_low': 2010.0,
        'breakout_level': 2013.0, 'armed_candles_elapsed': 1, 'window_candles_elapsed': 0,
    }
    sm = make_sm(tmp_path, initial_state=state)
    ind = make_indicators(trend='BULLISH', price=2015.0, atr_current=5.0)  # price > 2013
    signal, sl = tick_with(sm, ind)
    assert signal == 'BUY'
    assert sl == round(2015.0 - 2.0 * 5.0, 2)  # 2005.0


def test_window_open_sell_breakout_returns_sell_signal(tmp_path):
    """Price closes below breakout_level in SELL setup → SELL signal returned."""
    state = {
        'phase': 'WINDOW_OPEN', 'direction': 'SELL',
        'pullback_count': 1, 'pullback_high': 2013.0, 'pullback_low': 2010.0,
        'breakout_level': 2010.0, 'armed_candles_elapsed': 1, 'window_candles_elapsed': 0,
    }
    sm = make_sm(tmp_path, initial_state=state)
    ind = make_indicators(trend='BEARISH', price=2008.0, atr_current=5.0)  # price < 2010
    signal, sl = tick_with(sm, ind)
    assert signal == 'SELL'
    assert sl == round(2008.0 + 2.0 * 5.0, 2)  # 2018.0


def test_window_open_no_breakout_stays_window_open(tmp_path):
    """Price does not break out → stays WINDOW_OPEN."""
    state = {
        'phase': 'WINDOW_OPEN', 'direction': 'BUY',
        'pullback_count': 1, 'pullback_high': 2013.0, 'pullback_low': 2010.0,
        'breakout_level': 2013.0, 'armed_candles_elapsed': 1, 'window_candles_elapsed': 0,
    }
    sm = make_sm(tmp_path, initial_state=state)
    ind = make_indicators(trend='BULLISH', price=2012.0)  # price < breakout_level
    result = tick_with(sm, ind)
    assert result == ('NONE', None)
    assert sm._state['phase'] == 'WINDOW_OPEN'


def test_window_open_timeout_resets_to_scanning(tmp_path):
    """After ENTRY_WINDOW_CANDLES (2) with no breakout → reset to SCANNING."""
    state = {
        'phase': 'WINDOW_OPEN', 'direction': 'BUY',
        'pullback_count': 1, 'pullback_high': 2013.0, 'pullback_low': 2010.0,
        'breakout_level': 2013.0, 'armed_candles_elapsed': 1, 'window_candles_elapsed': 2,
    }
    sm = make_sm(tmp_path, initial_state=state)
    ind = make_indicators(trend='BULLISH', price=2012.0)  # no breakout
    tick_with(sm, ind)
    assert sm._state['phase'] == 'SCANNING'


def test_window_open_trend_reversal_resets_to_scanning(tmp_path):
    """Trend reverses while WINDOW_OPEN → reset to SCANNING."""
    state = {
        'phase': 'WINDOW_OPEN', 'direction': 'BUY',
        'pullback_count': 1, 'pullback_high': 2013.0, 'pullback_low': 2010.0,
        'breakout_level': 2013.0, 'armed_candles_elapsed': 1, 'window_candles_elapsed': 0,
    }
    sm = make_sm(tmp_path, initial_state=state)
    ind = make_indicators(trend='BEARISH', price=2015.0)
    tick_with(sm, ind)
    assert sm._state['phase'] == 'SCANNING'


# ---------- Filters ----------

def test_atr_extreme_blocks_scanning(tmp_path):
    """ATR current > avg × 1.8 → NONE returned, phase stays SCANNING."""
    sm = make_sm(tmp_path)
    ind = make_indicators(atr_current=10.0, atr_avg=5.0,  # 10 > 5*1.8=9 → extreme
                          trend='BULLISH', slope=2.0,
                          prev_ema14=2009.0, curr_ema14=2012.0,
                          prev_ema24=2010.0, curr_ema24=2011.0)
    result = tick_with(sm, ind)
    assert result == ('NONE', None)
    assert sm._state['phase'] == 'SCANNING'


def test_atr_within_normal_range_does_not_block(tmp_path):
    """ATR current <= avg × 1.8 → filter does not block."""
    sm = make_sm(tmp_path)
    ind = make_indicators(atr_current=8.0, atr_avg=5.0,  # 8 < 5*1.8=9 → ok
                          trend='BULLISH', slope=2.0,
                          prev_ema14=2009.0, curr_ema14=2012.0,
                          prev_ema24=2010.0, curr_ema24=2011.0)
    tick_with(sm, ind)
    assert sm._state['phase'] == 'ARMED'  # crossover was processed


def test_get_indicators_returns_none_when_h1_insufficient(tmp_path):
    """get_rates returns None for H1 → tick returns NONE."""
    from signal_generator import SignalStateMachine
    sm = SignalStateMachine(state_file=str(tmp_path / "state.json"))
    mt5 = MagicMock()
    mt5.get_rates.return_value = None
    signal, sl = sm.tick(mt5, 'XAUUSD')
    assert signal == 'NONE'
    assert sl is None


# ---------- State persistence ----------

def test_state_saved_to_file_after_crossover(tmp_path):
    """After SCANNING→ARMED transition, state file contains ARMED state."""
    f = str(tmp_path / "state.json")
    from signal_generator import SignalStateMachine
    sm = SignalStateMachine(state_file=f)
    ind = make_indicators(trend='BULLISH', slope=1.5,
                          prev_ema14=2009.0, curr_ema14=2012.0,
                          prev_ema24=2010.0, curr_ema24=2011.0)
    with patch.object(sm, '_get_indicators', return_value=ind):
        sm.tick(MagicMock(), 'XAUUSD')
    with open(f) as fp:
        saved = json.load(fp)
    assert saved['phase'] == 'ARMED'
    assert saved['direction'] == 'BUY'


def test_state_loaded_from_file_on_init(tmp_path):
    """State machine loads existing state from file on init."""
    f = str(tmp_path / "state.json")
    armed_state = {
        'phase': 'ARMED', 'direction': 'SELL',
        'pullback_count': 0, 'pullback_high': None, 'pullback_low': None,
        'breakout_level': None, 'armed_candles_elapsed': 2, 'window_candles_elapsed': 0,
    }
    with open(f, 'w') as fp:
        json.dump(armed_state, fp)
    from signal_generator import SignalStateMachine
    sm = SignalStateMachine(state_file=f)
    assert sm._state['phase'] == 'ARMED'
    assert sm._state['direction'] == 'SELL'
    assert sm._state['armed_candles_elapsed'] == 2


def test_corrupted_state_file_falls_back_to_scanning(tmp_path):
    """Corrupted state.json → falls back to SCANNING phase."""
    f = str(tmp_path / "state.json")
    with open(f, 'w') as fp:
        fp.write("not valid json {{{")
    from signal_generator import SignalStateMachine
    sm = SignalStateMachine(state_file=f)
    assert sm._state['phase'] == 'SCANNING'


def test_entry_resets_phase_to_scanning(tmp_path):
    """After ENTRY (BUY signal returned), phase resets to SCANNING."""
    state = {
        'phase': 'WINDOW_OPEN', 'direction': 'BUY',
        'pullback_count': 1, 'pullback_high': 2013.0, 'pullback_low': 2010.0,
        'breakout_level': 2013.0, 'armed_candles_elapsed': 1, 'window_candles_elapsed': 0,
    }
    sm = make_sm(tmp_path, initial_state=state)
    ind = make_indicators(trend='BULLISH', price=2015.0, atr_current=5.0)
    signal, _ = tick_with(sm, ind)
    assert signal == 'BUY'
    assert sm._state['phase'] == 'SCANNING'
```

- [ ] **Step 2: Jalankan tests — verifikasi SEMUA FAIL**

```bash
cd bot && pytest tests/test_signal_generator.py -v 2>&1 | head -40
```

Expected: semua test FAIL dengan `ImportError: cannot import name 'SignalStateMachine'` atau `AttributeError`.

---

## Task 4: Implementasi SignalStateMachine di signal_generator.py

**Files:**
- Rewrite: `bot/signal_generator.py`

- [ ] **Step 1: Tulis ulang signal_generator.py**

Ganti seluruh isi `bot/signal_generator.py` dengan:

```python
import json
import logging
import os
import pandas as pd
from ta.trend import EMAIndicator
from ta.volatility import AverageTrueRange

logger = logging.getLogger(__name__)

_TF_H1 = 16385
_TF_M15 = 15

EMA_H1_FAST = 20
EMA_H1_SLOW = 50
EMA_FAST_PERIOD = 14
EMA_SLOW_PERIOD = 24

PULLBACK_MAX_CANDLES = 3
ARMED_TIMEOUT_CANDLES = 5
ENTRY_WINDOW_CANDLES = 2

ATR_PERIOD = 14
ATR_AVG_WINDOW = 20
ATR_EXTREME_MULTIPLIER = 1.8
EMA_MIN_SLOPE = 0.5

SL_ATR_MULTIPLIER = 2.0

_DEFAULT_STATE_FILE = os.getenv("STATE_FILE", "/app/state.json")


class SignalStateMachine:

    def __init__(self, state_file: str = _DEFAULT_STATE_FILE):
        self._state_file = state_file
        self._state = self._load_state()

    def tick(self, mt5_conn, symbol: str) -> tuple[str, float | None]:
        ind = self._get_indicators(mt5_conn, symbol)
        if ind is None:
            return 'NONE', None

        if ind['atr_avg'] is not None and ind['atr_current'] > ind['atr_avg'] * ATR_EXTREME_MULTIPLIER:
            logger.debug(f"ATR extreme ({ind['atr_current']:.2f} > {ind['atr_avg'] * ATR_EXTREME_MULTIPLIER:.2f}) — skip")
            return 'NONE', None

        phase = self._state.get('phase', 'SCANNING')
        if phase == 'SCANNING':
            return self._phase_scanning(ind)
        if phase == 'ARMED':
            return self._phase_armed(ind)
        if phase == 'WINDOW_OPEN':
            return self._phase_window_open(ind)
        return 'NONE', None

    def _get_indicators(self, mt5_conn, symbol):
        rates_h1 = mt5_conn.get_rates(symbol, _TF_H1, 100)
        if rates_h1 is None or len(rates_h1) < 52:
            logger.debug("Not enough H1 candles")
            return None

        close_h1 = pd.Series([float(r['close']) for r in rates_h1])
        ema20 = EMAIndicator(close_h1, window=EMA_H1_FAST).ema_indicator()
        ema50 = EMAIndicator(close_h1, window=EMA_H1_SLOW).ema_indicator()

        if ema20.iloc[-1] > ema50.iloc[-1]:
            trend = 'BULLISH'
        elif ema20.iloc[-1] < ema50.iloc[-1]:
            trend = 'BEARISH'
        else:
            return None

        rates_m15 = mt5_conn.get_rates(symbol, _TF_M15, 100)
        if rates_m15 is None or len(rates_m15) < 30:
            logger.debug("Not enough M15 candles")
            return None

        close_m15 = pd.Series([float(r['close']) for r in rates_m15])
        open_m15  = pd.Series([float(r['open']) for r in rates_m15])
        high_m15  = pd.Series([float(r['high']) for r in rates_m15])
        low_m15   = pd.Series([float(r['low'])  for r in rates_m15])

        ema14      = EMAIndicator(close_m15, window=EMA_FAST_PERIOD).ema_indicator()
        ema24      = EMAIndicator(close_m15, window=EMA_SLOW_PERIOD).ema_indicator()
        atr_series = AverageTrueRange(high_m15, low_m15, close_m15, window=ATR_PERIOD).average_true_range()

        atr_current = float(atr_series.iloc[-1])
        atr_avg_raw = atr_series.rolling(ATR_AVG_WINDOW).mean().iloc[-1]
        atr_avg     = float(atr_avg_raw) if pd.notna(atr_avg_raw) else None

        slope = float(ema14.iloc[-1]) - float(ema14.iloc[-4])

        logger.info(
            f"H1 trend: {trend} | M15 EMA14={ema14.iloc[-1]:.2f} EMA24={ema24.iloc[-1]:.2f} "
            f"slope={slope:.3f} ATR={atr_current:.2f}"
        )

        return {
            'trend': trend,
            'ema14': ema14,
            'ema24': ema24,
            'slope': slope,
            'open_m15': open_m15,
            'high_m15': high_m15,
            'low_m15': low_m15,
            'price': float(close_m15.iloc[-1]),
            'atr_current': atr_current,
            'atr_avg': atr_avg,
        }

    def _phase_scanning(self, ind) -> tuple[str, float | None]:
        if abs(ind['slope']) < EMA_MIN_SLOPE:
            logger.debug(f"Slope too flat ({ind['slope']:.3f}) — skip crossover")
            return 'NONE', None

        ema14, ema24 = ind['ema14'], ind['ema24']
        prev14 = float(ema14.iloc[-2])
        curr14 = float(ema14.iloc[-1])
        prev24 = float(ema24.iloc[-2])
        curr24 = float(ema24.iloc[-1])
        trend  = ind['trend']

        direction = None
        if trend == 'BULLISH' and prev14 < prev24 and curr14 >= curr24:
            direction = 'BUY'
        elif trend == 'BEARISH' and prev14 > prev24 and curr14 <= curr24:
            direction = 'SELL'

        if direction:
            logger.info(f"SCANNING→ARMED: {direction} crossover, slope={ind['slope']:.3f}")
            self._state = {
                'phase': 'ARMED',
                'direction': direction,
                'pullback_count': 0,
                'pullback_high': None,
                'pullback_low': None,
                'breakout_level': None,
                'armed_candles_elapsed': 0,
                'window_candles_elapsed': 0,
            }
            self._save_state()

        return 'NONE', None

    def _phase_armed(self, ind) -> tuple[str, float | None]:
        direction = self._state['direction']
        expected_trend = 'BULLISH' if direction == 'BUY' else 'BEARISH'

        if ind['trend'] != expected_trend:
            logger.info("ARMED→SCANNING: trend reversed")
            self._reset()
            return 'NONE', None

        ema14 = float(ind['ema14'].iloc[-1])
        ema24 = float(ind['ema24'].iloc[-1])
        if direction == 'BUY' and ema14 < ema24:
            logger.info("ARMED→SCANNING: EMA crossed back")
            self._reset()
            return 'NONE', None
        if direction == 'SELL' and ema14 > ema24:
            logger.info("ARMED→SCANNING: EMA crossed back")
            self._reset()
            return 'NONE', None

        self._state['armed_candles_elapsed'] += 1
        if self._state['armed_candles_elapsed'] >= ARMED_TIMEOUT_CANDLES:
            logger.info("ARMED→SCANNING: timeout")
            self._reset()
            return 'NONE', None

        close = ind['price']
        open_ = float(ind['open_m15'].iloc[-1])
        high  = float(ind['high_m15'].iloc[-1])
        low   = float(ind['low_m15'].iloc[-1])

        is_pullback = (
            (direction == 'BUY'  and close < open_) or
            (direction == 'SELL' and close > open_)
        )

        if is_pullback:
            self._state['pullback_count'] += 1
            ph = self._state.get('pullback_high')
            pl = self._state.get('pullback_low')
            self._state['pullback_high'] = high if ph is None else max(ph, high)
            self._state['pullback_low']  = low  if pl is None else min(pl, low)

        if self._state['pullback_count'] >= 1:
            bl = (self._state['pullback_high'] if direction == 'BUY'
                  else self._state['pullback_low'])
            logger.info(f"ARMED→WINDOW_OPEN: direction={direction} breakout_level={bl:.2f}")
            self._state['phase']          = 'WINDOW_OPEN'
            self._state['breakout_level'] = bl
            self._state['window_candles_elapsed'] = 0

        self._save_state()
        return 'NONE', None

    def _phase_window_open(self, ind) -> tuple[str, float | None]:
        direction      = self._state['direction']
        breakout_level = self._state['breakout_level']
        price          = ind['price']
        expected_trend = 'BULLISH' if direction == 'BUY' else 'BEARISH'

        if ind['trend'] != expected_trend:
            logger.info("WINDOW_OPEN→SCANNING: trend reversed")
            self._reset()
            return 'NONE', None

        self._state['window_candles_elapsed'] += 1
        if self._state['window_candles_elapsed'] > ENTRY_WINDOW_CANDLES:
            logger.info("WINDOW_OPEN→SCANNING: timeout")
            self._reset()
            return 'NONE', None

        if direction == 'BUY' and price > breakout_level:
            sl = round(price - SL_ATR_MULTIPLIER * ind['atr_current'], 2)
            logger.info(f"ENTRY BUY: price={price:.2f} > breakout={breakout_level:.2f}, SL={sl:.2f}")
            self._reset()
            return 'BUY', sl

        if direction == 'SELL' and price < breakout_level:
            sl = round(price + SL_ATR_MULTIPLIER * ind['atr_current'], 2)
            logger.info(f"ENTRY SELL: price={price:.2f} < breakout={breakout_level:.2f}, SL={sl:.2f}")
            self._reset()
            return 'SELL', sl

        self._save_state()
        return 'NONE', None

    def _reset(self):
        self._state = {'phase': 'SCANNING'}
        self._save_state()

    def _load_state(self) -> dict:
        try:
            with open(self._state_file) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {'phase': 'SCANNING'}

    def _save_state(self):
        try:
            with open(self._state_file, 'w') as f:
                json.dump(self._state, f, indent=2)
        except OSError as e:
            logger.warning(f"Cannot save state: {e}")
```

- [ ] **Step 2: Jalankan tests — verifikasi semua PASS**

```bash
cd bot && pytest tests/test_signal_generator.py -v
```

Expected: semua 20 test PASS.

- [ ] **Step 3: Commit**

```bash
git add bot/signal_generator.py bot/tests/test_signal_generator.py
git commit -m "feat: implement SignalStateMachine — 4-phase EMA channel strategy v2"
```

---

## Task 5: Wire signal_watcher.py + Fix test_signal_watcher.py

**Files:**
- Modify: `bot/signal_watcher.py`
- Modify: `bot/tests/test_signal_watcher.py`

- [ ] **Step 1: Update import di signal_watcher.py**

Ganti baris 12 di `bot/signal_watcher.py`:

```python
from signal_generator import get_signal
```

Dengan:

```python
from signal_generator import SignalStateMachine
```

- [ ] **Step 2: Tambah state_machine di `__init__`**

Di dalam `def __init__(self, ...)` di `signal_watcher.py`, tambahkan setelah `self._in_active_hours: bool = False`:

```python
        self._state_machine: SignalStateMachine = SignalStateMachine()
```

- [ ] **Step 3: Ganti pemanggilan get_signal di `_try_generate_signal`**

Cari baris 201 di `bot/signal_watcher.py`:

```python
        signal, sl_price = get_signal(self.mt5, config.SYMBOL)
        logger.info(f"Signal: {signal}")
```

Ganti dengan:

```python
        signal, sl_price = self._state_machine.tick(self.mt5, config.SYMBOL)
        logger.info(f"Signal: {signal}")
```

- [ ] **Step 4: Jalankan test_signal_watcher.py — lihat apa yang fail**

```bash
cd bot && pytest tests/test_signal_watcher.py -v 2>&1
```

Expected: `test_paused_bot_does_not_generate_signal` FAIL karena masih patch `signal_watcher.get_signal` yang sudah tidak ada.

- [ ] **Step 5: Fix test_paused_bot_does_not_generate_signal**

Di `bot/tests/test_signal_watcher.py`, cari test ini (sekitar baris 107):

```python
def test_paused_bot_does_not_generate_signal():
    """Bot yang di-pause tidak memanggil get_signal."""
    from signal_watcher import SignalWatcher
    mt5 = make_mt5(balance=100.0, positions=[])
    watcher = SignalWatcher(mt5)
    watcher._known_tickets = set()
    watcher._paused = True
    watcher._day_start_balance = 100.0

    with patch("signal_watcher.is_active_trading_hour", return_value=True):
        with patch("signal_watcher.get_signal") as mock_signal:
            watcher.tick()
            mock_signal.assert_not_called()
```

Ganti dengan:

```python
def test_paused_bot_does_not_generate_signal():
    """Bot yang di-pause tidak memanggil state_machine.tick."""
    from signal_watcher import SignalWatcher
    mt5 = make_mt5(balance=100.0, positions=[])
    watcher = SignalWatcher(mt5)
    watcher._known_tickets = set()
    watcher._paused = True
    watcher._day_start_balance = 100.0

    with patch("signal_watcher.is_active_trading_hour", return_value=True):
        with patch.object(watcher._state_machine, 'tick') as mock_tick:
            watcher.tick()
            mock_tick.assert_not_called()
```

- [ ] **Step 6: Jalankan semua tests — verifikasi semua pass**

```bash
cd bot && pytest tests/ -v
```

Expected: semua test di seluruh test suite PASS.

- [ ] **Step 7: Commit**

```bash
git add bot/signal_watcher.py bot/tests/test_signal_watcher.py
git commit -m "feat: wire SignalStateMachine into signal_watcher, replace get_signal"
```

---

## Ringkasan Perubahan

| Komponen | V1 | V2 |
|---|---|---|
| Signal entry | RSI cross 50 + BB midline + pullback (semua sekaligus) | 4-phase: crossover → pullback → breakout |
| SL | 1.5x ATR | 2.0x ATR |
| TP1 | 1:1 RR | 1.5:1 RR |
| TP2 | 3:1 RR | 4:1 RR |
| Volatility filter | Tidak ada | ATR extreme (>1.8x avg) |
| Sideways filter | Tidak ada | EMA slope (<0.5) |
| State recovery | Tidak ada | `/app/state.json` |
