from datetime import datetime
from backtest.metrics import (trade_stats, equity_ideal, equity_real,
                              max_drawdown_pct, status_counts, monthly_r)
from backtest.simulator import Trade, DayResult


def _trade(r, risk=10.0, when="2025-03-04 15:00"):
    t = Trade("buy", datetime.fromisoformat(when), 2000.0, 2000.0 - risk,
              None, 2000.0 + risk * 1.5, risk)
    t.exit_time = t.entry_time
    t.r_multiple = r
    return t


def test_trade_stats_empty():
    s = trade_stats([])
    assert s == {"n": 0, "winrate": 0.0, "profit_factor": 0.0, "expectancy_r": 0.0,
                 "avg_win_r": 0.0, "avg_loss_r": 0.0}


def test_trade_stats():
    trades = [_trade(1.5), _trade(-1.0), _trade(1.5), _trade(-1.0)]
    s = trade_stats(trades)
    assert s["n"] == 4
    assert abs(s["winrate"] - 50.0) < 1e-9
    assert abs(s["profit_factor"] - 1.5) < 1e-9
    assert abs(s["expectancy_r"] - 0.25) < 1e-9


def test_equity_ideal_compounds_one_percent():
    eq = equity_ideal([_trade(2.0), _trade(-1.0)], start=10000.0, risk_pct=1.0)
    assert abs(eq[-1] - 10000.0 * 1.02 * 0.99) < 1e-6


def test_equity_real_min_lot_floor_over_risks():
    # balance 100, risk 1% = $1. SL $15 = 1500 points → lot ideal 0.0007 → floor 0.01
    # loss 1R = 1500 pts × $1 × 0.01 lot = $15 (15% akun, bukan 1%)
    eq = equity_real([_trade(-1.0, risk=15.0)], start=100.0)
    assert abs(eq[-1] - 85.0) < 1e-9


def test_equity_real_blowup_stops():
    trades = [_trade(-1.0, risk=30.0) for _ in range(5)]  # $30/trade
    eq = equity_real(trades, start=100.0)
    assert eq[-1] <= 10.0  # akun praktis habis
    assert len(eq) <= len(trades) + 1


def test_max_drawdown():
    assert abs(max_drawdown_pct([100, 120, 90, 130]) - 25.0) < 1e-9


def test_status_counts():
    days = [DayResult("d1", "traded"), DayResult("d2", "no_breakout"),
            DayResult("d3", "traded")]
    c = status_counts(days)
    assert c["traded"] == 2 and c["no_breakout"] == 1


def test_monthly_r():
    trades = [
        _trade(1.5, when="2025-03-04 15:00"),
        _trade(-1.0, when="2025-03-20 15:00"),
        _trade(2.0, when="2025-04-10 15:00"),
    ]
    result = monthly_r(trades)
    assert result == {"2025-03": 0.5, "2025-04": 2.0}
