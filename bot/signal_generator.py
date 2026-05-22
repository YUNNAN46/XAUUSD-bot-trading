import json
import logging
import os
import pandas as pd
from ta.trend import EMAIndicator
from ta.volatility import AverageTrueRange

logger = logging.getLogger(__name__)

_TF_H1 = 16385
_TF_M15 = 15

EMA_H1_FAST = 20
EMA_H1_SLOW = 50
EMA_FAST_PERIOD = 14
EMA_SLOW_PERIOD = 24

ARMED_TIMEOUT_CANDLES = 5
ENTRY_WINDOW_CANDLES = 2

ATR_PERIOD = 14
ATR_AVG_WINDOW = 20
ATR_EXTREME_MULTIPLIER = 1.8
EMA_MIN_SLOPE = 0.5

SL_ATR_MULTIPLIER = 2.0

_DEFAULT_STATE_FILE = os.getenv("STATE_FILE", "/app/state.json")


class SignalStateMachine:

    def __init__(self, state_file: str = _DEFAULT_STATE_FILE):
        self._state_file = state_file
        self._state = self._load_state()

    def tick(self, mt5_conn, symbol: str) -> tuple[str, float | None]:
        ind = self._get_indicators(mt5_conn, symbol)
        if ind is None:
            return 'NONE', None

        if ind['atr_avg'] is not None and ind['atr_current'] > ind['atr_avg'] * ATR_EXTREME_MULTIPLIER:
            logger.debug(f"ATR extreme ({ind['atr_current']:.2f} > {ind['atr_avg'] * ATR_EXTREME_MULTIPLIER:.2f}) — skip")
            return 'NONE', None

        phase = self._state.get('phase', 'SCANNING')
        if phase == 'SCANNING':
            return self._phase_scanning(ind)
        if phase == 'ARMED':
            return self._phase_armed(ind)
        if phase == 'WINDOW_OPEN':
            return self._phase_window_open(ind)
        return 'NONE', None

    def _get_indicators(self, mt5_conn, symbol):
        rates_h1 = mt5_conn.get_rates(symbol, _TF_H1, 100)
        if rates_h1 is None or len(rates_h1) < 52:
            logger.debug("Not enough H1 candles")
            return None

        close_h1 = pd.Series([float(r['close']) for r in rates_h1])
        ema20 = EMAIndicator(close_h1, window=EMA_H1_FAST).ema_indicator()
        ema50 = EMAIndicator(close_h1, window=EMA_H1_SLOW).ema_indicator()

        if ema20.iloc[-1] > ema50.iloc[-1]:
            trend = 'BULLISH'
        elif ema20.iloc[-1] < ema50.iloc[-1]:
            trend = 'BEARISH'
        else:
            return None

        rates_m15 = mt5_conn.get_rates(symbol, _TF_M15, 100)
        if rates_m15 is None or len(rates_m15) < 30:
            logger.debug("Not enough M15 candles")
            return None

        close_m15 = pd.Series([float(r['close']) for r in rates_m15])
        open_m15  = pd.Series([float(r['open']) for r in rates_m15])
        high_m15  = pd.Series([float(r['high']) for r in rates_m15])
        low_m15   = pd.Series([float(r['low'])  for r in rates_m15])

        ema14      = EMAIndicator(close_m15, window=EMA_FAST_PERIOD).ema_indicator()
        ema24      = EMAIndicator(close_m15, window=EMA_SLOW_PERIOD).ema_indicator()
        atr_series = AverageTrueRange(high_m15, low_m15, close_m15, window=ATR_PERIOD).average_true_range()

        atr_current = float(atr_series.iloc[-1])
        atr_avg_raw = atr_series.rolling(ATR_AVG_WINDOW).mean().iloc[-1]
        atr_avg     = float(atr_avg_raw) if pd.notna(atr_avg_raw) else None

        slope = float(ema14.iloc[-1]) - float(ema14.iloc[-4])

        logger.info(
            f"H1 trend: {trend} | M15 EMA14={ema14.iloc[-1]:.2f} EMA24={ema24.iloc[-1]:.2f} "
            f"slope={slope:.3f} ATR={atr_current:.2f}"
        )

        return {
            'trend': trend,
            'ema14': ema14,
            'ema24': ema24,
            'slope': slope,
            'open_m15': open_m15,
            'high_m15': high_m15,
            'low_m15': low_m15,
            'price': float(close_m15.iloc[-1]),
            'atr_current': atr_current,
            'atr_avg': atr_avg,
        }

    def _phase_scanning(self, ind) -> tuple[str, float | None]:
        if abs(ind['slope']) < EMA_MIN_SLOPE:
            logger.debug(f"Slope too flat ({ind['slope']:.3f}) — skip crossover")
            return 'NONE', None

        ema14, ema24 = ind['ema14'], ind['ema24']
        prev14 = float(ema14.iloc[-2])
        curr14 = float(ema14.iloc[-1])
        prev24 = float(ema24.iloc[-2])
        curr24 = float(ema24.iloc[-1])
        trend  = ind['trend']

        direction = None
        if trend == 'BULLISH' and prev14 < prev24 and curr14 >= curr24:
            direction = 'BUY'
        elif trend == 'BEARISH' and prev14 > prev24 and curr14 <= curr24:
            direction = 'SELL'

        if direction:
            logger.info(f"SCANNING→ARMED: {direction} crossover, slope={ind['slope']:.3f}")
            self._state = {
                'phase': 'ARMED',
                'direction': direction,
                'pullback_count': 0,
                'pullback_high': None,
                'pullback_low': None,
                'breakout_level': None,
                'armed_candles_elapsed': 0,
                'window_candles_elapsed': 0,
            }
            self._save_state()

        return 'NONE', None

    def _phase_armed(self, ind) -> tuple[str, float | None]:
        direction = self._state['direction']
        expected_trend = 'BULLISH' if direction == 'BUY' else 'BEARISH'

        if ind['trend'] != expected_trend:
            logger.info("ARMED→SCANNING: trend reversed")
            self._reset()
            return 'NONE', None

        ema14 = float(ind['ema14'].iloc[-1])
        ema24 = float(ind['ema24'].iloc[-1])
        if direction == 'BUY' and ema14 < ema24:
            logger.info("ARMED→SCANNING: EMA crossed back")
            self._reset()
            return 'NONE', None
        if direction == 'SELL' and ema14 > ema24:
            logger.info("ARMED→SCANNING: EMA crossed back")
            self._reset()
            return 'NONE', None

        self._state['armed_candles_elapsed'] += 1
        if self._state['armed_candles_elapsed'] >= ARMED_TIMEOUT_CANDLES:
            logger.info("ARMED→SCANNING: timeout")
            self._reset()
            return 'NONE', None

        close = ind['price']
        open_ = float(ind['open_m15'].iloc[-1])
        high  = float(ind['high_m15'].iloc[-1])
        low   = float(ind['low_m15'].iloc[-1])

        is_pullback = (
            (direction == 'BUY'  and close < open_) or
            (direction == 'SELL' and close > open_)
        )

        if is_pullback:
            self._state['pullback_count'] += 1
            ph = self._state.get('pullback_high')
            pl = self._state.get('pullback_low')
            self._state['pullback_high'] = high if ph is None else max(ph, high)
            self._state['pullback_low']  = low  if pl is None else min(pl, low)

        if self._state['pullback_count'] >= 1:
            bl = (self._state['pullback_high'] if direction == 'BUY'
                  else self._state['pullback_low'])
            logger.info(f"ARMED→WINDOW_OPEN: direction={direction} breakout_level={bl:.2f}")
            self._state['phase']          = 'WINDOW_OPEN'
            self._state['breakout_level'] = bl
            self._state['window_candles_elapsed'] = 0

        self._save_state()
        return 'NONE', None

    def _phase_window_open(self, ind) -> tuple[str, float | None]:
        direction      = self._state['direction']
        breakout_level = self._state['breakout_level']
        price          = ind['price']
        expected_trend = 'BULLISH' if direction == 'BUY' else 'BEARISH'

        if ind['trend'] != expected_trend:
            logger.info("WINDOW_OPEN→SCANNING: trend reversed")
            self._reset()
            return 'NONE', None

        self._state['window_candles_elapsed'] += 1
        if self._state['window_candles_elapsed'] > ENTRY_WINDOW_CANDLES:
            logger.info("WINDOW_OPEN→SCANNING: timeout")
            self._reset()
            return 'NONE', None

        if direction == 'BUY' and price > breakout_level:
            sl = round(price - SL_ATR_MULTIPLIER * ind['atr_current'], 2)
            logger.info(f"ENTRY BUY: price={price:.2f} > breakout={breakout_level:.2f}, SL={sl:.2f}")
            self._reset()
            return 'BUY', sl

        if direction == 'SELL' and price < breakout_level:
            sl = round(price + SL_ATR_MULTIPLIER * ind['atr_current'], 2)
            logger.info(f"ENTRY SELL: price={price:.2f} < breakout={breakout_level:.2f}, SL={sl:.2f}")
            self._reset()
            return 'SELL', sl

        self._save_state()
        return 'NONE', None

    def _reset(self):
        self._state = {'phase': 'SCANNING'}
        self._save_state()

    def _load_state(self) -> dict:
        try:
            with open(self._state_file) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {'phase': 'SCANNING'}

    def _save_state(self):
        try:
            with open(self._state_file, 'w') as f:
                json.dump(self._state, f, indent=2)
        except OSError as e:
            logger.warning(f"Cannot save state: {e}")
