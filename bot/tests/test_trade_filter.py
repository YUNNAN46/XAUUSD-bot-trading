import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime
from unittest.mock import MagicMock
import pytz

WIB = pytz.timezone("Asia/Jakarta")


def wib(hour, minute):
    return WIB.localize(datetime(2026, 5, 19, hour, minute))


# --- is_active_trading_hour ---

def test_within_first_window():
    from trade_filter import is_active_trading_hour
    assert is_active_trading_hour(wib(15, 30)) is True


def test_within_second_window():
    from trade_filter import is_active_trading_hour
    assert is_active_trading_hour(wib(21, 0)) is True


def test_outside_windows():
    from trade_filter import is_active_trading_hour
    assert is_active_trading_hour(wib(10, 0)) is False


def test_boundary_start_first_window():
    from trade_filter import is_active_trading_hour
    assert is_active_trading_hour(wib(14, 0)) is True


def test_boundary_end_second_window():
    from trade_filter import is_active_trading_hour
    assert is_active_trading_hour(wib(23, 0)) is True


def test_between_windows():
    from trade_filter import is_active_trading_hour
    assert is_active_trading_hour(wib(18, 0)) is False


# --- is_spread_acceptable ---

def test_spread_ok():
    from trade_filter import is_spread_acceptable
    assert is_spread_acceptable(79) is True


def test_spread_at_limit():
    from trade_filter import is_spread_acceptable
    assert is_spread_acceptable(80) is True


def test_spread_too_wide():
    from trade_filter import is_spread_acceptable
    assert is_spread_acceptable(81) is False


# --- is_trade_valid ---

def test_trade_with_sl():
    from trade_filter import is_trade_valid
    pos = MagicMock(sl=1990.0)
    valid, reason = is_trade_valid(pos)
    assert valid is True


def test_trade_without_sl():
    from trade_filter import is_trade_valid
    pos = MagicMock(sl=0)
    valid, reason = is_trade_valid(pos)
    assert valid is False
    assert "SL" in reason


# --- can_open_trade ---

def test_all_conditions_pass():
    from trade_filter import can_open_trade
    allowed, reason = can_open_trade(
        open_positions_count=1, daily_loss_pct=1.0, spread_points=50, now=wib(15, 0)
    )
    assert allowed is True
    assert reason == ""


def test_blocked_outside_hours():
    from trade_filter import can_open_trade
    allowed, reason = can_open_trade(0, 0.0, 50, wib(10, 0))
    assert allowed is False
    assert "jam trading" in reason


def test_blocked_max_trades():
    from trade_filter import can_open_trade
    allowed, reason = can_open_trade(2, 0.0, 50, wib(15, 0))
    assert allowed is False
    assert "trade terbuka" in reason


def test_blocked_high_spread():
    from trade_filter import can_open_trade
    allowed, reason = can_open_trade(0, 0.0, 100, wib(15, 0))
    assert allowed is False
    assert "Spread" in reason


def test_blocked_daily_loss():
    from trade_filter import can_open_trade
    allowed, reason = can_open_trade(0, 3.0, 50, wib(15, 0))
    assert allowed is False
    assert "Loss" in reason
