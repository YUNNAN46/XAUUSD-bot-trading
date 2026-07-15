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
    # terminating di 4dp (1.3918918918918919...) sehingga dibandingkan
    # terhadap literal round(x,4) yang sama persis, bukan toleransi longgar.
    assert t.r_multiple == round(15.45 / 11.10, 4)


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


def test_sl_wins_over_tp_same_bar():
    # bar entry juga menyentuh SL dan TP2 → SL duluan → r = −1
    day = run_one(make_day("2025-03-04", [
        ("15:00", 2001, 2022.0, 1994.0, 2000.0),  # ask high 2022.30, low 1994 <= sl 1994.70
    ]), Params(tp1_enabled=False))
    t = day.trade
    assert t.exit_reason == "sl"
    assert abs(t.r_multiple - (-1.0)) < 1e-9


def test_tp1_partial_then_breakeven():
    # TP1 2013.53 disentuh (SL tidak), lalu bar berikut turun ke BE (entry 2005.80)
    day = run_one(make_day("2025-03-04", [
        ("15:00", 2001, 2006.0, 2000.8, 2005.5),   # BUY @2005.80
        ("15:30", 2006, 2014.0, 2005.0, 2013.0),   # TP1 hit → 50% @2013.53, SL→BE
        ("16:00", 2013, 2014.0, 2005.5, 2006.0),   # low 2005.5 <= BE 2005.80 → exit sisa
    ]))
    t = day.trade
    assert t.tp1_hit is True
    assert t.exit_reason == "be"
    # sisa 50% keluar di BE = 0R; r_multiple disimpan round(...,4) di _finish(),
    # jadi expected dibulatkan juga (7.73/11.10 tidak terminating di 4dp) —
    # sama seperti pola di test_buy_triggered_with_spread di atas.
    expected = round(0.5 * (2013.53 - 2005.80) / 11.10, 4)
    assert abs(t.r_multiple - expected) < 1e-6


def test_tp1_then_tp2_full_profit():
    day = run_one(make_day("2025-03-04", [
        ("15:00", 2001, 2006.0, 2000.8, 2005.5),
        ("15:30", 2006, 2014.0, 2005.9, 2013.0),   # TP1
        ("16:00", 2013, 2022.0, 2012.0, 2021.5),   # TP2 2021.25
    ]))
    t = day.trade
    assert t.exit_reason == "tp2"
    expected = round(
        0.5 * (2013.53 - 2005.80) / 11.10 + 0.5 * (2021.25 - 2005.80) / 11.10, 4
    )
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
    expected = round((2010.0 - 2005.80) / 11.10, 4)
    assert abs(t.r_multiple - expected) < 1e-9


def test_sl_wins_over_tp_same_bar_sell():
    # bar entry juga menyentuh SL (ask 2005.65 >= sl_sell 2005.60) dan TP2
    # (ask_low 1978.30 <= tp_sell 1979.05) → SL duluan → r = −1
    day = run_one(make_day("2025-03-04", [
        ("15:00", 2000, 2005.35, 1978.0, 2000.0),
    ]), Params(tp1_enabled=False))
    t = day.trade
    assert t.exit_reason == "sl"
    assert abs(t.r_multiple - (-1.0)) < 1e-9


def test_tp1_partial_then_breakeven_sell():
    # TP1 1986.78 disentuh (SL tidak), lalu bar berikut naik ke BE (entry 1994.50)
    day = run_one(make_day("2025-03-04", [
        ("15:00", 2000, 2001.0, 1994.4, 1995.0),   # SELL @1994.50
        ("15:30", 1995, 1996.0, 1986.0, 1987.0),   # TP1 hit → 50% @1986.78, SL→BE
        ("16:00", 1987, 1995.0, 1986.5, 1994.0),   # ask_high 1995.30 >= BE 1994.50 → exit sisa
    ]))
    t = day.trade
    assert t.tp1_hit is True
    assert t.exit_reason == "be"
    # sisa 50% keluar di BE = 0R; r_multiple disimpan round(...,4) di _finish(),
    # jadi expected dibulatkan juga — sama seperti pola BUY di atas.
    expected = round(0.5 * (1994.50 - 1986.78) / 11.10, 4)
    assert abs(t.r_multiple - expected) < 1e-6


def test_end_of_data_closes_at_last_close_sell():
    day = run_one(make_day("2025-03-04", [
        ("15:00", 2000, 2001.0, 1994.4, 1995.0),
        ("16:59", 1995, 1996.0, 1990.0, 1992.0),
    ]), Params(tp1_enabled=False))
    t = day.trade
    assert t.exit_reason == "end_of_data"
    # SELL tutup dengan membeli di ask: last_close + spread
    expected = round((1994.50 - (1992.0 + 0.30)) / 11.10, 4)
    assert abs(t.r_multiple - expected) < 1e-9
