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


def make_position(ticket=1001, sl=1990.0, tp=2020.0, price_open=2000.0, pos_type=0, volume=0.01):
    p = MagicMock()
    p.ticket = ticket
    p.sl = sl
    p.tp = tp
    p.price_open = price_open
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


def test_paused_bot_does_not_generate_signal():
    """Bot yang di-pause tidak memanggil state_machine.tick."""
    from signal_watcher import SignalWatcher
    mt5 = make_mt5(balance=100.0, positions=[])
    watcher = SignalWatcher(mt5)
    watcher._known_tickets = set()
    watcher._paused = True
    watcher._day_start_balance = 100.0

    with patch("signal_watcher.is_active_trading_hour", return_value=True):
        with patch.object(watcher._state_machine, 'tick') as mock_tick:
            watcher.tick()
            mock_tick.assert_not_called()


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


def test_daily_loss_causes_early_return_from_tick():
    from signal_watcher import SignalWatcher
    pos = make_position(ticket=2001)
    mt5 = make_mt5(balance=96.5, positions=[pos])
    new_trades = []
    watcher = SignalWatcher(mt5, on_new_trade=new_trades.append)
    watcher._known_tickets = set()
    watcher._day_start_balance = 100.0
    watcher.tick()
    # Bot seharusnya pause dan tidak menerima trade baru
    assert watcher.is_paused is True
    assert len(new_trades) == 0


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
