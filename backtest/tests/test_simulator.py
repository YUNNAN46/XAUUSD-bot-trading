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
