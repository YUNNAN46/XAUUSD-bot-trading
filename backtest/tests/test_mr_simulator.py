"""Test simulator Mean Reversion sesi Asia (backtest/mr_simulator.py).

Semua fixture memakai window=3 agar kompak. Catatan penting: dengan std
ddof=0, z-score maksimum yang mungkin dalam sampel n bar adalah sqrt(n-1)
(window=3 → 1.414), jadi test memakai k_entry=1.0 supaya sinyal reachable.

Angka acuan skenario SELL (dipakai beberapa test):
  closes window (t=idx3, bar idx1..3) = [2000, 2000, 2003]
  SMA = 2001.0 ; deviasi = [-1, -1, +2] → var = 6/3 = 2 → std = √2 ≈ 1.414214
  ambang SELL = 2001 + 1.0×1.414214 = 2002.414 < close 2003 → sinyal SELL
  TP = round(SMA, 2) = 2001.00
  entry = open bar idx4 (bid) = 2002.80
  SL = round(2002.80 + 1.0×1.414214, 2) = 2004.21 ; risk = 1.41
"""
from backtest.mr_params import MRParams
from backtest.mr_simulator import simulate_mr
from backtest.tests.conftest import make_bars

P = MRParams(window=3, k_entry=1.0, k_sl=1.0)  # spread default 0.30

# Tiga bar warmup identik (close 2000) — window=3 → sinyal pertama di idx3
WARMUP = [
    ("07:00", 2000.0, 2000.5, 1999.5, 2000.0),
    ("07:01", 2000.0, 2000.5, 1999.5, 2000.0),
    ("07:02", 2000.0, 2000.5, 1999.5, 2000.0),
]


def run_one(df, params=P):
    results = simulate_mr(df, params)
    assert len(results) == 1
    return results[0]


def test_warmup_no_signal():
    # Hanya 3 bar sesi (< window+1 = 4): bar spike di idx2 tidak boleh
    # menghasilkan sinyal — warmup belum selesai.
    bars = WARMUP[:2] + [("07:02", 2000.0, 2003.5, 1999.8, 2003.0)]
    day = run_one(make_bars("2025-03-04", bars))
    assert day.status == "no_signal"
    assert day.trade is None


def test_no_session_bars_is_no_data():
    # Hari tanpa bar dalam [07:00, 14:00) → no_data
    day = run_one(make_bars("2025-03-04", [("15:00", 2000, 2001, 1999, 2000)]))
    assert day.status == "no_data"


def test_sell_signal_entry_tp_exit():
    # Lihat angka acuan di docstring modul. Bar idx4:
    #   SL? high+sp = 2003.3 < 2004.21 → tidak
    #   TP? low+sp  = 2000.8 ≤ 2001.00 → ya → exit di TP
    # r = (2002.80 − 2001.00) / 1.41 = 1.8/1.41 → round 4dp
    day = run_one(make_bars("2025-03-04", WARMUP + [
        ("07:03", 2000.0, 2003.5, 1999.8, 2003.0),   # bar sinyal t
        ("07:04", 2002.8, 2003.0, 2000.5, 2001.0),   # bar entry t+1
    ]))
    assert day.status == "traded"
    t = day.trade
    assert t.direction == "sell"
    assert t.entry == 2002.80          # open bar t+1 (bid)
    assert t.tp2 == 2001.00            # SMA saat sinyal, statis
    assert t.sl == 2004.21             # entry + 1.0×√2, statis
    assert t.tp1 is None and t.whipsaw is False
    assert t.risk == 1.41
    assert t.exit_reason == "tp"
    assert t.r_multiple == round(1.8 / 1.41, 4)      # 1.2766


def test_buy_signal_entry_tp_exit():
    # Cermin BUY: window [2000, 2000, 1997] → SMA=1999.0, std=√2
    # ambang BUY = 1999 − 1.414 = 1997.586 > close 1997 → sinyal BUY
    # entry = open idx4 + spread = 1997.2 + 0.30 = 1997.50 (ask)
    # TP = 1999.00 ; SL = round(1997.50 − 1.414214, 2) = 1996.09 ; risk = 1.41
    # Bar idx4: SL? low 1997.0 > 1996.09 tidak ; TP? high 1999.1 ≥ 1999.0 ya
    # r = (1999.00 − 1997.50) / 1.41 = 1.5/1.41 → 1.0638
    day = run_one(make_bars("2025-03-04", WARMUP + [
        ("07:03", 2000.0, 2000.2, 1996.5, 1997.0),
        ("07:04", 1997.2, 1999.1, 1997.0, 1998.5),
    ]))
    assert day.status == "traded"
    t = day.trade
    assert t.direction == "buy"
    assert t.entry == 1997.50
    assert t.tp2 == 1999.00
    assert t.sl == 1996.09
    assert t.risk == 1.41
    assert t.exit_reason == "tp"
    assert t.r_multiple == round(1.5 / 1.41, 4)      # 1.0638


def test_sl_wins_over_tp_same_bar_sell():
    # Bar entry menyentuh SL dan TP sekaligus → worst-case: SL menang.
    #   SL? high+sp = 2004.8 ≥ 2004.21 → ya
    #   TP? low+sp  = 2000.3 ≤ 2001.00 → ya (tapi SL dicek duluan)
    # r = (2002.80 − 2004.21) / 1.41 = −1.0
    day = run_one(make_bars("2025-03-04", WARMUP + [
        ("07:03", 2000.0, 2003.5, 1999.8, 2003.0),
        ("07:04", 2002.8, 2004.5, 2000.0, 2001.0),
    ]))
    t = day.trade
    assert t.exit_reason == "sl"
    assert t.r_multiple == -1.0


def test_session_end_force_close():
    # Posisi SELL tidak kena SL/TP sampai 14:00 → tutup paksa di OPEN bar
    # pertama ≥ 14:00, harga ask = open + spread.
    # r = (2002.80 − 2002.30) / 1.41 = 0.5/1.41 → 0.3546
    day = run_one(make_bars("2025-03-04", WARMUP + [
        ("07:03", 2000.0, 2003.5, 1999.8, 2003.0),
        ("07:04", 2002.8, 2003.0, 2002.5, 2002.9),   # entry, tanpa exit
        ("13:59", 2002.5, 2002.9, 2002.2, 2002.5),   # masih sesi, tanpa exit
        ("14:00", 2002.0, 2002.5, 2001.5, 2002.0),   # bar pertama ≥ 14:00
    ]))
    t = day.trade
    assert t.exit_reason == "session_end"
    assert t.exit_time.strftime("%H:%M") == "14:00"
    assert t.r_multiple == round(0.5 / 1.41, 4)      # exit ask 2002.30


def test_one_trade_per_day():
    # Trade pertama exit TP di 07:04; spike kedua di 07:07 memenuhi syarat
    # sinyal lagi, tapi TIDAK boleh membuka trade kedua.
    day = run_one(make_bars("2025-03-04", WARMUP + [
        ("07:03", 2000.0, 2003.5, 1999.8, 2003.0),
        ("07:04", 2002.8, 2003.0, 2000.5, 2001.0),   # trade 1 exit TP di sini
        ("07:05", 2001.0, 2001.5, 2000.5, 2001.0),
        ("07:06", 2001.0, 2001.5, 2000.5, 2001.0),
        ("07:07", 2001.0, 2004.5, 2000.8, 2004.0),   # calon sinyal kedua
        ("07:08", 2003.8, 2004.0, 2001.5, 2002.0),   # calon bar entry kedua
    ]))
    assert day.status == "traded"
    t = day.trade
    # Trade yang tercatat adalah yang PERTAMA (entry 07:04), bukan 07:08
    assert t.entry_time.strftime("%H:%M") == "07:04"
    assert t.entry == 2002.80
    assert t.exit_reason == "tp"


def test_no_entry_after_1300():
    # Bar sinyal ber-stempel 12:59 close-nya tepat 13:00 → TIDAK < 13:00 →
    # tidak ada trade meski pola sinyal valid dan bar entry tersedia.
    bars_late = [
        ("12:56", 2000.0, 2000.5, 1999.5, 2000.0),
        ("12:57", 2000.0, 2000.5, 1999.5, 2000.0),
        ("12:58", 2000.0, 2000.5, 1999.5, 2000.0),
        ("12:59", 2000.0, 2003.5, 1999.8, 2003.0),   # close 13:00 → blokir
        ("13:00", 2002.8, 2003.0, 2000.5, 2001.0),
    ]
    day = run_one(make_bars("2025-03-04", bars_late))
    assert day.status == "no_signal"
    assert day.trade is None

    # Batas sebaliknya: bar sinyal 12:58 close 12:59 < 13:00 → trade jalan.
    bars_ok = [
        ("12:55", 2000.0, 2000.5, 1999.5, 2000.0),
        ("12:56", 2000.0, 2000.5, 1999.5, 2000.0),
        ("12:57", 2000.0, 2000.5, 1999.5, 2000.0),
        ("12:58", 2000.0, 2003.5, 1999.8, 2003.0),
        ("12:59", 2002.8, 2003.0, 2000.5, 2001.0),
    ]
    day = run_one(make_bars("2025-03-05", bars_ok))
    assert day.status == "traded"
    assert day.trade.entry_time.strftime("%H:%M") == "12:59"


def test_no_lookahead_stats_use_bar_t_only():
    # Sinyal di t harus memakai SMA/std s/d bar t SAJA. Bar t+1 anjlok jauh:
    # jika stats (salah) menyertakan bar t+1, window jadi [2000, 2003, 1990]
    # → SMA = 1997.667, std = √(92.667/3) = 5.558 → ambang 2003.22 > 2003
    # → TIDAK ada sinyal. Implementasi benar (s/d t): window [2000,2000,2003]
    # → SMA 2001, std √2 → ambang 2002.41 < 2003 → SELL dengan TP 2001.00.
    # (Close bar t sendiri IKUT dalam window — by design, bukan lookahead,
    # karena sinyal dievaluasi saat close bar t.)
    day = run_one(make_bars("2025-03-04", WARMUP + [
        ("07:03", 2000.0, 2003.5, 1999.8, 2003.0),   # bar sinyal t
        ("07:04", 2002.8, 2003.0, 1989.5, 1990.0),   # bar t+1 anjlok
    ]))
    assert day.status == "traded"
    t = day.trade
    assert t.direction == "sell"
    assert t.tp2 == 2001.00      # SMA versi t-only — beda jika ada lookahead
    assert t.sl == 2004.21       # std versi t-only
    # Bar entry: SL? high+sp 2003.3 < 2004.21 tidak; TP? low+sp 1989.8 ≤ 2001 ya
    assert t.exit_reason == "tp"
    assert t.r_multiple == round(1.8 / 1.41, 4)
