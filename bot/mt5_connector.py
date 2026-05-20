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
        if MetaTrader5 is None:
            logger.error("mt5linux library not installed — only available on Linux with Wine+MT5")
            return False
        try:
            self._mt5 = MetaTrader5(host=self.host, port=self.port)
            if self._mt5.initialize(
                login=config.MT5_LOGIN,
                password=config.MT5_PASSWORD,
                server=config.MT5_SERVER,
            ):
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
            "deviation": config.MT5_DEVIATION,
            "magic": config.MT5_MAGIC,
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

    def get_rates(self, symbol: str, timeframe: int, count: int = 100):
        if not self._connected:
            return None
        return self._mt5.copy_rates_from_pos(symbol, timeframe, 0, count)

    def open_position(self, symbol: str, order_type: int, lot: float, sl: float, tp: float, comment: str = "bot"):
        """order_type: 0=BUY, 1=SELL. Returns ticket number or None."""
        if not self._connected:
            return None
        tick = self.get_tick(symbol)
        if not tick:
            return None
        price = tick.ask if order_type == 0 else tick.bid
        request = {
            "action": self._mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(lot),
            "type": self._mt5.ORDER_TYPE_BUY if order_type == 0 else self._mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": float(sl),
            "tp": float(tp),
            "deviation": config.MT5_DEVIATION,
            "magic": config.MT5_MAGIC,
            "comment": comment,
            "type_time": self._mt5.ORDER_TIME_GTC,
            "type_filling": self._mt5.ORDER_FILLING_IOC,
        }
        result = self._mt5.order_send(request)
        if result and result.retcode == self._mt5.TRADE_RETCODE_DONE:
            logger.info(f"Order opened: ticket={result.order}, {symbol} {'BUY' if order_type == 0 else 'SELL'} {lot}lot")
            return result.order
        logger.error(f"open_position failed: retcode={getattr(result, 'retcode', None)}, comment={getattr(result, 'comment', '')}")
        return None

    def partial_close_position(self, position, volume: float) -> bool:
        """Close a portion of an open position (e.g., 50% at TP1)."""
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
            "volume": float(volume),
            "type": close_type,
            "position": position.ticket,
            "price": price,
            "deviation": config.MT5_DEVIATION,
            "magic": config.MT5_MAGIC,
            "comment": "TP1 partial",
            "type_time": self._mt5.ORDER_TIME_GTC,
            "type_filling": self._mt5.ORDER_FILLING_IOC,
        }
        result = self._mt5.order_send(request)
        if result and result.retcode == self._mt5.TRADE_RETCODE_DONE:
            logger.info(f"Partial close {position.ticket}: {volume}lot closed")
            return True
        logger.error(f"Partial close failed for {position.ticket}: retcode={getattr(result, 'retcode', None)}")
        return False

    def modify_position_sl(self, position, new_sl: float) -> bool:
        """Modify only the SL of a position (keeps existing TP)."""
        if not self._connected:
            return False
        request = {
            "action": self._mt5.TRADE_ACTION_SLTP,
            "symbol": position.symbol,
            "position": position.ticket,
            "sl": float(new_sl),
            "tp": position.tp,
        }
        result = self._mt5.order_send(request)
        if result and result.retcode == self._mt5.TRADE_RETCODE_DONE:
            return True
        logger.error(f"Modify SL failed for {position.ticket}: {result}")
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
        if result and result.retcode == self._mt5.TRADE_RETCODE_DONE:
            return True
        logger.error(f"Modify TP failed for {position.ticket}: {result}")
        return False
