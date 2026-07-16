"""Simulator Mean Reversion sesi Asia — fade spike ekstrem saat gold ranging.

Model sinyal & eksekusi (sinyal di close bar, entry di open bar berikutnya —
sengaja menghindari ambiguitas trigger intra-bar):
- Bar sesi = waktu dalam [07:00, 14:00) WIB, dihitung per hari kalender.
- SMA & std rolling `window` bar HANYA dari close sesi hari itu — tanpa
  carryover hari sebelumnya (gap overnight meracuni statistik).
  std memakai ddof=0 (population std).
- Warmup: `window` bar sesi pertama tanpa sinyal. Sinyal hanya jika close
  bar sinyal < 13:00 WIB (bar ber-stempel HH:MM dianggap close di HH:MM+1,
  jadi stempel harus < 12:59) — tidak ada posisi baru di jam terakhir.
- Sinyal di CLOSE bar sesi t (window bar t-window+1..t, INKLUSIF bar t):
  close > SMA + k_entry×std → SELL (fade spike naik);
  close < SMA − k_entry×std → BUY (fade spike turun); std == 0 → tanpa sinyal.
- Entry di OPEN bar t+1: BUY = open+spread (ask), SELL = open (bid).
  Bar sinyal = bar sesi terakhir → tanpa trade.
- TP = SMA saat sinyal (statis). SL = entry ± k_sl×std (statis).
- Maksimal SATU trade per hari (sinyal pertama menang).
- Manajemen posisi worst-case sama dengan LB: SL dicek sebelum TP dalam
  satu bar; BUY exit di bid, SELL exit di ask (high/low + spread).
- Tutup PAKSA di bar pertama ≥ 14:00 WIB pada open bar itu
  (exit_reason 'session_end') — posisi MR tidak boleh terbawa ke London
  breakout. Data hari habis sebelum 14:00 → tutup di close bar terakhir
  ('end_of_data').

Konvensi harga sama dengan simulator LB: data = bid, ask = bid + spread.
Semua level harga round 2dp dengan float Python murni (array numpy
dikonversi via .to_numpy().tolist() sebelum aritmetika — jangan
memasukkan numpy scalar ke field Trade).
"""
from dataclasses import dataclass
from datetime import date as date_type, time
from math import sqrt

import pandas as pd

from backtest.mr_params import MRParams
from backtest.simulator import Trade

SESSION_START = time(7, 0)
SESSION_END = time(14, 0)       # eksklusif
LAST_SIGNAL_STAMP = time(12, 59)  # stempel bar < 12:59 ⇔ close bar < 13:00


@dataclass
class MRDayResult:
    date: date_type
    status: str               # 'traded' | 'no_signal' | 'no_data'
    trade: Trade | None = None


def simulate_mr(df: pd.DataFrame, params: MRParams) -> list[MRDayResult]:
    """df: OHLC bid, DatetimeIndex tz WIB, terurut. Satu MRDayResult per hari ber-data."""
    times = df.index
    opens = df["open"].to_numpy().tolist()
    highs = df["high"].to_numpy().tolist()
    lows = df["low"].to_numpy().tolist()
    closes = df["close"].to_numpy().tolist()
    tod = [t.time() for t in times]
    dates = times.date

    n = len(df)
    day_starts: dict = {}
    for k in range(n):
        day_starts.setdefault(dates[k], k)

    results: list[MRDayResult] = []
    for day, start in day_starts.items():
        end = start
        while end < n and dates[end] == day:
            end += 1
        results.append(_simulate_day(
            day, start, end, times, opens, highs, lows, closes, tod, params))
    return results


def _simulate_day(day, start, end, times, opens, highs, lows, closes, tod,
                  p: MRParams) -> MRDayResult:
    sess = [k for k in range(start, end) if SESSION_START <= tod[k] < SESSION_END]
    if not sess:
        return MRDayResult(day, "no_data")

    w = p.window
    # Rolling sum & sum-of-squares atas close sesi. Nilai digeser relatif
    # close sesi pertama agar stabil numerik (harga ~2000-3000, deviasi
    # intra-sesi kecil — tanpa shift, sum^2 kehilangan presisi).
    base = closes[sess[0]]
    xs: list[float] = []
    s = s2 = 0.0
    for i, k in enumerate(sess):
        x = closes[k] - base
        xs.append(x)
        s += x
        s2 += x * x
        if i >= w:
            old = xs[i - w]
            s -= old
            s2 -= old * old
        if i < w:
            continue          # warmup: `window` bar sesi pertama tanpa sinyal
        if tod[k] >= LAST_SIGNAL_STAMP:
            break             # close bar ≥ 13:00 — bar berikut lebih larut lagi
        mean_x = s / w
        var = s2 / w - mean_x * mean_x
        if var <= 0.0:
            continue          # std == 0 → tanpa sinyal
        std = sqrt(var)
        sma = mean_x + base
        c = closes[k]
        if c > sma + p.k_entry * std:
            direction = "sell"    # fade spike naik
        elif c < sma - p.k_entry * std:
            direction = "buy"     # fade spike turun
        else:
            continue
        if i + 1 >= len(sess):
            break             # bar sinyal = bar sesi terakhir → tanpa bar entry
        trade = _open_trade(direction, sess[i + 1], sma, std, times, opens, p)
        if trade is None:
            continue          # risk membulat ke 0 — perlakukan seperti tanpa sinyal
        _manage(trade, sess[i + 1], end, times, opens, highs, lows, closes, tod, p)
        return MRDayResult(day, "traded", trade)

    return MRDayResult(day, "no_signal")


def _open_trade(direction, k, sma, std, times, opens, p: MRParams) -> Trade | None:
    if direction == "buy":
        entry = round(opens[k] + p.spread, 2)   # ask
        sl = round(entry - p.k_sl * std, 2)
    else:
        entry = round(opens[k], 2)              # bid
        sl = round(entry + p.k_sl * std, 2)
    tp = round(sma, 2)
    risk = round(abs(entry - sl), 2)
    if risk <= 0.0:
        return None
    # Reuse dataclass Trade milik LB: TP tunggal MR disimpan di field tp2 (tp1=None)
    return Trade(direction, times[k], entry, sl, None, tp, risk)


def _manage(trade: Trade, entry_idx: int, day_end: int, times, opens, highs,
            lows, closes, tod, p: MRParams) -> None:
    """Jalankan posisi dari bar entry sampai exit (dalam hari itu). Mutasi in-place."""
    sp = p.spread
    buy = trade.direction == "buy"

    for k in range(entry_idx, day_end):
        if tod[k] >= SESSION_END:
            # Tutup paksa di open bar pertama ≥ 14:00 (bid utk BUY, ask utk SELL)
            price = opens[k] if buy else round(opens[k] + sp, 2)
            _finish(trade, times[k], price, "session_end", buy)
            return
        if buy:
            sl_hit = lows[k] <= trade.sl
            tp_hit = highs[k] >= trade.tp2
        else:
            sl_hit = highs[k] + sp >= trade.sl
            tp_hit = lows[k] + sp <= trade.tp2
        if sl_hit:            # worst-case: SL menang atas TP di bar yang sama
            _finish(trade, times[k], trade.sl, "sl", buy)
            return
        if tp_hit:
            _finish(trade, times[k], trade.tp2, "tp", buy)
            return

    # data hari ini habis sebelum 14:00 — tutup di close bar terakhir
    price = closes[day_end - 1] if buy else round(closes[day_end - 1] + sp, 2)
    _finish(trade, times[day_end - 1], price, "end_of_data", buy)


def _finish(trade: Trade, exit_time, exit_price: float, reason: str, buy: bool) -> None:
    sign = 1.0 if buy else -1.0
    trade.exit_time = exit_time
    trade.exit_reason = reason
    trade.r_multiple = round(sign * (exit_price - trade.entry) / trade.risk, 4)
