import logging
import pandas as pd
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands, AverageTrueRange

logger = logging.getLogger(__name__)

# MT5 timeframe constants
_TF_H1 = 16385
_TF_M15 = 15

ATR_PERIOD = 14
ATR_SL_MULTIPLIER = 1.5  # SL = 1.5x ATR dari entry price
PULLBACK_LOOKBACK = 3     # jumlah candle yang dicek untuk konfirmasi pullback


def _has_pullback(opens: pd.Series, closes: pd.Series, order_type: int) -> bool:
    """
    Pastikan ada minimal 1 candle counter-trend dalam PULLBACK_LOOKBACK candle terakhir.
    BUY  (order_type=0): cari candle bearish (close < open) = pullback di trend bullish.
    SELL (order_type=1): cari candle bullish (close > open) = pullback di trend bearish.
    """
    recent_opens = opens.iloc[-PULLBACK_LOOKBACK - 1:-1]
    recent_closes = closes.iloc[-PULLBACK_LOOKBACK - 1:-1]
    if order_type == 0:
        return bool((recent_closes < recent_opens).any())
    return bool((recent_closes > recent_opens).any())


def get_signal(mt5_conn, symbol: str):
    """
    H1 trend via EMA 20/50. M15 entry via:
      1. RSI 14 momentum cross 50
      2. Harga di bawah/atas BB midline (SMA20)
      3. Pullback confirmation: minimal 1 candle counter-trend di 3 candle terakhir

    SL dinamis = 1.5x ATR dari harga entry.
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
    open_m15 = pd.Series([float(r['open']) for r in rates_m15])
    high_m15 = pd.Series([float(r['high']) for r in rates_m15])
    low_m15 = pd.Series([float(r['low']) for r in rates_m15])

    rsi_series = RSIIndicator(close_m15, window=14).rsi()
    bb = BollingerBands(close_m15, window=20, window_dev=2)
    bb_upper = bb.bollinger_hband().iloc[-1]
    bb_lower = bb.bollinger_lband().iloc[-1]
    bb_mid = bb.bollinger_mavg().iloc[-1]  # SMA20 = midline

    atr = AverageTrueRange(high_m15, low_m15, close_m15, window=ATR_PERIOD).average_true_range().iloc[-1]

    rsi_curr = rsi_series.iloc[-1]
    rsi_prev = rsi_series.iloc[-2]
    price = close_m15.iloc[-1]

    logger.info(
        f"M15: RSI={rsi_curr:.1f} (prev={rsi_prev:.1f}), "
        f"price={price:.2f}, BB_mid={bb_mid:.2f}, "
        f"BB=[{bb_lower:.2f}-{bb_upper:.2f}], ATR={atr:.2f}"
    )

    if trend == 'BULLISH':
        if rsi_prev < 50 <= rsi_curr and price < bb_mid:
            if not _has_pullback(open_m15, close_m15, order_type=0):
                logger.debug("BUY blocked: tidak ada candle bearish di 3 candle terakhir")
                return 'NONE', None
            sl = round(price - ATR_SL_MULTIPLIER * atr, 2)
            logger.info(
                f"BUY signal: RSI {rsi_prev:.1f}->{rsi_curr:.1f}, "
                f"price={price:.2f}, BB_mid={bb_mid:.2f}, ATR={atr:.2f}, SL={sl}"
            )
            return 'BUY', sl

    elif trend == 'BEARISH':
        if rsi_prev > 50 >= rsi_curr and price > bb_mid:
            if not _has_pullback(open_m15, close_m15, order_type=1):
                logger.debug("SELL blocked: tidak ada candle bullish di 3 candle terakhir")
                return 'NONE', None
            sl = round(price + ATR_SL_MULTIPLIER * atr, 2)
            logger.info(
                f"SELL signal: RSI {rsi_prev:.1f}->{rsi_curr:.1f}, "
                f"price={price:.2f}, BB_mid={bb_mid:.2f}, ATR={atr:.2f}, SL={sl}"
            )
            return 'SELL', sl

    return 'NONE', None
