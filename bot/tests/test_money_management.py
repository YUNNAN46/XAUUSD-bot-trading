import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


def test_lot_size_floored_to_min():
    from money_management import calculate_lot_size
    # balance=$100, risk=1% → risk_usd=$1, SL=150pts, tick_val=$1/lot
    # lot = 1/(150*1) = 0.0067 → floored to MIN_LOT=0.01
    lot = calculate_lot_size(balance=100.0, sl_points=150, tick_value_per_lot=1.0)
    assert lot == 0.01


def test_lot_size_normal_range():
    from money_management import calculate_lot_size
    # balance=$100, risk=1% → risk_usd=$1, SL=30pts, tick_val=$1/lot
    # lot = 1/(30*1) = 0.033 → rounded to 0.03
    lot = calculate_lot_size(balance=100.0, sl_points=30, tick_value_per_lot=1.0)
    assert lot == 0.03


def test_lot_size_capped_at_max():
    from money_management import calculate_lot_size
    lot = calculate_lot_size(balance=10000.0, sl_points=1, tick_value_per_lot=0.1)
    assert lot == 0.05


def test_lot_size_zero_sl_returns_min():
    from money_management import calculate_lot_size
    lot = calculate_lot_size(balance=100.0, sl_points=0, tick_value_per_lot=1.0)
    assert lot == 0.01


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


def test_daily_loss_not_reached():
    from money_management import is_daily_loss_limit_reached
    assert is_daily_loss_limit_reached(2.9) is False


def test_daily_loss_reached():
    from money_management import is_daily_loss_limit_reached
    assert is_daily_loss_limit_reached(3.0) is True


def test_drawdown_not_reached():
    from money_management import is_drawdown_limit_reached
    # 10% drawdown, limit 15% → tidak tercapai
    assert is_drawdown_limit_reached(current_balance=90.0, peak_balance=100.0) is False


def test_drawdown_reached():
    from money_management import is_drawdown_limit_reached
    # 16% drawdown, limit 15% → tercapai
    assert is_drawdown_limit_reached(current_balance=84.0, peak_balance=100.0) is True


def test_lot_size_zero_tick_value_returns_min():
    from money_management import calculate_lot_size
    lot = calculate_lot_size(balance=100.0, sl_points=150, tick_value_per_lot=0)
    assert lot == 0.01


def test_tp_entry_equals_sl_raises():
    from money_management import calculate_tp_price
    with pytest.raises(ValueError, match="tidak boleh sama"):
        calculate_tp_price(entry_price=2000.0, sl_price=2000.0, order_type=0)


def test_tp_invalid_order_type_raises():
    from money_management import calculate_tp_price
    with pytest.raises(ValueError, match="order_type"):
        calculate_tp_price(entry_price=2000.0, sl_price=1990.0, order_type=2)
