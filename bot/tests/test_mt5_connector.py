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
    mock.SYMBOL_FILLING_FOK = 1
    mock.SYMBOL_FILLING_IOC = 2
    mock.ORDER_FILLING_FOK = 0
    mock.ORDER_FILLING_IOC = 1
    mock.ORDER_FILLING_RETURN = 2
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


def test_connect_when_library_not_available():
    import mt5_connector
    import importlib
    original = mt5_connector.MetaTrader5
    mt5_connector.MetaTrader5 = None
    conn = mt5_connector.MT5Connector()
    result = conn.connect()
    mt5_connector.MetaTrader5 = original
    assert result is False
    assert conn.is_connected is False


def test_disconnect_clears_state(mock_mt5_lib):
    with patch("mt5_connector.MetaTrader5", return_value=mock_mt5_lib):
        from mt5_connector import MT5Connector
        conn = MT5Connector()
        conn.connect()
        assert conn.is_connected is True
        conn.disconnect()
        assert conn.is_connected is False


def test_close_position_when_order_send_returns_none(mock_mt5_lib):
    mock_mt5_lib.order_send.return_value = None
    with patch("mt5_connector.MetaTrader5", return_value=mock_mt5_lib):
        from mt5_connector import MT5Connector
        conn = MT5Connector()
        conn.connect()
        pos = MagicMock(ticket=1001, symbol="XAUUSD", volume=0.01, type=0)
        assert conn.close_position(pos) is False


def test_modify_tp_when_order_send_returns_none(mock_mt5_lib):
    mock_mt5_lib.order_send.return_value = None
    with patch("mt5_connector.MetaTrader5", return_value=mock_mt5_lib):
        from mt5_connector import MT5Connector
        conn = MT5Connector()
        conn.connect()
        pos = MagicMock(ticket=1001, symbol="XAUUSD", sl=1990.0)
        assert conn.modify_position_tp(pos, new_tp=2020.0) is False


def test_get_filling_type_picks_fok_when_supported(mock_mt5_lib):
    mock_mt5_lib.symbol_info.return_value = MagicMock(filling_mode=1)  # FOK only
    with patch("mt5_connector.MetaTrader5", return_value=mock_mt5_lib):
        from mt5_connector import MT5Connector
        conn = MT5Connector()
        conn.connect()
        assert conn._get_filling_type("XAUUSD") == mock_mt5_lib.ORDER_FILLING_FOK


def test_get_filling_type_picks_ioc_when_fok_unsupported(mock_mt5_lib):
    mock_mt5_lib.symbol_info.return_value = MagicMock(filling_mode=2)  # IOC only
    with patch("mt5_connector.MetaTrader5", return_value=mock_mt5_lib):
        from mt5_connector import MT5Connector
        conn = MT5Connector()
        conn.connect()
        assert conn._get_filling_type("XAUUSD") == mock_mt5_lib.ORDER_FILLING_IOC


def test_get_filling_type_falls_back_to_return(mock_mt5_lib):
    mock_mt5_lib.symbol_info.return_value = MagicMock(filling_mode=0)  # neither FOK nor IOC
    with patch("mt5_connector.MetaTrader5", return_value=mock_mt5_lib):
        from mt5_connector import MT5Connector
        conn = MT5Connector()
        conn.connect()
        assert conn._get_filling_type("XAUUSD") == mock_mt5_lib.ORDER_FILLING_RETURN


def test_get_filling_type_when_symbol_info_unavailable(mock_mt5_lib):
    mock_mt5_lib.symbol_info.return_value = None
    with patch("mt5_connector.MetaTrader5", return_value=mock_mt5_lib):
        from mt5_connector import MT5Connector
        conn = MT5Connector()
        conn.connect()
        assert conn._get_filling_type("XAUUSD") == mock_mt5_lib.ORDER_FILLING_IOC


def test_open_position_uses_detected_filling_type(mock_mt5_lib):
    mock_mt5_lib.symbol_info.return_value = MagicMock(filling_mode=1)  # FOK only
    mock_mt5_lib.order_send.return_value = MagicMock(retcode=10009, order=555)
    with patch("mt5_connector.MetaTrader5", return_value=mock_mt5_lib):
        from mt5_connector import MT5Connector
        conn = MT5Connector()
        conn.connect()
        ticket = conn.open_position("XAUUSD", order_type=0, lot=0.01, sl=1990.0, tp=2020.0)
        assert ticket == 555
        sent_request = mock_mt5_lib.order_send.call_args[0][0]
        assert sent_request["type_filling"] == mock_mt5_lib.ORDER_FILLING_FOK


# --- place_stop_order ---

def _make_conn(connected=True):
    from mt5_connector import MT5Connector
    conn = MT5Connector.__new__(MT5Connector)
    conn._connected = connected
    conn.last_order_error = None
    mt5 = MagicMock()
    mt5.ORDER_TYPE_BUY_STOP  = 4
    mt5.ORDER_TYPE_SELL_STOP = 5
    mt5.ORDER_TIME_DAY       = 1
    mt5.TRADE_ACTION_PENDING = 5
    mt5.TRADE_ACTION_REMOVE  = 8
    mt5.TRADE_RETCODE_DONE   = 10009
    mt5.symbol_info.return_value = MagicMock(filling_mode=1)
    conn._mt5 = mt5
    return conn, mt5


def test_place_stop_order_buy_stop_returns_ticket():
    conn, mt5 = _make_conn()
    result_mock = MagicMock(retcode=10009, order=9999)
    mt5.order_send.return_value = result_mock
    ticket = conn.place_stop_order('XAUUSD', 0, 0.01, 2320.5, 2309.7, 2335.5)
    assert ticket == 9999
    sent = mt5.order_send.call_args[0][0]
    assert sent['type'] == 4   # ORDER_TYPE_BUY_STOP
    assert sent['price'] == 2320.5


def test_place_stop_order_sell_stop_uses_correct_type():
    conn, mt5 = _make_conn()
    result_mock = MagicMock(retcode=10009, order=8888)
    mt5.order_send.return_value = result_mock
    ticket = conn.place_stop_order('XAUUSD', 1, 0.01, 2309.5, 2320.3, 2294.5)
    assert ticket == 8888
    sent = mt5.order_send.call_args[0][0]
    assert sent['type'] == 5   # ORDER_TYPE_SELL_STOP


def test_place_stop_order_returns_none_on_failure():
    conn, mt5 = _make_conn()
    mt5.order_send.return_value = MagicMock(retcode=10006, comment='rejected')
    ticket = conn.place_stop_order('XAUUSD', 0, 0.01, 2320.5, 2309.7, 2335.5)
    assert ticket is None
    assert conn.last_order_error == (10006, 'rejected')


def test_place_stop_order_returns_none_when_disconnected():
    conn, _ = _make_conn(connected=False)
    ticket = conn.place_stop_order('XAUUSD', 0, 0.01, 2320.5, 2309.7, 2335.5)
    assert ticket is None


# --- cancel_order ---

def test_cancel_order_sends_remove_action():
    conn, mt5 = _make_conn()
    mt5.order_send.return_value = MagicMock(retcode=10009)
    result = conn.cancel_order(12345)
    assert result is True
    sent = mt5.order_send.call_args[0][0]
    assert sent['action'] == 8   # TRADE_ACTION_REMOVE
    assert sent['order']  == 12345


def test_cancel_order_returns_false_on_failure():
    conn, mt5 = _make_conn()
    mt5.order_send.return_value = MagicMock(retcode=10006)
    result = conn.cancel_order(12345)
    assert result is False


def test_cancel_order_returns_false_when_disconnected():
    conn, _ = _make_conn(connected=False)
    assert conn.cancel_order(12345) is False


def test_place_stop_order_returns_none_when_order_send_returns_none():
    conn, mt5 = _make_conn()
    mt5.order_send.return_value = None
    ticket = conn.place_stop_order('XAUUSD', 0, 0.01, 2320.5, 2309.7, 2335.5)
    assert ticket is None


def test_cancel_order_returns_false_when_order_send_returns_none():
    conn, mt5 = _make_conn()
    mt5.order_send.return_value = None
    result = conn.cancel_order(12345)
    assert result is False


# --- get_pending_orders ---

def test_get_pending_orders_returns_list():
    conn, mt5 = _make_conn()
    order = MagicMock()
    mt5.orders_get.return_value = [order]
    result = conn.get_pending_orders('XAUUSD')
    assert result == [order]
    mt5.orders_get.assert_called_once_with(symbol='XAUUSD')


def test_get_pending_orders_returns_empty_when_none():
    conn, mt5 = _make_conn()
    mt5.orders_get.return_value = None
    assert conn.get_pending_orders('XAUUSD') == []


def test_get_pending_orders_returns_empty_when_disconnected():
    conn, _ = _make_conn(connected=False)
    assert conn.get_pending_orders('XAUUSD') == []


def test_get_pending_orders_no_symbol_calls_orders_get_without_kwarg():
    conn, mt5 = _make_conn()
    mt5.orders_get.return_value = []
    result = conn.get_pending_orders()   # no symbol
    mt5.orders_get.assert_called_once_with()  # no keyword arg
    assert result == []
