import logging
import config

logger = logging.getLogger(__name__)

try:
    from mt5linux import MetaTrader5
except ImportError:
    MetaTrader5 = None


class MT5Connector:
    def __init__(self, host: str = None, port: int = None):
        self.host = host or config.MT5_HOST
        self.port = port or config.MT5_PORT
        self._mt5 = None
        self._connected = False

    def connect(self) -> bool:
        try:
            self._mt5 = MetaTrader5(host=self.host, port=self.port)
            if self._mt5.initialize():
                self._connected = True
                logger.info(f"MT5 connected: {self.host}:{self.port}")
                return True
            logger.error(f"MT5 init failed: {self._mt5.last_error()}")
            return False
        except Exception as e:
            logger.error(f"MT5 connection error: {e}")
            return False

    def disconnect(self):
        if self._mt5 and self._connected:
            self._mt5.shutdown()
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def get_account_info(self):
        if not self._connected:
            return None
        return self._mt5.account_info()

    def get_balance(self) -> float:
        info = self.get_account_info()
        return info.balance if info else 0.0

    def get_equity(self) -> float:
        info = self.get_account_info()
        return info.equity if info else 0.0

    def get_positions(self, symbol: str = None):
        if not self._connected:
            return []
        result = self._mt5.positions_get(symbol=symbol) if symbol else self._mt5.positions_get()
        return list(result) if result else []

    def get_symbol_info(self, symbol: str):
        if not self._connected:
            return None
        return self._mt5.symbol_info(symbol)

    def get_tick(self, symbol: str):
        if not self._connected:
            return None
        return self._mt5.symbol_info_tick(symbol)

    def get_spread(self, symbol: str) -> int:
        info = self.get_symbol_info(symbol)
        return info.spread if info else 999

    def close_position(self, position) -> bool:
        if not self._connected:
            return False
        tick = self.get_tick(position.symbol)
        if not tick:
            return False
        close_type = self._mt5.ORDER_TYPE_SELL if position.type == 0 else self._mt5.ORDER_TYPE_BUY
        price = tick.bid if position.type == 0 else tick.ask
        request = {
            "action": self._mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": close_type,
            "position": position.ticket,
            "price": price,
            "deviation": 20,
            "magic": 12345,
            "comment": "Bot close",
            "type_time": self._mt5.ORDER_TIME_GTC,
            "type_filling": self._mt5.ORDER_FILLING_IOC,
        }
        result = self._mt5.order_send(request)
        if result and result.retcode == self._mt5.TRADE_RETCODE_DONE:
            logger.info(f"Position {position.ticket} closed")
            return True
        logger.error(f"Close failed: {result}")
        return False

    def modify_position_tp(self, position, new_tp: float) -> bool:
        if not self._connected:
            return False
        request = {
            "action": self._mt5.TRADE_ACTION_SLTP,
            "symbol": position.symbol,
            "position": position.ticket,
            "sl": position.sl,
            "tp": new_tp,
        }
        result = self._mt5.order_send(request)
        return bool(result and result.retcode == self._mt5.TRADE_RETCODE_DONE)
