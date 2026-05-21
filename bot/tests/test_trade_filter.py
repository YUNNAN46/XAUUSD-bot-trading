import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
import pytz

WIB = pytz.timezone("Asia/Jakarta")

NO_BLACKOUT = patch('trade_filter.is_news_blackout', return_value=(False, ""))


def wib(hour, minute):
    return WIB.localize(datetime(2026, 5, 19, hour, minute))


# --- is_active_trading_hour ---
# Jam aktif: 15:00–19:00 WIB (London open) dan 20:00–23:59 WIB (NY session)

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
    assert is_active_trading_hour(wib(15, 0)) is True


def test_boundary_end_first_window():
    from trade_filter import is_active_trading_hour
    assert is_active_trading_hour(wib(19, 0)) is True


def test_boundary_start_second_window():
    from trade_filter import is_active_trading_hour
    assert is_active_trading_hour(wib(20, 0)) is True


def test_boundary_end_second_window():
    from trade_filter import is_active_trading_hour
    assert is_active_trading_hour(wib(23, 59)) is True


def test_between_windows():
    from trade_filter import is_active_trading_hour
    assert is_active_trading_hour(wib(19, 30)) is False


def test_before_first_window():
    from trade_filter import is_active_trading_hour
    assert is_active_trading_hour(wib(14, 0)) is False


def test_after_second_window():
    from trade_filter import is_active_trading_hour
    assert is_active_trading_hour(wib(0, 30)) is False


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


def test_trade_with_none_sl():
    from trade_filter import is_trade_valid
    pos = MagicMock(sl=None)
    valid, reason = is_trade_valid(pos)
    assert valid is False


def test_trade_with_negative_sl():
    from trade_filter import is_trade_valid
    pos = MagicMock(sl=-1990.0)
    valid, reason = is_trade_valid(pos)
    assert valid is False


# --- can_open_trade ---

def test_all_conditions_pass():
    from trade_filter import can_open_trade
    with NO_BLACKOUT:
        allowed, reason = can_open_trade(1, 1.0, 50, wib(16, 0))
    assert allowed is True
    assert reason == ""


def test_blocked_outside_hours():
    from trade_filter import can_open_trade
    allowed, reason = can_open_trade(0, 0.0, 50, wib(10, 0))
    assert allowed is False
    assert "jam trading" in reason


def test_blocked_news_blackout():
    from trade_filter import can_open_trade
    with patch('trade_filter.is_news_blackout', return_value=(True, "Non-Farm Payrolls")):
        allowed, reason = can_open_trade(0, 0.0, 50, wib(16, 0))
    assert allowed is False
    assert "Blackout" in reason
    assert "Non-Farm Payrolls" in reason


def test_blocked_max_trades():
    from trade_filter import can_open_trade
    with NO_BLACKOUT:
        allowed, reason = can_open_trade(2, 0.0, 50, wib(16, 0))
    assert allowed is False
    assert "trade terbuka" in reason


def test_blocked_high_spread():
    from trade_filter import can_open_trade
    with NO_BLACKOUT:
        allowed, reason = can_open_trade(0, 0.0, 100, wib(16, 0))
    assert allowed is False
    assert "Spread" in reason


def test_blocked_daily_loss():
    from trade_filter import can_open_trade
    with NO_BLACKOUT:
        allowed, reason = can_open_trade(0, 3.0, 50, wib(16, 0))
    assert allowed is False
    assert "Loss" in reason
