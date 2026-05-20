import logging
import pandas as pd
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands

logger = logging.getLogger(__name__)

# MT5 timeframe constants
_TF_H1 = 16385
_TF_M15 = 15


def get_signal(mt5_conn, symbol: str):
    """
    Analyze H1 trend via EMA 20/50, then look for M15 entry via RSI 14 + BB 20.

    Trend filter (H1):
      - EMA20 > EMA50 → BULLISH (only look for BUY)
      - EMA20 < EMA50 → BEARISH (only look for SELL)

    Entry signal (M15):
      - BUY:  RSI crosses up through 30 (oversold exit) + price near/below lower BB
      - SELL: RSI crosses down through 70 (overbought exit) + price near/above upper BB

    Returns (direction, sl_price) where direction is 'BUY', 'SELL', or 'NONE'.
    SL is placed just outside the Bollinger Band.
    """
    rates_h1 = mt5_conn.get_rates(symbol, _TF_H1, 100)
    if rates_h1 is None or len(rates_h1) < 52:
        logger.debug("Not enough H1 candles")
        return 'NONE', None

    close_h1 = pd.Series([float(r['close']) for r in rates_h1])
    ema20 = EMAIndicator(close_h1, window=20).ema_indicator()
    ema50 = EMAIndicator(close_h1, window=50).ema_indicator()

    last_ema20 = ema20.iloc[-1]
    last_ema50 = ema50.iloc[-1]

    if last_ema20 > last_ema50:
        trend = 'BULLISH'
    elif last_ema20 < last_ema50:
        trend = 'BEARISH'
    else:
        return 'NONE', None

    logger.info(f"H1 trend: {trend} (EMA20={last_ema20:.2f}, EMA50={last_ema50:.2f})")

    rates_m15 = mt5_conn.get_rates(symbol, _TF_M15, 100)
    if rates_m15 is None or len(rates_m15) < 22:
        logger.debug("Not enough M15 candles")
        return 'NONE', None

    close_m15 = pd.Series([float(r['close']) for r in rates_m15])
    rsi_series = RSIIndicator(close_m15, window=14).rsi()
    bb = BollingerBands(close_m15, window=20, window_dev=2)
    bb_upper = bb.bollinger_hband().iloc[-1]
    bb_lower = bb.bollinger_lband().iloc[-1]
    bb_width = bb_upper - bb_lower

    rsi_curr = rsi_series.iloc[-1]
    rsi_prev = rsi_series.iloc[-2]
    price = close_m15.iloc[-1]

    # Allow 10% of BB width as tolerance around the band
    tolerance = bb_width * 0.10

    if trend == 'BULLISH':
        if rsi_prev < 30 <= rsi_curr and price <= bb_lower + tolerance:
            sl = round(bb_lower - bb_width * 0.1, 2)
            logger.info(
                f"BUY signal: RSI {rsi_prev:.1f}→{rsi_curr:.1f}, "
                f"price={price:.2f}, BB_lower={bb_lower:.2f}, SL={sl}"
            )
            return 'BUY', sl

    elif trend == 'BEARISH':
        if rsi_prev > 70 >= rsi_curr and price >= bb_upper - tolerance:
            sl = round(bb_upper + bb_width * 0.1, 2)
            logger.info(
                f"SELL signal: RSI {rsi_prev:.1f}→{rsi_curr:.1f}, "
                f"price={price:.2f}, BB_upper={bb_upper:.2f}, SL={sl}"
            )
            return 'SELL', sl

    return 'NONE', None
