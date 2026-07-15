# London Breakout XAUUSD Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backtest 3 tahun strategi London Breakout XAUUSD persis aturan bot, baseline + 36 kombinasi variasi, dengan laporan metrik dan dua simulasi akun.

**Architecture:** Folder `backtest/` terpisah dari `bot/`. Data M1 diunduh sekali via `dukascopy-node` (Node v24 tersedia) ke CSV. Simulator Python murni memproses bar hari-per-hari (range Asia → pending stop OCO → manajemen TP1/BE/TP2/SL), metrics terpisah, runner CLI menghasilkan report markdown + grafik PNG.

**Tech Stack:** Python 3.14 (`py` launcher di mesin ini), pandas, matplotlib, pytest. Node/npx hanya untuk download data.

**Spec:** `docs/superpowers/specs/2026-07-15-london-breakout-backtest-design.md`

**PENTING untuk executor:**
- Python di mesin ini dipanggil dengan `py`, BUKAN `python` (alias `python` mengarah ke Microsoft Store stub).
- Jalankan pytest dengan `py -m pytest backtest/tests -v` dari root repo.
- Sebelum menulis kode grafik (Task 8), baca skill `dataviz` sesuai trigger-nya.

## File Structure

```
backtest/
├── __init__.py           # kosong — agar importable dari tests
├── params.py             # dataclass Params (semua knob strategi)
├── download_data.py      # wrapper npx dukascopy-node → backtest/data/xauusd_m1.csv
├── loader.py             # CSV → DataFrame OHLC bid, index tz WIB
├── simulator.py          # Trade, DayResult, simulate() — engine inti
├── metrics.py            # stats trade, equity curve ideal & riil, max DD, monthly
├── run_backtest.py       # CLI: baseline + grid 36 varian → report.md + PNG; --audit
├── data/                 # CSV hasil unduhan (gitignored)
├── results/              # report + grafik (di-commit)
└── tests/
    ├── __init__.py
    ├── conftest.py        # helper pembuat bar sintetis
    ├── test_loader.py
    ├── test_simulator.py
    └── test_metrics.py
```

---

### Task 1: Scaffolding + Params

**Files:**
- Create: `backtest/__init__.py`, `backtest/tests/__init__.py`, `backtest/params.py`
- Modify: `.gitignore`

- [ ] **Step 1: Buat direktori dan file kosong**

```powershell
New-Item -ItemType Directory -Force backtest/tests, backtest/data, backtest/results
New-Item -ItemType File backtest/__init__.py, backtest/tests/__init__.py
```

- [ ] **Step 2: Tambah ke `.gitignore`** (buat file jika belum ada; jika sudah ada, append)

```
backtest/data/
```

- [ ] **Step 3: Tulis `backtest/params.py`**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Params:
    range_min: float = 5.0       # USD — skip jika range Asia < ini
    range_max: float = 35.0      # USD — skip jika range Asia > ini
    entry_buffer: float = 0.5    # USD di luar tepi range
    sl_buffer: float = 0.3       # USD di luar tepi seberang (mode 'opposite')
    tp_rr: float = 1.5           # TP = tp_rr × range dari entry
    sl_mode: str = "opposite"    # 'opposite' (baseline bot) | 'mid' (tengah range)
    tp1_enabled: bool = True     # TP1 midpoint + partial 50% + SL→BE
    spread: float = 0.30         # USD — data bid, ask = bid + spread
    slippage: float = 0.0        # USD — memperburuk harga entry stop order

    def label(self) -> str:
        return (f"sl={self.sl_mode} tp_rr={self.tp_rr} "
                f"range_max={self.range_max} tp1={'on' if self.tp1_enabled else 'off'}")


BASELINE = Params()
```

- [ ] **Step 4: Commit**

```bash
git add backtest .gitignore
git commit -m "feat(backtest): scaffold backtest package with strategy params"
```

---

### Task 2: Download data Dukascopy (mulai di awal, biarkan jalan background)

**Files:**
- Create: `backtest/download_data.py`

Download 3 tahun M1 memakan beberapa menit — mulai sekarang, lanjut Task 3 sambil menunggu.

- [ ] **Step 1: Verifikasi flag CLI dukascopy-node**

Run: `npx dukascopy-node --help`
Expected: daftar opsi berisi `--instrument`, `--date-from`, `--date-to`, `--timeframe`, `--format`, `--directory`, `--volumes` (atau bentuk pendeknya). Jika nama flag berbeda dari Step 2, sesuaikan Step 2 dengan output help.

- [ ] **Step 2: Tulis `backtest/download_data.py`**

```python
"""Unduh XAUUSD M1 (bid) dari Dukascopy via dukascopy-node ke backtest/data/xauusd_m1.csv."""
import glob
import os
import shutil
import subprocess
import sys

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
TARGET = os.path.join(DATA_DIR, "xauusd_m1.csv")
DATE_FROM = "2023-07-01"
DATE_TO = "2026-07-15"


def main():
    if os.path.exists(TARGET):
        print(f"{TARGET} sudah ada — skip download. Hapus file untuk mengunduh ulang.")
        return
    cmd = [
        "npx", "dukascopy-node",
        "--instrument", "xauusd",
        "--date-from", DATE_FROM,
        "--date-to", DATE_TO,
        "--timeframe", "m1",
        "--format", "csv",
        "--volumes", "true",
        "--directory", DATA_DIR,
        "--retries", "5",
    ]
    print("Menjalankan:", " ".join(cmd))
    subprocess.run(cmd, check=True, shell=(os.name == "nt"))
    produced = glob.glob(os.path.join(DATA_DIR, "xauusd-m1-*.csv"))
    if not produced:
        sys.exit("Download selesai tapi tidak ada file xauusd-m1-*.csv di backtest/data/")
    shutil.move(max(produced, key=os.path.getmtime), TARGET)
    size_mb = os.path.getsize(TARGET) / 1e6
    print(f"OK: {TARGET} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Jalankan download di background**

Run (background, timeout panjang): `py backtest/download_data.py`
Expected saat selesai: `OK: ...xauusd_m1.csv (>50 MB)`. ~1,1 juta baris untuk 3 tahun. Lanjutkan ke Task 3 sambil menunggu; cek hasil sebelum Task 9.

- [ ] **Step 4: Commit**

```bash
git add backtest/download_data.py
git commit -m "feat(backtest): dukascopy-node data downloader"
```

---

### Task 3: Loader CSV → DataFrame WIB

**Files:**
- Create: `backtest/loader.py`
- Test: `backtest/tests/test_loader.py`

Format CSV dukascopy-node: header `timestamp,open,high,low,close,volume`, timestamp = epoch **milidetik** UTC, harga bid.

- [ ] **Step 1: Tulis failing test `backtest/tests/test_loader.py`**

```python
import io
import pandas as pd
from backtest.loader import load_m1_csv

CSV = """timestamp,open,high,low,close,volume
1704067200000,2062.5,2063.0,2062.0,2062.8,120.5
1704067260000,2062.8,2064.0,2062.5,2063.5,98.0
1704067320000,2063.5,2063.5,2063.5,2063.5,0
"""


def test_load_converts_to_wib_and_drops_zero_volume():
    df = load_m1_csv(io.StringIO(CSV))
    # 1704067200000 ms = 2024-01-01 00:00 UTC = 07:00 WIB
    assert str(df.index.tz) == "Asia/Jakarta"
    assert df.index[0].hour == 7 and df.index[0].minute == 0
    assert list(df.columns) == ["open", "high", "low", "close"]
    assert len(df) == 2  # baris volume 0 (bar sintetis flat) dibuang
    assert df.iloc[1]["high"] == 2064.0
```

- [ ] **Step 2: Jalankan test, pastikan gagal**

Run: `py -m pytest backtest/tests/test_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backtest.loader'`

- [ ] **Step 3: Tulis `backtest/loader.py`**

```python
import pandas as pd

WIB = "Asia/Jakarta"


def load_m1_csv(path_or_buf) -> pd.DataFrame:
    """CSV dukascopy-node (timestamp ms UTC, bid OHLCV) → DataFrame OHLC index WIB.

    Bar dengan volume 0 (bar flat sintetis saat pasar tutup) dibuang.
    """
    df = pd.read_csv(path_or_buf)
    df = df[df["volume"] > 0]
    idx = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_convert(WIB)
    out = df[["open", "high", "low", "close"]].copy()
    out.index = idx
    out.index.name = "time"
    return out.sort_index()
```

- [ ] **Step 4: Jalankan test, pastikan lolos**

Run: `py -m pytest backtest/tests/test_loader.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backtest/loader.py backtest/tests/test_loader.py
git commit -m "feat(backtest): M1 CSV loader with WIB timezone"
```

---

### Task 4: Helper test bar sintetis + range Asia & klasifikasi hari

**Files:**
- Create: `backtest/tests/conftest.py`, `backtest/simulator.py`
- Test: `backtest/tests/test_simulator.py`

Angka acuan semua test simulator (spread 0.30, buffer 0.5/0.3, params default):
- Bar Asia: high bid max = **2005.0**, low bid min = **1995.0**
- `asian_high_ask` = 2005.30, `asian_low_bid` = 1995.00, **range = 10.30** (valid, 5–35)
- `buy_stop` = 2005.80 (ask) · `sell_stop` = 1994.50 (bid)
- `sl_buy` = 1994.70 · `sl_sell` = 2005.60 (mode opposite)
- `tp_buy` = 2005.80 + 1.5×10.30 = **2021.25** · `tp_sell` = 1994.50 − 15.45 = **1979.05**
- `risk_buy` = 11.10 · `tp1_buy` = round((2005.80+2021.25)/2, 2) = **2013.52** (dibulatkan 2dp seperti bot)

- [ ] **Step 1: Tulis `backtest/tests/conftest.py`**

```python
import pandas as pd

WIB = "Asia/Jakarta"

# Bar Asia standar: menghasilkan high 2005 / low 1995 (range 10.30 dgn spread 0.30)
ASIAN_BARS = [
    ("07:00", 2000.0, 2005.0, 1995.0, 2001.0),
    ("13:00", 2001.0, 2004.0, 1996.0, 2000.0),
]


def make_bars(date_str: str, bars: list[tuple]) -> pd.DataFrame:
    """bars: list of ('HH:MM', open, high, low, close) → DataFrame index WIB."""
    idx = pd.DatetimeIndex(
        [f"{date_str} {hhmm}" for hhmm, *_ in bars]
    ).tz_localize(WIB)
    df = pd.DataFrame(
        [list(vals) for _, *vals in bars],
        columns=["open", "high", "low", "close"],
        index=idx,
    )
    df.index.name = "time"
    return df


def make_day(date_str: str, window_bars: list[tuple],
             asian_bars: list[tuple] = None) -> pd.DataFrame:
    return make_bars(date_str, (asian_bars or ASIAN_BARS) + window_bars)
```

- [ ] **Step 2: Tulis failing tests klasifikasi hari di `backtest/tests/test_simulator.py`**

```python
import pandas as pd
from backtest.params import Params
from backtest.simulator import simulate
from backtest.tests.conftest import make_day, make_bars

P = Params()  # baseline


def run_one(df, params=P):
    results = simulate(df, params)
    assert len(results) == 1
    return results[0]


def test_range_valid_computed():
    day = run_one(make_day("2025-03-04", [("14:50", 2000, 2001, 1999, 2000)]))
    assert day.range_size == 10.30
    assert day.status == "no_breakout"


def test_range_too_narrow_skipped():
    asian = [("07:00", 2000.0, 2001.0, 1999.0, 2000.5),
             ("13:00", 2000.5, 2001.0, 1999.5, 2000.0)]  # range 2.30 < 5
    day = run_one(make_day("2025-03-04", [("14:50", 2000, 2001, 1999, 2000)], asian))
    assert day.status == "range_invalid_narrow"


def test_range_too_wide_skipped():
    asian = [("07:00", 2000.0, 2040.0, 1995.0, 2001.0),
             ("13:00", 2001.0, 2004.0, 1996.0, 2000.0)]  # range 45.30 > 35
    day = run_one(make_day("2025-03-04", [("14:50", 2000, 2001, 1999, 2000)], asian))
    assert day.status == "range_invalid_wide"


def test_no_asian_data():
    df = make_bars("2025-03-04", [("15:00", 2000, 2001, 1999, 2000)])
    day = run_one(df)
    assert day.status == "no_data"


def test_pre_broken_buy_side():
    # open 14:50 = 2006 → ask 2006.30 >= buy_stop 2005.80
    day = run_one(make_day("2025-03-04", [("14:50", 2006.0, 2007, 2005, 2006)]))
    assert day.status == "pre_broken"


def test_no_breakout_expires():
    day = run_one(make_day("2025-03-04", [
        ("14:50", 2000, 2002, 1999, 2001),
        ("16:59", 2001, 2003, 2000, 2002),
    ]))
    assert day.status == "no_breakout"
    assert day.trade is None
```

- [ ] **Step 3: Jalankan tests, pastikan gagal**

Run: `py -m pytest backtest/tests/test_simulator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backtest.simulator'`

- [ ] **Step 4: Tulis `backtest/simulator.py` — struktur data + klasifikasi hari + trigger + manajemen posisi**

Ini modul inti — ditulis lengkap sekali di sini; Task 5–6 hanya menambah test terhadap perilaku yang sudah didefinisikan berikut.

```python
"""Simulator London Breakout — mereplikasi aturan bot/signal_watcher.py + signal_generator.py.

Konvensi harga: data = bid. ask = bid + params.spread.
BUY : trigger & entry di ask (level buy_stop adalah harga ask), exit dicek di bid.
SELL: trigger & entry di bid, exit dicek di ask.
Worst-case intra-bar: SL diperiksa lebih dulu; setelah TP1 tereksekusi dalam
sebuah bar, tidak ada event lain yang diproses di bar yang sama.
"""
from dataclasses import dataclass, field
from datetime import datetime, time

import pandas as pd

from backtest.params import Params

ASIAN_START = time(7, 0)
ASIAN_END = time(14, 0)     # eksklusif
PLACE_TIME = time(14, 50)
EXPIRY_TIME = time(17, 0)   # eksklusif


@dataclass
class Trade:
    direction: str            # 'buy' | 'sell'
    entry_time: datetime
    entry: float
    sl: float                 # SL awal
    tp1: float | None
    tp2: float
    risk: float               # |entry − sl| (jarak harga)
    whipsaw: bool = False
    tp1_hit: bool = False
    exit_time: datetime | None = None
    exit_reason: str = ""     # 'sl' | 'be' | 'tp2' | 'end_of_data'
    r_multiple: float = 0.0
    crossed_midnight: bool = False
    crossed_weekend: bool = False

    @property
    def hold_minutes(self) -> float:
        if self.exit_time is None:
            return 0.0
        return (self.exit_time - self.entry_time).total_seconds() / 60


@dataclass
class DayResult:
    date: object
    status: str               # 'traded'|'no_breakout'|'range_invalid_narrow'|
                              # 'range_invalid_wide'|'pre_broken'|'no_data'
    range_size: float | None = None
    whipsaw: bool = False
    trade: Trade | None = None


def simulate(df: pd.DataFrame, params: Params) -> list[DayResult]:
    """df: OHLC bid, DatetimeIndex tz WIB, terurut. Return satu DayResult per hari kalender ber-data."""
    times = df.index
    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    tod = [t.time() for t in times]           # time-of-day per bar
    dates = times.date

    results: list[DayResult] = []
    n = len(df)
    i = 0
    # indeks awal setiap hari kalender
    day_starts: dict = {}
    for k in range(n):
        day_starts.setdefault(dates[k], k)

    for day, start in day_starts.items():
        end = start
        while end < n and dates[end] == day:
            end += 1
        results.append(_simulate_day(
            day, start, end, times, opens, highs, lows, closes, tod, params, n
        ))
    return results


def _simulate_day(day, start, end, times, opens, highs, lows, closes, tod,
                  params: Params, n: int) -> DayResult:
    sp = params.spread

    # --- Range Asia (replikasi bot: high dari ask, low dari bid) ---
    hi = lo = None
    for k in range(start, end):
        if ASIAN_START <= tod[k] < ASIAN_END:
            if hi is None or highs[k] > hi:
                hi = highs[k]
            if lo is None or lows[k] < lo:
                lo = lows[k]
    if hi is None:
        return DayResult(day, "no_data")

    asian_high = round(hi + sp, 2)            # ask
    asian_low = round(lo, 2)                  # bid
    rng = round(asian_high - asian_low, 2)
    if rng < params.range_min:
        return DayResult(day, "range_invalid_narrow", rng)
    if rng > params.range_max:
        return DayResult(day, "range_invalid_wide", rng)

    buy_stop = round(asian_high + params.entry_buffer, 2)    # ask
    sell_stop = round(asian_low - params.entry_buffer, 2)    # bid
    if params.sl_mode == "mid":
        mid = round((asian_high + asian_low) / 2, 2)
        sl_buy = sl_sell = mid
    else:  # 'opposite' — baseline bot
        sl_buy = round(asian_low - params.sl_buffer, 2)
        sl_sell = round(asian_high + params.sl_buffer, 2)
    tp_buy = round(buy_stop + rng * params.tp_rr, 2)
    tp_sell = round(sell_stop - rng * params.tp_rr, 2)

    # --- Window 14:50–17:00: cari trigger ---
    win = [k for k in range(start, end) if PLACE_TIME <= tod[k] < EXPIRY_TIME]
    if not win:
        return DayResult(day, "no_data", rng)

    first = win[0]
    if opens[first] + sp >= buy_stop or opens[first] <= sell_stop:
        return DayResult(day, "pre_broken", rng)

    for k in win:
        buy_trig = highs[k] + sp >= buy_stop
        sell_trig = lows[k] <= sell_stop
        if not (buy_trig or sell_trig):
            continue
        whipsaw = buy_trig and sell_trig
        if whipsaw:
            dist_buy = buy_stop - (opens[k] + sp)
            dist_sell = opens[k] - sell_stop
            direction = "buy" if dist_buy <= dist_sell else "sell"
        else:
            direction = "buy" if buy_trig else "sell"

        if direction == "buy":
            entry = round(buy_stop + params.slippage, 2)
            trade = Trade("buy", times[k], entry, sl_buy,
                          round((entry + tp_buy) / 2, 2) if params.tp1_enabled else None,
                          tp_buy, round(entry - sl_buy, 2), whipsaw=whipsaw)
        else:
            entry = round(sell_stop - params.slippage, 2)
            trade = Trade("sell", times[k], entry, sl_sell,
                          round((entry + tp_sell) / 2, 2) if params.tp1_enabled else None,
                          tp_sell, round(sl_sell - entry, 2), whipsaw=whipsaw)

        _manage(trade, k, times, highs, lows, closes, params, n)
        return DayResult(day, "traded", rng, whipsaw, trade)

    return DayResult(day, "no_breakout", rng)


def _manage(trade: Trade, entry_idx: int, times, highs, lows, closes,
            params: Params, n: int) -> None:
    """Jalankan posisi dari bar entry sampai exit. Mutasi trade in-place."""
    sp = params.spread
    buy = trade.direction == "buy"
    current_sl = trade.sl
    remaining = 1.0
    r_total = 0.0

    def r_of(exit_price: float, fraction: float) -> float:
        sign = 1.0 if buy else -1.0
        return sign * (exit_price - trade.entry) / trade.risk * fraction

    for k in range(entry_idx, n):
        if buy:
            sl_hit = lows[k] <= current_sl
            tp1_hit = (trade.tp1 is not None and not trade.tp1_hit
                       and highs[k] >= trade.tp1)
            tp2_hit = highs[k] >= trade.tp2
        else:
            sl_hit = highs[k] + sp >= current_sl
            tp1_hit = (trade.tp1 is not None and not trade.tp1_hit
                       and lows[k] + sp <= trade.tp1)
            tp2_hit = lows[k] + sp <= trade.tp2

        if sl_hit:  # worst-case: SL menang atas TP di bar yang sama
            r_total += r_of(current_sl, remaining)
            trade.exit_reason = "be" if trade.tp1_hit else "sl"
            _finish(trade, times[k], r_total)
            return
        if tp1_hit:
            r_total += r_of(trade.tp1, 0.5)
            remaining = 0.5
            trade.tp1_hit = True
            current_sl = trade.entry  # breakeven
            continue  # tidak ada event lain di bar yang sama
        if tp2_hit:
            r_total += r_of(trade.tp2, remaining)
            trade.exit_reason = "tp2"
            _finish(trade, times[k], r_total)
            return

    # data habis — tutup di close bar terakhir
    last_close = closes[n - 1] if buy else closes[n - 1] + sp
    r_total += r_of(last_close, remaining)
    trade.exit_reason = "end_of_data"
    _finish(trade, times[n - 1], r_total)


def _finish(trade: Trade, exit_time, r_total: float) -> None:
    trade.exit_time = exit_time
    trade.r_multiple = round(r_total, 4)
    if exit_time.date() != trade.entry_time.date():
        trade.crossed_midnight = True
        span_days = (exit_time.date() - trade.entry_time.date()).days
        if span_days > 2 or exit_time.weekday() < trade.entry_time.weekday():
            trade.crossed_weekend = True
```

- [ ] **Step 5: Jalankan tests klasifikasi, pastikan lolos**

Run: `py -m pytest backtest/tests/test_simulator.py -v`
Expected: 6 PASS

- [ ] **Step 6: Commit**

```bash
git add backtest/simulator.py backtest/tests/conftest.py backtest/tests/test_simulator.py
git commit -m "feat(backtest): simulator core - asian range, day classification, OCO trigger, position management"
```

---

### Task 5: Test trigger entry, spread, whipsaw

**Files:**
- Test: `backtest/tests/test_simulator.py` (append)

Perilaku sudah diimplementasikan di Task 4 — task ini menambahkan test yang membuktikannya benar.

- [ ] **Step 1: Tambah tests berikut ke `backtest/tests/test_simulator.py`**

```python
def test_buy_triggered_with_spread():
    # high 2006 → ask 2006.30 >= buy_stop 2005.80 → BUY @2005.80
    # high bid 2006 TIDAK menyentuh buy_stop tanpa spread (2005.80 > 2006? tidak —
    # justru test sebaliknya di bawah). Di sini pastikan entry & level benar.
    day = run_one(make_day("2025-03-04", [
        ("14:50", 2000, 2002, 1999, 2001),
        ("15:00", 2001, 2006.0, 2000.8, 2005.5),
        ("15:30", 2005.5, 2022.0, 2005.0, 2021.0),  # tp2 2021.25? high 2022 >= → exit
    ]), Params(tp1_enabled=False))
    assert day.status == "traded"
    t = day.trade
    assert t.direction == "buy"
    assert t.entry == 2005.80
    assert t.sl == 1994.70 and t.tp2 == 2021.25
    assert t.exit_reason == "tp2"
    assert abs(t.r_multiple - (2021.25 - 2005.80) / 11.10) < 1e-9


def test_high_below_ask_threshold_no_trigger():
    # high 2005.4 → ask 2005.70 < buy_stop 2005.80 → tidak trigger
    day = run_one(make_day("2025-03-04", [
        ("15:00", 2001, 2005.4, 2000.8, 2005.0),
    ]))
    assert day.status == "no_breakout"


def test_sell_triggered():
    # low 1994.4 <= sell_stop 1994.50 → SELL @1994.50
    day = run_one(make_day("2025-03-04", [
        ("15:00", 2000, 2001.0, 1994.4, 1995.0),
        ("16:00", 1995, 1996.0, 1978.0, 1979.0),  # ask_low 1978.30 <= tp_sell 1979.05
    ]), Params(tp1_enabled=False))
    t = day.trade
    assert t.direction == "sell"
    assert t.entry == 1994.50 and t.tp2 == 1979.05
    assert t.exit_reason == "tp2"


def test_whipsaw_picks_side_closer_to_open():
    # open 1999 → dist_buy = 2005.80−1999.30 = 6.50 ; dist_sell = 1999−1994.50 = 4.50
    # → SELL dipilih, whipsaw tercatat
    day = run_one(make_day("2025-03-04", [
        ("15:00", 1999.0, 2007.0, 1993.0, 2000.0),
    ]), Params(tp1_enabled=False))
    assert day.status == "traded"
    assert day.whipsaw is True
    assert day.trade.direction == "sell"
```

- [ ] **Step 2: Jalankan, pastikan lolos**

Run: `py -m pytest backtest/tests/test_simulator.py -v`
Expected: semua PASS. (Jika `test_whipsaw...` gagal karena bar whipsaw juga menyentuh SL — low 1993 <= sl? SELL sl = 2005.60, ask_high = 2007.30 >= 2005.60 → SL hit di bar yang sama = benar sesuai aturan worst-case; assertion exit_reason tidak dicek di sini, hanya arah & whipsaw.)

- [ ] **Step 3: Commit**

```bash
git add backtest/tests/test_simulator.py
git commit -m "test(backtest): entry trigger, spread threshold, whipsaw side selection"
```

---

### Task 6: Test manajemen posisi — SL-first, TP1/BE, lintas hari

**Files:**
- Test: `backtest/tests/test_simulator.py` (append)

- [ ] **Step 1: Tambah tests**

```python
def test_sl_wins_over_tp_same_bar():
    # bar entry juga menyentuh SL dan TP2 → SL duluan → r = −1
    day = run_one(make_day("2025-03-04", [
        ("15:00", 2001, 2022.0, 1994.0, 2000.0),  # ask high 2022.30, low 1994 <= sl 1994.70
    ]), Params(tp1_enabled=False))
    t = day.trade
    assert t.exit_reason == "sl"
    assert abs(t.r_multiple - (-1.0)) < 1e-9


def test_tp1_partial_then_breakeven():
    # TP1 2013.52 disentuh (SL tidak), lalu bar berikut turun ke BE (entry 2005.80)
    day = run_one(make_day("2025-03-04", [
        ("15:00", 2001, 2006.0, 2000.8, 2005.5),   # BUY @2005.80
        ("15:30", 2006, 2014.0, 2005.0, 2013.0),   # TP1 hit → 50% @2013.52, SL→BE
        ("16:00", 2013, 2014.0, 2005.5, 2006.0),   # low 2005.5 <= BE 2005.80 → exit sisa
    ]))
    t = day.trade
    assert t.tp1_hit is True
    assert t.exit_reason == "be"
    expected = 0.5 * (2013.52 - 2005.80) / 11.10   # sisa 50% keluar di BE = 0R
    assert abs(t.r_multiple - expected) < 1e-6


def test_tp1_then_tp2_full_profit():
    day = run_one(make_day("2025-03-04", [
        ("15:00", 2001, 2006.0, 2000.8, 2005.5),
        ("15:30", 2006, 2014.0, 2005.9, 2013.0),   # TP1
        ("16:00", 2013, 2022.0, 2012.0, 2021.5),   # TP2 2021.25
    ]))
    t = day.trade
    assert t.exit_reason == "tp2"
    expected = 0.5 * (2013.52 - 2005.80) / 11.10 + 0.5 * (2021.25 - 2005.80) / 11.10
    assert abs(t.r_multiple - expected) < 1e-6


def test_tp1_and_tp2_same_bar_only_tp1_processed():
    # satu bar melompati TP1 dan TP2 → hanya TP1 dieksekusi di bar itu (aturan konservatif)
    day = run_one(make_day("2025-03-04", [
        ("15:00", 2001, 2006.0, 2000.8, 2005.5),
        ("15:30", 2006, 2022.0, 2005.9, 2021.0),   # tembus TP1 & TP2 sekaligus
        ("16:00", 2021, 2022.0, 2020.0, 2021.5),   # TP2 dieksekusi di bar berikut
    ]))
    t = day.trade
    assert t.tp1_hit is True and t.exit_reason == "tp2"


def test_position_carries_to_next_day():
    import pandas as pd
    d1 = make_day("2025-03-04", [("15:00", 2001, 2006.0, 2000.8, 2005.5),
                                 ("16:59", 2005, 2007.0, 2004.0, 2006.0)])
    # hari ke-2 hanya bar management (tanpa sesi Asia → status 'no_data'),
    # dibuat via make_bars agar tidak jatuh ke ASIAN_BARS default
    d2 = make_bars("2025-03-05", [("10:00", 2006, 2022.0, 2005.9, 2021.0)])
    df = pd.concat([d1, d2])
    results = simulate(df, Params(tp1_enabled=False))
    traded = [r for r in results if r.status == "traded"]
    assert len(traded) == 1
    t = traded[0].trade
    assert t.exit_reason == "tp2"
    assert t.crossed_midnight is True


def test_end_of_data_closes_at_last_close():
    day = run_one(make_day("2025-03-04", [
        ("15:00", 2001, 2006.0, 2000.8, 2005.5),
        ("16:59", 2005, 2007.0, 2004.0, 2010.0),
    ]), Params(tp1_enabled=False))
    t = day.trade
    assert t.exit_reason == "end_of_data"
    assert abs(t.r_multiple - (2010.0 - 2005.80) / 11.10) < 1e-9
```

- [ ] **Step 2: Jalankan, pastikan lolos**

Run: `py -m pytest backtest/tests/test_simulator.py -v`
Expected: semua PASS

- [ ] **Step 3: Commit**

```bash
git add backtest/tests/test_simulator.py
git commit -m "test(backtest): position management - SL-first, TP1/breakeven, cross-day carry"
```

---

### Task 7: Metrics — statistik trade + dua simulasi akun

**Files:**
- Create: `backtest/metrics.py`
- Test: `backtest/tests/test_metrics.py`

- [ ] **Step 1: Tulis failing tests `backtest/tests/test_metrics.py`**

```python
from datetime import datetime
from backtest.metrics import (trade_stats, equity_ideal, equity_real,
                              max_drawdown_pct, status_counts)
from backtest.simulator import Trade, DayResult


def _trade(r, risk=10.0, when="2025-03-04 15:00"):
    t = Trade("buy", datetime.fromisoformat(when), 2000.0, 2000.0 - risk,
              None, 2000.0 + risk * 1.5, risk)
    t.exit_time = t.entry_time
    t.r_multiple = r
    return t


def test_trade_stats():
    trades = [_trade(1.5), _trade(-1.0), _trade(1.5), _trade(-1.0)]
    s = trade_stats(trades)
    assert s["n"] == 4
    assert abs(s["winrate"] - 50.0) < 1e-9
    assert abs(s["profit_factor"] - 1.5) < 1e-9
    assert abs(s["expectancy_r"] - 0.25) < 1e-9


def test_equity_ideal_compounds_one_percent():
    eq = equity_ideal([_trade(2.0), _trade(-1.0)], start=10000.0, risk_pct=1.0)
    assert abs(eq[-1] - 10000.0 * 1.02 * 0.99) < 1e-6


def test_equity_real_min_lot_floor_over_risks():
    # balance 100, risk 1% = $1. SL $15 = 1500 points → lot ideal 0.0007 → floor 0.01
    # loss 1R = 1500 pts × $1 × 0.01 lot = $15 (15% akun, bukan 1%)
    eq = equity_real([_trade(-1.0, risk=15.0)], start=100.0)
    assert abs(eq[-1] - 85.0) < 1e-9


def test_equity_real_blowup_stops():
    trades = [_trade(-1.0, risk=30.0) for _ in range(5)]  # $30/trade
    eq = equity_real(trades, start=100.0)
    assert eq[-1] <= 10.0  # akun praktis habis
    assert len(eq) <= len(trades) + 1


def test_max_drawdown():
    assert abs(max_drawdown_pct([100, 120, 90, 130]) - 25.0) < 1e-9


def test_status_counts():
    days = [DayResult("d1", "traded"), DayResult("d2", "no_breakout"),
            DayResult("d3", "traded")]
    c = status_counts(days)
    assert c["traded"] == 2 and c["no_breakout"] == 1
```

- [ ] **Step 2: Jalankan, pastikan gagal**

Run: `py -m pytest backtest/tests/test_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backtest.metrics'`

- [ ] **Step 3: Tulis `backtest/metrics.py`**

```python
"""Statistik hasil backtest + simulasi akun (ideal 1% vs riil $100 MIN_LOT)."""
from collections import Counter

# Spesifikasi kontrak XAUUSD standar: 1 lot = 100 oz, point = 0.01 → $1/point/lot
POINT = 0.01
TICK_VALUE = 1.0
MIN_LOT = 0.01
MAX_LOT = 0.50


def trade_stats(trades) -> dict:
    rs = [t.r_multiple for t in trades]
    n = len(rs)
    if n == 0:
        return {"n": 0, "winrate": 0.0, "profit_factor": 0.0, "expectancy_r": 0.0,
                "avg_win_r": 0.0, "avg_loss_r": 0.0}
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    return {
        "n": n,
        "winrate": 100.0 * len(wins) / n,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else float("inf"),
        "expectancy_r": sum(rs) / n,
        "avg_win_r": (gross_win / len(wins)) if wins else 0.0,
        "avg_loss_r": (-gross_loss / len(losses)) if losses else 0.0,
    }


def _sorted_by_exit(trades):
    return sorted(trades, key=lambda t: t.exit_time)


def equity_ideal(trades, start: float = 10000.0, risk_pct: float = 1.0) -> list[float]:
    """Compounding risk_pct% per trade dengan lot fraksional sempurna."""
    eq = [start]
    for t in _sorted_by_exit(trades):
        eq.append(eq[-1] * (1.0 + risk_pct / 100.0 * t.r_multiple))
    return eq


def equity_real(trades, start: float = 100.0, risk_pct: float = 1.0) -> list[float]:
    """Replikasi bot/money_management.calculate_lot_size: floor ke MIN_LOT.
    Berhenti jika balance <= 0 (akun habis)."""
    eq = [start]
    for t in _sorted_by_exit(trades):
        balance = eq[-1]
        sl_points = round(t.risk / POINT)
        risk_usd = balance * risk_pct / 100.0
        lot = round(risk_usd / (sl_points * TICK_VALUE), 2)
        lot = max(MIN_LOT, min(MAX_LOT, lot))
        pnl = t.r_multiple * sl_points * TICK_VALUE * lot
        balance = balance + pnl
        eq.append(round(balance, 2))
        if balance <= 0:
            break
    return eq


def max_drawdown_pct(equity) -> float:
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0:
            max_dd = max(max_dd, (peak - v) / peak * 100.0)
    return max_dd


def status_counts(day_results) -> Counter:
    return Counter(d.status for d in day_results)


def monthly_r(trades) -> dict:
    """{'YYYY-MM': total R} berdasarkan waktu exit."""
    out: dict[str, float] = {}
    for t in _sorted_by_exit(trades):
        key = t.exit_time.strftime("%Y-%m")
        out[key] = round(out.get(key, 0.0) + t.r_multiple, 4)
    return out
```

- [ ] **Step 4: Jalankan, pastikan lolos**

Run: `py -m pytest backtest/tests/test_metrics.py -v`
Expected: 6 PASS

- [ ] **Step 5: Jalankan seluruh test suite backtest**

Run: `py -m pytest backtest/tests -v`
Expected: semua PASS

- [ ] **Step 6: Commit**

```bash
git add backtest/metrics.py backtest/tests/test_metrics.py
git commit -m "feat(backtest): trade stats, ideal vs real-account equity simulation"
```

---

### Task 8: Runner — grid 36 varian, report markdown, grafik

**Files:**
- Create: `backtest/run_backtest.py`

**Sebelum menulis kode grafik: baca skill `dataviz` (wajib per trigger skill tersebut).** Sesuaikan styling matplotlib dengan panduannya; struktur logika di bawah tetap.

- [ ] **Step 1: Tulis `backtest/run_backtest.py`**

```python
"""Runner backtest: baseline + grid 36 varian → results/report.md + PNG.

Pakai: py backtest/run_backtest.py            # full run
       py backtest/run_backtest.py --audit 2025-03-04   # detail satu hari (baseline)
"""
import argparse
import itertools
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from backtest.loader import load_m1_csv
from backtest.params import Params, BASELINE
from backtest.simulator import simulate
from backtest.metrics import (trade_stats, equity_ideal, equity_real,
                              max_drawdown_pct, status_counts, monthly_r)

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data", "xauusd_m1.csv")
RESULTS = os.path.join(HERE, "results")

SL_MODES = ["opposite", "mid"]
TP_RRS = [1.5, 2.0, 3.0]
RANGE_MAXES = [25.0, 35.0, 50.0]
TP1_OPTIONS = [True, False]


def run_variant(df, p: Params) -> dict:
    days = simulate(df, p)
    trades = [d.trade for d in days if d.trade is not None]
    stats = trade_stats(trades)
    eq_ideal = equity_ideal(trades)
    return {
        "params": p, "days": days, "trades": trades, "stats": stats,
        "eq_ideal": eq_ideal, "max_dd": max_drawdown_pct(eq_ideal),
        "statuses": status_counts(days),
    }


def fmt_row(v: dict) -> str:
    p, s = v["params"], v["stats"]
    star = " ★" if p == BASELINE else ""
    return (f"| {p.sl_mode} | {p.tp_rr} | {p.range_max:.0f} | "
            f"{'on' if p.tp1_enabled else 'off'} | {s['n']} | {s['winrate']:.1f}% | "
            f"{s['profit_factor']:.2f} | {s['expectancy_r']:+.3f} | "
            f"{v['max_dd']:.1f}% |{star}")


def write_report(variants: list[dict], df) -> str:
    base = next(v for v in variants if v["params"] == BASELINE)
    trades, s, days = base["trades"], base["stats"], base["days"]
    sc = base["statuses"]
    eq_real = equity_real(trades)
    n_cross_mid = sum(1 for t in trades if t.crossed_midnight)
    n_cross_wk = sum(1 for t in trades if t.crossed_weekend)
    n_whipsaw = sum(1 for d in days if d.whipsaw)
    holds = sorted(t.hold_minutes for t in trades)
    median_hold = holds[len(holds) // 2] / 60 if holds else 0.0

    lines = [
        "# Hasil Backtest London Breakout XAUUSD",
        "",
        f"Data: Dukascopy M1 bid, {df.index[0]:%Y-%m-%d} s/d {df.index[-1]:%Y-%m-%d} "
        f"({len(df):,} bar). Spread tetap ${BASELINE.spread:.2f}. "
        "Asumsi worst-case: SL menang di bar yang sama.",
        "",
        "## Baseline (konfigurasi bot saat ini)",
        "",
        f"- Trade: **{s['n']}** | Winrate: **{s['winrate']:.1f}%** | "
        f"Profit factor: **{s['profit_factor']:.2f}** | "
        f"Expectancy: **{s['expectancy_r']:+.3f}R** | Max DD (ideal 1%): **{base['max_dd']:.1f}%**",
        f"- Hari: traded {sc.get('traded', 0)}, no_breakout {sc.get('no_breakout', 0)}, "
        f"range sempit {sc.get('range_invalid_narrow', 0)}, range lebar {sc.get('range_invalid_wide', 0)}, "
        f"pre-broken {sc.get('pre_broken', 0)}, tanpa data {sc.get('no_data', 0)}",
        f"- Whipsaw (dua sisi tersentuh di menit yang sama): {n_whipsaw} hari",
        f"- Median hold: {median_hold:.1f} jam | Menginap: {n_cross_mid} trade | "
        f"Lewat weekend: {n_cross_wk} trade",
        "",
        "### Simulasi akun",
        "",
        f"1. **Ideal** (risk 1%, lot fraksional, mulai $10.000): "
        f"akhir **${base['eq_ideal'][-1]:,.2f}**, max DD {base['max_dd']:.1f}%",
        f"2. **Riil $100 + floor MIN_LOT 0.01** (replikasi bot): "
        f"akhir **${eq_real[-1]:,.2f}** setelah {len(eq_real) - 1} trade"
        + (" — **AKUN HABIS**" if eq_real[-1] <= 0 else "")
        + f", max DD {max_drawdown_pct(eq_real):.1f}%",
        "",
        "### R bulanan (baseline)",
        "",
        "| Bulan | R |", "|---|---|",
    ]
    lines += [f"| {m} | {r:+.2f} |" for m, r in monthly_r(trades).items()]
    lines += [
        "",
        "## Grid 36 varian (urut expectancy)",
        "",
        "| SL | TP_RR | RangeMax | TP1 | N | Winrate | PF | Exp (R) | MaxDD | |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    ranked = sorted(variants, key=lambda v: v["stats"]["expectancy_r"], reverse=True)
    lines += [fmt_row(v) for v in ranked]
    lines += ["", "★ = baseline (konfigurasi bot saat ini)", ""]
    return "\n".join(lines)


def plot_equity(base: dict, path_ideal: str, path_real: str) -> None:
    # NOTE executor: styling final mengikuti skill dataviz — baca dulu.
    for eq, path, title in [
        (base["eq_ideal"], path_ideal, "Equity — risk 1% ideal (mulai $10.000)"),
        (equity_real(base["trades"]), path_real, "Equity — akun riil $100, floor MIN_LOT 0.01"),
    ]:
        fig, ax = plt.subplots(figsize=(9, 4.5))
        ax.plot(range(len(eq)), eq)
        ax.set_title(title)
        ax.set_xlabel("Trade #")
        ax.set_ylabel("Balance (USD)")
        fig.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)


def audit_day(df, date_str: str) -> None:
    import pandas as pd
    day_df = df[df.index.date == pd.Timestamp(date_str).date()]
    results = simulate(day_df, BASELINE)
    for r in results:
        print(f"{r.date} status={r.status} range={r.range_size} whipsaw={r.whipsaw}")
        if r.trade:
            t = r.trade
            print(f"  {t.direction.upper()} entry={t.entry} @ {t.entry_time} "
                  f"SL={t.sl} TP1={t.tp1} TP2={t.tp2}")
            print(f"  exit={t.exit_reason} @ {t.exit_time} r={t.r_multiple:+.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", metavar="YYYY-MM-DD")
    args = ap.parse_args()

    print("Memuat data...")
    df = load_m1_csv(DATA)
    print(f"{len(df):,} bar, {df.index[0]} → {df.index[-1]}")

    if args.audit:
        audit_day(df, args.audit)
        return

    os.makedirs(RESULTS, exist_ok=True)
    variants = []
    combos = list(itertools.product(SL_MODES, TP_RRS, RANGE_MAXES, TP1_OPTIONS))
    for i, (sl, rr, rmax, tp1) in enumerate(combos, 1):
        p = Params(sl_mode=sl, tp_rr=rr, range_max=rmax, tp1_enabled=tp1)
        print(f"[{i}/{len(combos)}] {p.label()}")
        variants.append(run_variant(df, p))

    report = write_report(variants, df)
    report_path = os.path.join(RESULTS, "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    base = next(v for v in variants if v["params"] == BASELINE)
    plot_equity(base,
                os.path.join(RESULTS, "equity_ideal.png"),
                os.path.join(RESULTS, "equity_real_100usd.png"))
    print(f"Selesai → {report_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test dengan data sintetis kecil**

Jika download data belum selesai: jalankan `py -c` kecil yang memanggil `run_variant` dengan DataFrame dari `make_day` untuk memastikan tidak ada import error / crash. Jika data sudah ada, langsung Step 3 Task 9.

Run: `py -c "from backtest.run_backtest import run_variant; from backtest.params import BASELINE; from backtest.tests.conftest import make_day; v = run_variant(make_day('2025-03-04', [('15:00', 2001, 2006.0, 2000.8, 2005.5), ('16:00', 2006, 2022.0, 2005.9, 2021.5)]), BASELINE); print(v['stats'])"`
Expected: dict stats dengan `n == 1`, tanpa exception.

- [ ] **Step 3: Commit**

```bash
git add backtest/run_backtest.py
git commit -m "feat(backtest): runner - 36-variant grid, markdown report, equity charts"
```

---

### Task 9: Full run + audit manual + laporan akhir

**Files:**
- Create: `backtest/results/report.md`, `backtest/results/equity_ideal.png`, `backtest/results/equity_real_100usd.png` (hasil run)

- [ ] **Step 1: Pastikan download data selesai**

Run: `py -c "import os; p='backtest/data/xauusd_m1.csv'; print(os.path.getsize(p)/1e6, 'MB')"`
Expected: > 30 MB. Jika download gagal total, laporkan ke user — jangan lanjut dengan data parsial tanpa memberi tahu.

- [ ] **Step 2: Jalankan full backtest**

Run: `py backtest/run_backtest.py` (timeout longgar, 36 varian × ~780 hari)
Expected: progress 1/36 … 36/36, lalu `Selesai → backtest/results/report.md`

- [ ] **Step 3: Audit manual 3 hari sampel**

Pilih 3 tanggal dari report/log dengan status berbeda (1 traded-win, 1 traded-loss, 1 skip). Untuk tiap tanggal:

Run: `py backtest/run_backtest.py --audit YYYY-MM-DD`

lalu hitung tangan dari CSV mentah:

```powershell
py -c "import pandas as pd; from backtest.loader import load_m1_csv; df = load_m1_csv('backtest/data/xauusd_m1.csv'); d = df[df.index.date == pd.Timestamp('YYYY-MM-DD').date()]; asia = d.between_time('07:00','13:59'); print('high', asia.high.max(), 'low', asia.low.min())"
```

Verifikasi: `asian_high = high + 0.30`, `range`, `buy_stop/sell_stop`, arah trigger, dan harga exit cocok dengan output `--audit`. Jika ada selisih → **berhenti, diagnosis dengan skill systematic-debugging sebelum mempercayai hasil**.

- [ ] **Step 4: Commit hasil**

```bash
git add backtest/results/report.md backtest/results/equity_ideal.png backtest/results/equity_real_100usd.png
git commit -m "docs(backtest): 3-year London Breakout backtest results"
```

- [ ] **Step 5: Rangkum untuk user (Bahasa Indonesia)**

Sampaikan: verdict baseline (layak/tidak berdasarkan expectancy & PF), perbandingan varian kunci satu-dimensi vs baseline (SL mid vs opposite, TP_RR, RANGE_MAX, TP1 on/off), hasil simulasi akun $100 (bukti masalah MIN_LOT), statistik menginap/weekend (bukti perlunya time-exit), dan caveat (M1 worst-case, spread tetap, harga Dukascopy ≠ broker).
