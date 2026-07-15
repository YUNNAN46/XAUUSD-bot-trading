import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
import pytz

WIB = pytz.timezone("Asia/Jakarta")


def make_mt5(balance=100.0, equity=100.0, positions=None, spread=50):
    mt5 = MagicMock()
    mt5.is_connected = True
    mt5.get_balance.return_value = balance
    mt5.get_equity.return_value = equity
    mt5.get_positions.return_value = positions or []
    mt5.get_spread.return_value = spread
    mt5.close_position.return_value = True
    mt5.modify_position_tp.return_value = True
    return mt5


def make_position(ticket=1001, sl=1990.0, tp=2020.0, price_open=2000.0, pos_type=0, volume=0.01, price_current=None):
    p = MagicMock()
    p.ticket = ticket
    p.sl = sl
    p.tp = tp
    p.price_open = price_open
    p.price_current = price_current if price_current is not None else price_open
    p.type = pos_type
    p.volume = volume
    p.symbol = "XAUUSD"
    return p


def test_initialize_sets_known_tickets():
    from signal_watcher import SignalWatcher
    pos = make_position(ticket=1001)
    mt5 = make_mt5(balance=100.0, positions=[pos])
    watcher = SignalWatcher(mt5)
    watcher.initialize()
    assert 1001 in watcher._known_tickets


def test_drawdown_not_reached():
    from signal_watcher import SignalWatcher
    mt5 = make_mt5(balance=90.0)
    alerts = []
    watcher = SignalWatcher(mt5, on_alert=alerts.append)
    watcher._peak_balance = 100.0
    assert watcher.check_drawdown() is False
    assert len(alerts) == 0


def test_drawdown_reached_triggers_alert():
    from signal_watcher import SignalWatcher
    mt5 = make_mt5(balance=84.0)
    alerts = []
    watcher = SignalWatcher(mt5, on_alert=alerts.append)
    watcher._peak_balance = 100.0
    assert watcher.check_drawdown() is True
    assert len(alerts) == 1


def test_daily_loss_triggers_pause():
    from signal_watcher import SignalWatcher
    mt5 = make_mt5(balance=96.5)
    watcher = SignalWatcher(mt5)
    watcher._day_start_balance = 100.0
    watcher.check_daily_loss()
    assert watcher.is_paused is True


def test_new_position_tracked_after_tick():
    """Posisi yang baru muncul ditambahkan ke _known_tickets setelah tick."""
    from signal_watcher import SignalWatcher
    pos = make_position(ticket=1002)
    mt5 = make_mt5(balance=100.0, positions=[pos], spread=50)
    watcher = SignalWatcher(mt5)
    watcher._known_tickets = set()
    watcher._day_start_balance = 100.0

    with patch("signal_watcher.can_open_trade", return_value=(False, "Di luar jam trading aktif")):
        with patch("signal_watcher.is_active_trading_hour", return_value=False):
            watcher.tick()

    assert 1002 in watcher._known_tickets


def test_filter_fails_does_not_open_trade():
    """Jika can_open_trade gagal, tidak ada posisi baru yang dibuka."""
    from signal_watcher import SignalWatcher
    mt5 = make_mt5(balance=100.0, positions=[], spread=50)
    new_trades = []
    watcher = SignalWatcher(mt5, on_new_trade=new_trades.append)
    watcher._known_tickets = set()
    watcher._day_start_balance = 100.0

    with patch("signal_watcher.can_open_trade", return_value=(False, "Di luar jam trading aktif")):
        with patch("signal_watcher.is_active_trading_hour", return_value=False):
            watcher.tick()

    mt5.open_position.assert_not_called()
    assert len(new_trades) == 0



def test_pause_and_resume():
    from signal_watcher import SignalWatcher
    mt5 = make_mt5()
    watcher = SignalWatcher(mt5)
    assert watcher.is_paused is False
    watcher.pause()
    assert watcher.is_paused is True
    watcher.resume()
    assert watcher.is_paused is False


def test_peak_balance_updates_on_profit():
    from signal_watcher import SignalWatcher
    mt5 = make_mt5(balance=110.0)
    watcher = SignalWatcher(mt5)
    watcher._peak_balance = 100.0
    watcher.check_drawdown()
    assert watcher._peak_balance == 110.0


def test_drawdown_also_pauses_bot():
    from signal_watcher import SignalWatcher
    mt5 = make_mt5(balance=84.0)
    watcher = SignalWatcher(mt5)
    watcher._peak_balance = 100.0
    watcher.check_drawdown()
    assert watcher.is_paused is True


def test_daily_loss_causes_pause():
    from signal_watcher import SignalWatcher
    pos = make_position(ticket=2001)
    mt5 = make_mt5(balance=96.5, positions=[pos])
    watcher = SignalWatcher(mt5)
    watcher._known_tickets = {2001}  # position already known, no new-trade tracking
    watcher._day_start_balance = 100.0
    watcher.tick()
    assert watcher.is_paused is True


def test_closed_position_triggers_on_trade_closed():
    from signal_watcher import SignalWatcher
    closed_calls = []
    mt5 = make_mt5(balance=102.0, positions=[])  # posisi sudah tidak ada
    watcher = SignalWatcher(mt5, on_trade_closed=lambda ticket, profit: closed_calls.append(ticket))
    watcher._known_tickets = {1005}  # posisi 1005 sebelumnya ada
    watcher._day_start_balance = 100.0
    with patch("signal_watcher.can_open_trade", return_value=(True, "")):
        watcher.tick()
    assert 1005 in closed_calls


def test_closed_position_passes_correct_profit():
    from signal_watcher import SignalWatcher
    closed_calls = []
    mt5 = make_mt5(balance=102.5, positions=[])  # posisi sudah tutup
    watcher = SignalWatcher(mt5, on_trade_closed=lambda ticket, profit: closed_calls.append((ticket, profit)))
    watcher._known_tickets = {9001}
    watcher._last_known_profits = {9001: 2.5}
    watcher._day_start_balance = 100.0
    with patch("signal_watcher.can_open_trade", return_value=(True, "")):
        watcher.tick()
    assert len(closed_calls) == 1
    assert closed_calls[0] == (9001, 2.5)


def test_reset_day_updates_balance_and_peak():
    from signal_watcher import SignalWatcher
    mt5 = make_mt5()
    watcher = SignalWatcher(mt5)
    watcher._peak_balance = 100.0
    watcher.reset_day(110.0)
    assert watcher._day_start_balance == 110.0
    assert watcher._peak_balance == 110.0  # updated karena lebih tinggi


# ---------------------------------------------------------------------------
# London Breakout tests
# ---------------------------------------------------------------------------
from datetime import datetime, time as time_type
import pytz as _pytz

_WIB = _pytz.timezone("Asia/Jakarta")


def make_watcher_lb(balance=100.0, positions=None, spread=50):
    from signal_watcher import SignalWatcher
    mt5 = make_mt5(balance=balance, positions=positions or [], spread=spread)
    mt5.get_tick.return_value = MagicMock(bid=2315.0, ask=2315.5)
    mt5.is_algo_trading_enabled.return_value = True
    mt5.get_symbol_info.return_value = MagicMock(point=0.01, trade_tick_value=1.0)
    mt5.place_stop_order.return_value = None
    mt5.cancel_order.return_value = True
    mt5.get_pending_orders.return_value = []
    alerts = []
    watcher = SignalWatcher(mt5, on_alert=alerts.append)
    watcher._peak_balance = balance
    watcher._day_start_balance = balance
    return watcher, mt5, alerts


def _wib(hour, minute):
    return datetime.now(_WIB).replace(hour=hour, minute=minute, second=0, microsecond=0)


def test_collecting_updates_asian_range_from_tick():
    watcher, mt5, _ = make_watcher_lb()
    mt5.get_tick.return_value = MagicMock(bid=2310.0, ask=2311.0)
    watcher._london_state = 'COLLECTING'
    watcher._update_london_breakout(_wib(10, 0))
    assert watcher._strategy.asian_high == 2311.0
    assert watcher._strategy.asian_low  == 2310.0


def test_collecting_does_not_run_outside_asian_window():
    watcher, mt5, _ = make_watcher_lb()
    mt5.get_tick.return_value = MagicMock(bid=2310.0, ask=2311.0)
    watcher._london_state = 'IDLE'
    watcher._update_london_breakout(_wib(15, 30))  # outside 07:00-14:00 WIB
    assert watcher._strategy.asian_high is None


def test_places_orders_at_14_50_when_collecting():
    # balance cukup besar agar lot >= MIN_LOT (SL dist $10.8 → 1080 pts)
    watcher, mt5, alerts = make_watcher_lb(balance=20000.0)
    watcher._strategy.update_asian_range(2320.0, 2310.0)  # valid $10 range
    watcher._london_state = 'COLLECTING'
    mt5.place_stop_order.return_value = 1001
    watcher._update_london_breakout(_wib(14, 50))
    assert mt5.place_stop_order.call_count == 2
    assert watcher._london_state == 'ORDERS_SET'
    assert any("dipasang" in a for a in alerts)


def test_skips_orders_when_lot_below_min():
    # balance $100, SL dist $10.8 → lot ideal 0.0009 < MIN_LOT → jangan trade
    watcher, mt5, alerts = make_watcher_lb(balance=100.0)
    watcher._strategy.update_asian_range(2320.0, 2310.0)  # valid $10 range
    watcher._london_state = 'COLLECTING'
    mt5.place_stop_order.return_value = 1001
    watcher._update_london_breakout(_wib(14, 50))
    mt5.place_stop_order.assert_not_called()
    assert watcher._london_state == 'EXPIRED'
    assert any("MIN_LOT" in a or "terlalu kecil" in a for a in alerts)


def test_skips_order_placement_if_range_invalid():
    watcher, mt5, alerts = make_watcher_lb()
    watcher._strategy.update_asian_range(2310.5, 2310.0)  # $0.5 — too small
    watcher._london_state = 'COLLECTING'
    watcher._update_london_breakout(_wib(14, 50))
    mt5.place_stop_order.assert_not_called()
    assert any("Skip" in a or "tidak valid" in a for a in alerts)


def test_cancels_pending_orders_at_expiry():
    watcher, mt5, alerts = make_watcher_lb()
    watcher._london_state = 'ORDERS_SET'
    watcher._pending_buy_ticket  = 1001
    watcher._pending_sell_ticket = 1002
    mt5.cancel_order.return_value = True
    watcher._update_london_breakout(_wib(17, 0))
    assert mt5.cancel_order.call_count == 2
    assert watcher._london_state == 'EXPIRED'
    assert any("dihapus" in a or "Expired" in a for a in alerts)


def test_oco_cancels_sell_when_buy_triggers():
    watcher, mt5, _ = make_watcher_lb()
    watcher._london_state        = 'ORDERS_SET'
    watcher._pending_buy_ticket  = 1001
    watcher._pending_sell_ticket = 1002
    # 1001 gone from pending → buy triggered
    mt5.get_pending_orders.return_value = [MagicMock(ticket=1002)]
    watcher._update_london_breakout(_wib(15, 30))
    mt5.cancel_order.assert_called_once_with(1002)


def test_oco_cancels_buy_when_sell_triggers():
    watcher, mt5, _ = make_watcher_lb()
    watcher._london_state        = 'ORDERS_SET'
    watcher._pending_buy_ticket  = 1001
    watcher._pending_sell_ticket = 1002
    # 1002 gone from pending → sell triggered
    mt5.get_pending_orders.return_value = [MagicMock(ticket=1001)]
    watcher._update_london_breakout(_wib(15, 30))
    mt5.cancel_order.assert_called_once_with(1001)


def test_reset_day_clears_strategy_and_london_state():
    watcher, _, _ = make_watcher_lb()
    watcher._strategy.update_asian_range(2320.0, 2310.0)
    watcher._london_state = 'ORDERS_SET'
    watcher.reset_day(100.0)
    assert watcher._strategy.asian_high is None
    assert watcher._london_state == 'IDLE'
