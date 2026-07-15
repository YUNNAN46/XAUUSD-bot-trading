"""Simulator London Breakout — mereplikasi aturan bot/signal_watcher.py + signal_generator.py.

Konvensi harga: data = bid. ask = bid + params.spread.
BUY : trigger & entry di ask (level buy_stop adalah harga ask), exit dicek di bid.
SELL: trigger & entry di bid, exit dicek di ask.
Worst-case intra-bar: SL diperiksa lebih dulu; setelah TP1 tereksekusi dalam
sebuah bar, tidak ada event lain yang diproses di bar yang sama.
"""
from dataclasses import dataclass
from datetime import date, datetime, time

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
    date: date
    status: str               # 'traded'|'no_breakout'|'range_invalid_narrow'|
                              # 'range_invalid_wide'|'pre_broken'|'no_data'
    range_size: float | None = None
    whipsaw: bool = False
    trade: Trade | None = None


def simulate(df: pd.DataFrame, params: Params) -> list[DayResult]:
    """df: OHLC bid, DatetimeIndex tz WIB, terurut. Return satu DayResult per hari kalender ber-data."""
    times = df.index
    opens = df["open"].to_numpy().tolist()
    highs = df["high"].to_numpy().tolist()
    lows = df["low"].to_numpy().tolist()
    closes = df["close"].to_numpy().tolist()
    tod = [t.time() for t in times]           # time-of-day per bar
    dates = times.date

    results: list[DayResult] = []
    n = len(df)
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
