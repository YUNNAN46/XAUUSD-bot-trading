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
