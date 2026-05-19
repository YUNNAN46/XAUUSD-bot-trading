import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_mt5_lib():
    mock = MagicMock()
    mock.initialize.return_value = True
    mock.account_info.return_value = MagicMock(balance=150.0, equity=148.0)
    mock.symbol_info.return_value = MagicMock(spread=45)
    mock.symbol_info_tick.return_value = MagicMock(bid=2000.0, ask=2000.5)
    mock.positions_get.return_value = [
        MagicMock(ticket=1001, symbol="XAUUSD", volume=0.01, type=0,
                  sl=1990.0, tp=2020.0, price_open=2000.0)
    ]
    mock.TRADE_RETCODE_DONE = 10009
    mock.TRADE_ACTION_DEAL = 1
    mock.TRADE_ACTION_SLTP = 6
    mock.ORDER_TYPE_SELL = 1
    mock.ORDER_TYPE_BUY = 0
    mock.ORDER_TIME_GTC = 1
    mock.ORDER_FILLING_IOC = 1
    return mock


def test_connect_success(mock_mt5_lib):
    with patch("mt5_connector.MetaTrader5", return_value=mock_mt5_lib):
        from mt5_connector import MT5Connector
        conn = MT5Connector(host="localhost", port=8001)
        assert conn.connect() is True
        assert conn.is_connected is True


def test_connect_failure(mock_mt5_lib):
    mock_mt5_lib.initialize.return_value = False
    mock_mt5_lib.last_error.return_value = (1, "Connection refused")
    with patch("mt5_connector.MetaTrader5", return_value=mock_mt5_lib):
        from mt5_connector import MT5Connector
        conn = MT5Connector(host="localhost", port=8001)
        assert conn.connect() is False
        assert conn.is_connected is False


def test_get_balance(mock_mt5_lib):
    with patch("mt5_connector.MetaTrader5", return_value=mock_mt5_lib):
        from mt5_connector import MT5Connector
        conn = MT5Connector()
        conn.connect()
        assert conn.get_balance() == 150.0


def test_get_spread(mock_mt5_lib):
    with patch("mt5_connector.MetaTrader5", return_value=mock_mt5_lib):
        from mt5_connector import MT5Connector
        conn = MT5Connector()
        conn.connect()
        assert conn.get_spread("XAUUSD") == 45


def test_get_positions(mock_mt5_lib):
    with patch("mt5_connector.MetaTrader5", return_value=mock_mt5_lib):
        from mt5_connector import MT5Connector
        conn = MT5Connector()
        conn.connect()
        positions = conn.get_positions("XAUUSD")
        assert len(positions) == 1
        assert positions[0].ticket == 1001


def test_get_positions_disconnected():
    import importlib
    import mt5_connector
    importlib.reload(mt5_connector)
    conn = mt5_connector.MT5Connector()
    assert conn.get_positions() == []


def test_close_position_success(mock_mt5_lib):
    mock_mt5_lib.order_send.return_value = MagicMock(retcode=10009)
    with patch("mt5_connector.MetaTrader5", return_value=mock_mt5_lib):
        from mt5_connector import MT5Connector
        conn = MT5Connector()
        conn.connect()
        pos = MagicMock(ticket=1001, symbol="XAUUSD", volume=0.01, type=0)
        assert conn.close_position(pos) is True


def test_modify_tp_success(mock_mt5_lib):
    mock_mt5_lib.order_send.return_value = MagicMock(retcode=10009)
    with patch("mt5_connector.MetaTrader5", return_value=mock_mt5_lib):
        from mt5_connector import MT5Connector
        conn = MT5Connector()
        conn.connect()
        pos = MagicMock(ticket=1001, symbol="XAUUSD", sl=1990.0)
        assert conn.modify_position_tp(pos, new_tp=2020.0) is True
