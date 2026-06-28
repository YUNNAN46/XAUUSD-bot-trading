import logging
import config

logger = logging.getLogger(__name__)


class LondonBreakoutStrategy:

    def __init__(self):
        self._asian_high: float | None = None
        self._asian_low:  float | None = None

    def update_asian_range(self, high: float, low: float) -> None:
        if self._asian_high is None or high > self._asian_high:
            self._asian_high = high
        if self._asian_low is None or low < self._asian_low:
            self._asian_low = low

    @property
    def asian_high(self) -> float | None:
        return self._asian_high

    @property
    def asian_low(self) -> float | None:
        return self._asian_low

    @property
    def range_size(self) -> float | None:
        if self._asian_high is None or self._asian_low is None:
            return None
        return round(self._asian_high - self._asian_low, 2)

    def is_range_valid(self) -> bool:
        r = self.range_size
        if r is None:
            return False
        return config.RANGE_MIN_USD <= r <= config.RANGE_MAX_USD

    def get_pending_orders(self) -> dict | None:
        if not self.is_range_valid():
            return None
        r          = self.range_size
        buy_price  = round(self._asian_high + config.BREAKOUT_BUFFER_USD, 2)
        sell_price = round(self._asian_low  - config.BREAKOUT_BUFFER_USD, 2)
        sl_buy     = round(self._asian_low  - config.SL_BUFFER_USD, 2)
        sl_sell    = round(self._asian_high + config.SL_BUFFER_USD, 2)
        tp_buy     = round(buy_price  + r * config.TP_RR_BREAKOUT, 2)
        tp_sell    = round(sell_price - r * config.TP_RR_BREAKOUT, 2)
        return {
            'buy_price':  buy_price,
            'sell_price': sell_price,
            'sl_buy':     sl_buy,
            'sl_sell':    sl_sell,
            'tp_buy':     tp_buy,
            'tp_sell':    tp_sell,
            'range_size': r,
        }

    def reset(self) -> None:
        self._asian_high = None
        self._asian_low  = None
