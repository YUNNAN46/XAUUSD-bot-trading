import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pandas as pd
from unittest.mock import MagicMock, patch


# ---------- helpers ----------

def make_indicators(
    trend='BULLISH',
    slope=1.0,
    prev_ema14=2009.0, curr_ema14=2012.0,
    prev_ema24=2010.0, curr_ema24=2011.0,
    price=2015.0, open_=2012.0, high=2016.0, low=2011.0,
    atr_current=5.0, atr_avg=4.0,
):
    n = 100
    ema14_series = pd.Series([prev_ema14] * (n - 1) + [curr_ema14])
    ema24_series = pd.Series([prev_ema24] * (n - 1) + [curr_ema24])
    open_series  = pd.Series([2000.0] * (n - 1) + [open_])
    high_series  = pd.Series([2001.0] * (n - 1) + [high])
    low_series   = pd.Series([1999.0] * (n - 1) + [low])
    return {
        'trend': trend,
        'ema14': ema14_series,
        'ema24': ema24_series,
        'slope': slope,
        'open_m15': open_series,
        'high_m15': high_series,
        'low_m15': low_series,
        'price': price,
        'atr_current': atr_current,
        'atr_avg': atr_avg,
    }


def make_sm(tmp_path, initial_state=None):
    from signal_generator import SignalStateMachine
    f = str(tmp_path / "state.json")
    if initial_state:
        with open(f, 'w') as fp:
            json.dump(initial_state, fp)
    return SignalStateMachine(state_file=f)


def tick_with(sm, ind):
    with patch.object(sm, '_get_indicators', return_value=ind):
        return sm.tick(MagicMock(), 'XAUUSD')


# ---------- SCANNING phase ----------

def test_scanning_buy_crossover_transitions_to_armed(tmp_path):
    """EMA14 cross above EMA24 in BULLISH trend → phase ARMED, direction BUY."""
    sm = make_sm(tmp_path)
    # prev_ema14 < prev_ema24, curr_ema14 >= curr_ema24
    ind = make_indicators(trend='BULLISH', slope=1.5,
                          prev_ema14=2009.0, curr_ema14=2012.0,
                          prev_ema24=2010.0, curr_ema24=2011.0)
    result = tick_with(sm, ind)
    assert result == ('NONE', None)
    assert sm._state['phase'] == 'ARMED'
    assert sm._state['direction'] == 'BUY'


def test_scanning_sell_crossover_transitions_to_armed(tmp_path):
    """EMA14 cross below EMA24 in BEARISH trend → phase ARMED, direction SELL."""
    sm = make_sm(tmp_path)
    # prev_ema14 > prev_ema24, curr_ema14 <= curr_ema24
    ind = make_indicators(trend='BEARISH', slope=-1.5,
                          prev_ema14=2012.0, curr_ema14=2009.0,
                          prev_ema24=2010.0, curr_ema24=2011.0)
    result = tick_with(sm, ind)
    assert result == ('NONE', None)
    assert sm._state['phase'] == 'ARMED'
    assert sm._state['direction'] == 'SELL'


def test_scanning_no_crossover_stays_scanning(tmp_path):
    """EMA14 already above EMA24 (no fresh crossover) → stays SCANNING."""
    sm = make_sm(tmp_path)
    ind = make_indicators(trend='BULLISH', slope=1.0,
                          prev_ema14=2012.0, curr_ema14=2013.0,  # both above ema24
                          prev_ema24=2010.0, curr_ema24=2011.0)
    result = tick_with(sm, ind)
    assert result == ('NONE', None)
    assert sm._state['phase'] == 'SCANNING'


def test_scanning_slope_too_flat_blocks_crossover(tmp_path):
    """Slope < EMA_MIN_SLOPE (0.5) → crossover ignored."""
    sm = make_sm(tmp_path)
    ind = make_indicators(trend='BULLISH', slope=0.3,  # too flat
                          prev_ema14=2009.0, curr_ema14=2012.0,
                          prev_ema24=2010.0, curr_ema24=2011.0)
    tick_with(sm, ind)
    assert sm._state['phase'] == 'SCANNING'


def test_scanning_bearish_crossover_ignored_in_bullish_trend(tmp_path):
    """SELL crossover when trend is BULLISH → ignored."""
    sm = make_sm(tmp_path)
    ind = make_indicators(trend='BULLISH', slope=-1.5,
                          prev_ema14=2012.0, curr_ema14=2009.0,
                          prev_ema24=2010.0, curr_ema24=2011.0)
    tick_with(sm, ind)
    assert sm._state['phase'] == 'SCANNING'


# ---------- ARMED phase ----------

def test_armed_bearish_pullback_transitions_to_window_open(tmp_path):
    """Bearish candle (close < open) in BUY ARMED → transitions to WINDOW_OPEN."""
    state = {
        'phase': 'ARMED', 'direction': 'BUY',
        'pullback_count': 0, 'pullback_high': None, 'pullback_low': None,
        'breakout_level': None, 'armed_candles_elapsed': 0, 'window_candles_elapsed': 0,
    }
    sm = make_sm(tmp_path, initial_state=state)
    ind = make_indicators(trend='BULLISH', price=2008.0, open_=2010.0,  # bearish candle
                          high=2011.0, low=2007.0)
    tick_with(sm, ind)
    assert sm._state['phase'] == 'WINDOW_OPEN'
    assert sm._state['breakout_level'] == 2011.0  # highest high of pullback


def test_armed_bullish_pullback_transitions_to_window_open_sell(tmp_path):
    """Bullish candle (close > open) in SELL ARMED → transitions to WINDOW_OPEN."""
    state = {
        'phase': 'ARMED', 'direction': 'SELL',
        'pullback_count': 0, 'pullback_high': None, 'pullback_low': None,
        'breakout_level': None, 'armed_candles_elapsed': 0, 'window_candles_elapsed': 0,
    }
    sm = make_sm(tmp_path, initial_state=state)
    ind = make_indicators(trend='BEARISH', price=2012.0, open_=2010.0,  # bullish candle
                          high=2013.0, low=2009.0)
    tick_with(sm, ind)
    assert sm._state['phase'] == 'WINDOW_OPEN'
    assert sm._state['breakout_level'] == 2009.0  # lowest low of pullback


def test_armed_timeout_resets_to_scanning(tmp_path):
    """After ARMED_TIMEOUT_CANDLES (5) candles with no pullback → reset to SCANNING."""
    state = {
        'phase': 'ARMED', 'direction': 'BUY',
        'pullback_count': 0, 'pullback_high': None, 'pullback_low': None,
        'breakout_level': None, 'armed_candles_elapsed': 4, 'window_candles_elapsed': 0,
    }
    sm = make_sm(tmp_path, initial_state=state)
    # Bullish candle (not a pullback for BUY)
    ind = make_indicators(trend='BULLISH', price=2013.0, open_=2010.0)
    tick_with(sm, ind)
    assert sm._state['phase'] == 'SCANNING'


def test_armed_trend_reversal_resets_to_scanning(tmp_path):
    """Trend changes while ARMED → reset to SCANNING."""
    state = {
        'phase': 'ARMED', 'direction': 'BUY',
        'pullback_count': 0, 'pullback_high': None, 'pullback_low': None,
        'breakout_level': None, 'armed_candles_elapsed': 1, 'window_candles_elapsed': 0,
    }
    sm = make_sm(tmp_path, initial_state=state)
    ind = make_indicators(trend='BEARISH')  # trend flipped
    tick_with(sm, ind)
    assert sm._state['phase'] == 'SCANNING'


def test_armed_ema_crossback_resets_to_scanning(tmp_path):
    """EMA14 crosses back below EMA24 while BUY ARMED → reset."""
    state = {
        'phase': 'ARMED', 'direction': 'BUY',
        'pullback_count': 0, 'pullback_high': None, 'pullback_low': None,
        'breakout_level': None, 'armed_candles_elapsed': 1, 'window_candles_elapsed': 0,
    }
    sm = make_sm(tmp_path, initial_state=state)
    ind = make_indicators(trend='BULLISH',
                          prev_ema14=2009.0, curr_ema14=2009.0,  # ema14 < ema24
                          prev_ema24=2011.0, curr_ema24=2011.0)
    tick_with(sm, ind)
    assert sm._state['phase'] == 'SCANNING'


# ---------- WINDOW_OPEN phase ----------

def test_window_open_buy_breakout_returns_buy_signal(tmp_path):
    """Price closes above breakout_level in BUY setup → BUY signal returned."""
    state = {
        'phase': 'WINDOW_OPEN', 'direction': 'BUY',
        'pullback_count': 1, 'pullback_high': 2013.0, 'pullback_low': 2010.0,
        'breakout_level': 2013.0, 'armed_candles_elapsed': 1, 'window_candles_elapsed': 0,
    }
    sm = make_sm(tmp_path, initial_state=state)
    ind = make_indicators(trend='BULLISH', price=2015.0, atr_current=5.0)  # price > 2013
    signal, sl = tick_with(sm, ind)
    assert signal == 'BUY'
    assert sl == round(2015.0 - 2.0 * 5.0, 2)  # 2005.0


def test_window_open_sell_breakout_returns_sell_signal(tmp_path):
    """Price closes below breakout_level in SELL setup → SELL signal returned."""
    state = {
        'phase': 'WINDOW_OPEN', 'direction': 'SELL',
        'pullback_count': 1, 'pullback_high': 2013.0, 'pullback_low': 2010.0,
        'breakout_level': 2010.0, 'armed_candles_elapsed': 1, 'window_candles_elapsed': 0,
    }
    sm = make_sm(tmp_path, initial_state=state)
    ind = make_indicators(trend='BEARISH', price=2008.0, atr_current=5.0)  # price < 2010
    signal, sl = tick_with(sm, ind)
    assert signal == 'SELL'
    assert sl == round(2008.0 + 2.0 * 5.0, 2)  # 2018.0


def test_window_open_no_breakout_stays_window_open(tmp_path):
    """Price does not break out → stays WINDOW_OPEN."""
    state = {
        'phase': 'WINDOW_OPEN', 'direction': 'BUY',
        'pullback_count': 1, 'pullback_high': 2013.0, 'pullback_low': 2010.0,
        'breakout_level': 2013.0, 'armed_candles_elapsed': 1, 'window_candles_elapsed': 0,
    }
    sm = make_sm(tmp_path, initial_state=state)
    ind = make_indicators(trend='BULLISH', price=2012.0)  # price < breakout_level
    result = tick_with(sm, ind)
    assert result == ('NONE', None)
    assert sm._state['phase'] == 'WINDOW_OPEN'


def test_window_open_timeout_resets_to_scanning(tmp_path):
    """After ENTRY_WINDOW_CANDLES (2) with no breakout → reset to SCANNING."""
    state = {
        'phase': 'WINDOW_OPEN', 'direction': 'BUY',
        'pullback_count': 1, 'pullback_high': 2013.0, 'pullback_low': 2010.0,
        'breakout_level': 2013.0, 'armed_candles_elapsed': 1, 'window_candles_elapsed': 2,
    }
    sm = make_sm(tmp_path, initial_state=state)
    ind = make_indicators(trend='BULLISH', price=2012.0)  # no breakout
    tick_with(sm, ind)
    assert sm._state['phase'] == 'SCANNING'


def test_window_open_trend_reversal_resets_to_scanning(tmp_path):
    """Trend reverses while WINDOW_OPEN → reset to SCANNING."""
    state = {
        'phase': 'WINDOW_OPEN', 'direction': 'BUY',
        'pullback_count': 1, 'pullback_high': 2013.0, 'pullback_low': 2010.0,
        'breakout_level': 2013.0, 'armed_candles_elapsed': 1, 'window_candles_elapsed': 0,
    }
    sm = make_sm(tmp_path, initial_state=state)
    ind = make_indicators(trend='BEARISH', price=2015.0)
    tick_with(sm, ind)
    assert sm._state['phase'] == 'SCANNING'


# ---------- Filters ----------

def test_atr_extreme_blocks_scanning(tmp_path):
    """ATR current > avg × 1.8 → NONE returned, phase stays SCANNING."""
    sm = make_sm(tmp_path)
    ind = make_indicators(atr_current=10.0, atr_avg=5.0,  # 10 > 5*1.8=9 → extreme
                          trend='BULLISH', slope=2.0,
                          prev_ema14=2009.0, curr_ema14=2012.0,
                          prev_ema24=2010.0, curr_ema24=2011.0)
    result = tick_with(sm, ind)
    assert result == ('NONE', None)
    assert sm._state['phase'] == 'SCANNING'


def test_atr_within_normal_range_does_not_block(tmp_path):
    """ATR current <= avg × 1.8 → filter does not block."""
    sm = make_sm(tmp_path)
    ind = make_indicators(atr_current=8.0, atr_avg=5.0,  # 8 < 5*1.8=9 → ok
                          trend='BULLISH', slope=2.0,
                          prev_ema14=2009.0, curr_ema14=2012.0,
                          prev_ema24=2010.0, curr_ema24=2011.0)
    tick_with(sm, ind)
    assert sm._state['phase'] == 'ARMED'  # crossover was processed


def test_get_indicators_returns_none_when_h1_insufficient(tmp_path):
    """get_rates returns None for H1 → tick returns NONE."""
    from signal_generator import SignalStateMachine
    sm = SignalStateMachine(state_file=str(tmp_path / "state.json"))
    mt5 = MagicMock()
    mt5.get_rates.return_value = None
    signal, sl = sm.tick(mt5, 'XAUUSD')
    assert signal == 'NONE'
    assert sl is None


# ---------- State persistence ----------

def test_state_saved_to_file_after_crossover(tmp_path):
    """After SCANNING→ARMED transition, state file contains ARMED state."""
    f = str(tmp_path / "state.json")
    from signal_generator import SignalStateMachine
    sm = SignalStateMachine(state_file=f)
    ind = make_indicators(trend='BULLISH', slope=1.5,
                          prev_ema14=2009.0, curr_ema14=2012.0,
                          prev_ema24=2010.0, curr_ema24=2011.0)
    with patch.object(sm, '_get_indicators', return_value=ind):
        sm.tick(MagicMock(), 'XAUUSD')
    with open(f) as fp:
        saved = json.load(fp)
    assert saved['phase'] == 'ARMED'
    assert saved['direction'] == 'BUY'


def test_state_loaded_from_file_on_init(tmp_path):
    """State machine loads existing state from file on init."""
    f = str(tmp_path / "state.json")
    armed_state = {
        'phase': 'ARMED', 'direction': 'SELL',
        'pullback_count': 0, 'pullback_high': None, 'pullback_low': None,
        'breakout_level': None, 'armed_candles_elapsed': 2, 'window_candles_elapsed': 0,
    }
    with open(f, 'w') as fp:
        json.dump(armed_state, fp)
    from signal_generator import SignalStateMachine
    sm = SignalStateMachine(state_file=f)
    assert sm._state['phase'] == 'ARMED'
    assert sm._state['direction'] == 'SELL'
    assert sm._state['armed_candles_elapsed'] == 2


def test_corrupted_state_file_falls_back_to_scanning(tmp_path):
    """Corrupted state.json → falls back to SCANNING phase."""
    f = str(tmp_path / "state.json")
    with open(f, 'w') as fp:
        fp.write("not valid json {{{")
    from signal_generator import SignalStateMachine
    sm = SignalStateMachine(state_file=f)
    assert sm._state['phase'] == 'SCANNING'


def test_entry_resets_phase_to_scanning(tmp_path):
    """After ENTRY (BUY signal returned), phase resets to SCANNING."""
    state = {
        'phase': 'WINDOW_OPEN', 'direction': 'BUY',
        'pullback_count': 1, 'pullback_high': 2013.0, 'pullback_low': 2010.0,
        'breakout_level': 2013.0, 'armed_candles_elapsed': 1, 'window_candles_elapsed': 0,
    }
    sm = make_sm(tmp_path, initial_state=state)
    ind = make_indicators(trend='BULLISH', price=2015.0, atr_current=5.0)
    signal, _ = tick_with(sm, ind)
    assert signal == 'BUY'
    assert sm._state['phase'] == 'SCANNING'
