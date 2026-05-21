import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pandas as pd
from unittest.mock import MagicMock, patch


# ---------- helpers ----------

def make_h1_rates(n=100):
    return [{'open': 2000.0, 'high': 2001.0, 'low': 1999.0, 'close': 2000.0} for _ in range(n)]


def make_m15_rates(n=100, tail=None):
    """
    tail: list of (open, close) untuk n candle terakhir.
    Candle sisanya netral (open == close).
    """
    rates = [{'open': 2000.0, 'high': 2001.0, 'low': 1999.0, 'close': 2000.0} for _ in range(n)]
    if tail:
        for i, (o, c) in enumerate(tail):
            idx = n - len(tail) + i
            rates[idx] = {
                'open': o,
                'high': max(o, c) + 0.5,
                'low': min(o, c) - 0.5,
                'close': c,
            }
    return rates


def make_mt5(h1=None, m15=None):
    mt5 = MagicMock()

    def get_rates(symbol, tf, count):
        if tf == 16385:  # H1
            return h1 if h1 is not None else make_h1_rates()
        return m15 if m15 is not None else make_m15_rates()

    mt5.get_rates.side_effect = get_rates
    return mt5


def patch_indicators(ema20, ema50, rsi_prev, rsi_curr, bb_mid, bb_upper, bb_lower, atr):
    """
    Buat patch untuk semua indikator.
    EMAIndicator dipanggil 2x: pertama untuk EMA20, kedua untuk EMA50.
    """
    n = 100
    call_idx = [0]

    ema20_series = pd.Series([ema20] * n)
    ema50_series = pd.Series([ema50] * n)

    def ema_factory(series, window):
        inst = MagicMock()
        inst.ema_indicator.return_value = ema20_series if call_idx[0] == 0 else ema50_series
        call_idx[0] += 1
        return inst

    rsi_series = pd.Series([50.0] * (n - 2) + [rsi_prev, rsi_curr])

    def rsi_factory(series, window):
        inst = MagicMock()
        inst.rsi.return_value = rsi_series
        return inst

    def bb_factory(series, window, window_dev):
        inst = MagicMock()
        inst.bollinger_mavg.return_value = pd.Series([bb_mid] * n)
        inst.bollinger_hband.return_value = pd.Series([bb_upper] * n)
        inst.bollinger_lband.return_value = pd.Series([bb_lower] * n)
        return inst

    def atr_factory(high, low, close, window):
        inst = MagicMock()
        inst.average_true_range.return_value = pd.Series([atr] * n)
        return inst

    return {
        'ema': patch('signal_generator.EMAIndicator', side_effect=ema_factory),
        'rsi': patch('signal_generator.RSIIndicator', side_effect=rsi_factory),
        'bb': patch('signal_generator.BollingerBands', side_effect=bb_factory),
        'atr': patch('signal_generator.AverageTrueRange', side_effect=atr_factory),
    }


def run_signal(mt5, patches):
    from signal_generator import get_signal
    with patches['ema'], patches['rsi'], patches['bb'], patches['atr']:
        return get_signal(mt5, 'XAUUSD')


# ---------- tests: data tidak cukup ----------

def test_returns_none_when_h1_rates_is_none():
    mt5 = make_mt5(h1=None)
    mt5.get_rates.side_effect = lambda s, tf, c: None
    from signal_generator import get_signal
    direction, sl = get_signal(mt5, 'XAUUSD')
    assert direction == 'NONE'
    assert sl is None


def test_returns_none_when_h1_rates_too_few():
    mt5 = make_mt5(h1=make_h1_rates(n=10))
    from signal_generator import get_signal
    direction, sl = get_signal(mt5, 'XAUUSD')
    assert direction == 'NONE'


def test_returns_none_when_m15_rates_is_none():
    mt5 = make_mt5(h1=make_h1_rates(n=100), m15=None)
    p = patch_indicators(2020, 2000, 48, 52, 2010, 2020, 1990, 5.0)
    with p['ema']:
        from signal_generator import get_signal
        # m15 None → get_rates returns None untuk M15
        mt5.get_rates.side_effect = lambda s, tf, c: make_h1_rates() if tf == 16385 else None
        direction, sl = get_signal(mt5, 'XAUUSD')
    assert direction == 'NONE'


# ---------- tests: trend ----------

def test_returns_none_when_trend_is_flat():
    """EMA20 == EMA50 → trend tidak jelas → NONE."""
    m15 = make_m15_rates(tail=[(2005, 2002), (2002, 2003), (2003, 2004), (2004, 2000)])
    mt5 = make_mt5(m15=m15)
    p = patch_indicators(2000, 2000, 48, 52, 2010, 2020, 1990, 5.0)  # EMA20 == EMA50
    direction, sl = run_signal(mt5, p)
    assert direction == 'NONE'


# ---------- tests: BUY signal ----------

def test_buy_signal_when_all_conditions_met():
    """
    BULLISH trend + RSI cross naik 50 + price < BB_mid + ada candle bearish (pullback).
    """
    # 3 candle sebelum current: ada 1 candle bearish (2005→2002)
    m15 = make_m15_rates(tail=[
        (2005.0, 2002.0),  # bearish ← pullback
        (2002.0, 2003.0),  # bullish
        (2003.0, 2004.0),  # bullish
        (2004.0, 2000.0),  # current candle (close=2000)
    ])
    mt5 = make_mt5(m15=m15)
    p = patch_indicators(
        ema20=2020.0, ema50=2000.0,  # BULLISH
        rsi_prev=48.0, rsi_curr=52.0,  # cross naik 50
        bb_mid=2010.0, bb_upper=2020.0, bb_lower=1990.0,
        atr=5.0,
    )
    direction, sl = run_signal(mt5, p)
    assert direction == 'BUY'


def test_buy_sl_equals_price_minus_atr_multiplier():
    """SL untuk BUY = harga entry - 1.5x ATR."""
    m15 = make_m15_rates(tail=[
        (2005.0, 2002.0),
        (2002.0, 2003.0),
        (2003.0, 2004.0),
        (2004.0, 2000.0),  # current close = 2000
    ])
    mt5 = make_mt5(m15=m15)
    p = patch_indicators(2020, 2000, 48, 52, 2010, 2020, 1990, atr=8.0)
    direction, sl = run_signal(mt5, p)
    assert direction == 'BUY'
    assert sl == round(2000.0 - 1.5 * 8.0, 2)  # 1988.0


def test_no_buy_when_rsi_does_not_cross_50():
    """RSI tetap di bawah 50 → tidak ada BUY."""
    m15 = make_m15_rates(tail=[
        (2005.0, 2002.0),
        (2002.0, 2003.0),
        (2003.0, 2004.0),
        (2004.0, 2000.0),
    ])
    mt5 = make_mt5(m15=m15)
    p = patch_indicators(2020, 2000, rsi_prev=45, rsi_curr=48, bb_mid=2010, bb_upper=2020, bb_lower=1990, atr=5)
    direction, sl = run_signal(mt5, p)
    assert direction == 'NONE'


def test_no_buy_when_price_above_bb_mid():
    """Price >= BB midline → harga tidak di zona pullback → tidak ada BUY."""
    m15 = make_m15_rates(tail=[
        (2005.0, 2002.0),
        (2002.0, 2003.0),
        (2003.0, 2004.0),
        (2004.0, 2015.0),  # current close = 2015 > bb_mid (2010)
    ])
    mt5 = make_mt5(m15=m15)
    p = patch_indicators(2020, 2000, 48, 52, bb_mid=2010, bb_upper=2020, bb_lower=1990, atr=5)
    direction, sl = run_signal(mt5, p)
    assert direction == 'NONE'


def test_no_buy_when_no_pullback_candle():
    """Semua 3 candle terakhir bullish → tidak ada pullback → tidak ada BUY."""
    m15 = make_m15_rates(tail=[
        (1999.0, 2001.0),  # bullish
        (2001.0, 2003.0),  # bullish
        (2003.0, 2005.0),  # bullish
        (2005.0, 2000.0),  # current
    ])
    mt5 = make_mt5(m15=m15)
    p = patch_indicators(2020, 2000, 48, 52, bb_mid=2010, bb_upper=2020, bb_lower=1990, atr=5)
    direction, sl = run_signal(mt5, p)
    assert direction == 'NONE'


# ---------- tests: SELL signal ----------

def test_sell_signal_when_all_conditions_met():
    """
    BEARISH trend + RSI cross turun 50 + price > BB_mid + ada candle bullish (pullback).
    """
    # 3 candle sebelum current: ada 1 candle bullish (2000→2003) = pullback di bearish trend
    m15 = make_m15_rates(tail=[
        (2000.0, 2003.0),  # bullish ← pullback di trend bearish
        (2003.0, 2002.0),  # bearish
        (2002.0, 2001.0),  # bearish
        (2001.0, 2015.0),  # current candle (close=2015)
    ])
    mt5 = make_mt5(m15=m15)
    p = patch_indicators(
        ema20=1980.0, ema50=2000.0,  # BEARISH
        rsi_prev=52.0, rsi_curr=48.0,  # cross turun 50
        bb_mid=2010.0, bb_upper=2025.0, bb_lower=1995.0,
        atr=6.0,
    )
    direction, sl = run_signal(mt5, p)
    assert direction == 'SELL'


def test_sell_sl_equals_price_plus_atr_multiplier():
    """SL untuk SELL = harga entry + 1.5x ATR."""
    m15 = make_m15_rates(tail=[
        (2000.0, 2003.0),
        (2003.0, 2002.0),
        (2002.0, 2001.0),
        (2001.0, 2015.0),  # current close = 2015
    ])
    mt5 = make_mt5(m15=m15)
    p = patch_indicators(1980, 2000, 52, 48, bb_mid=2010, bb_upper=2025, bb_lower=1995, atr=6.0)
    direction, sl = run_signal(mt5, p)
    assert direction == 'SELL'
    assert sl == round(2015.0 + 1.5 * 6.0, 2)  # 2024.0


def test_no_sell_when_no_pullback_candle():
    """Semua 3 candle terakhir bearish → tidak ada pullback → tidak ada SELL."""
    m15 = make_m15_rates(tail=[
        (2005.0, 2003.0),  # bearish
        (2003.0, 2001.0),  # bearish
        (2001.0, 1999.0),  # bearish
        (1999.0, 2015.0),  # current
    ])
    mt5 = make_mt5(m15=m15)
    p = patch_indicators(1980, 2000, 52, 48, bb_mid=2010, bb_upper=2025, bb_lower=1995, atr=5)
    direction, sl = run_signal(mt5, p)
    assert direction == 'NONE'


def test_no_sell_when_price_below_bb_mid():
    """Price <= BB midline di trend BEARISH → tidak ada SELL."""
    m15 = make_m15_rates(tail=[
        (2000.0, 2003.0),
        (2003.0, 2002.0),
        (2002.0, 2001.0),
        (2001.0, 2005.0),  # current close = 2005 < bb_mid (2010)
    ])
    mt5 = make_mt5(m15=m15)
    p = patch_indicators(1980, 2000, 52, 48, bb_mid=2010, bb_upper=2025, bb_lower=1995, atr=5)
    direction, sl = run_signal(mt5, p)
    assert direction == 'NONE'
