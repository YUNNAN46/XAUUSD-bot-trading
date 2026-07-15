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
    # r_multiple disimpan round(...,4) di _finish(); 15.45/11.10 tidak
    # terminating di 4dp (1.391891891891896...) sehingga toleransi harus
    # mengakomodasi rounding tsb (maks error round(x,4) = 5e-5), bukan 1e-9.
    assert abs(t.r_multiple - (2021.25 - 2005.80) / 11.10) < 1e-4


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
