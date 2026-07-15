"""Statistik hasil backtest + simulasi akun (ideal 1% vs riil $100 MIN_LOT)."""
from collections import Counter

# Spesifikasi kontrak XAUUSD standar: 1 lot = 100 oz, point = 0.01 → $1/point/lot
POINT = 0.01
TICK_VALUE = 1.0
MIN_LOT = 0.01
MAX_LOT = 0.50


def trade_stats(trades) -> dict:
    rs = [t.r_multiple for t in trades]
    n = len(rs)
    if n == 0:
        return {"n": 0, "winrate": 0.0, "profit_factor": 0.0, "expectancy_r": 0.0,
                "avg_win_r": 0.0, "avg_loss_r": 0.0}
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    return {
        "n": n,
        "winrate": 100.0 * len(wins) / n,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else float("inf"),
        "expectancy_r": sum(rs) / n,
        "avg_win_r": (gross_win / len(wins)) if wins else 0.0,
        "avg_loss_r": (-gross_loss / len(losses)) if losses else 0.0,
    }


def _sorted_by_exit(trades):
    return sorted(trades, key=lambda t: t.exit_time)


def equity_ideal(trades, start: float = 10000.0, risk_pct: float = 1.0) -> list[float]:
    """Compounding risk_pct% per trade dengan lot fraksional sempurna."""
    eq = [start]
    for t in _sorted_by_exit(trades):
        eq.append(eq[-1] * (1.0 + risk_pct / 100.0 * t.r_multiple))
    return eq


def equity_real(trades, start: float = 100.0, risk_pct: float = 1.0) -> list[float]:
    """Replikasi bot/money_management.calculate_lot_size: floor ke MIN_LOT.
    Berhenti jika balance <= 0 (akun habis)."""
    eq = [start]
    for t in _sorted_by_exit(trades):
        balance = eq[-1]
        sl_points = round(t.risk / POINT)
        risk_usd = balance * risk_pct / 100.0
        lot = round(risk_usd / (sl_points * TICK_VALUE), 2)
        lot = max(MIN_LOT, min(MAX_LOT, lot))
        pnl = t.r_multiple * sl_points * TICK_VALUE * lot
        balance = balance + pnl
        eq.append(round(balance, 2))
        if balance <= 0:
            break
    return eq


def max_drawdown_pct(equity) -> float:
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0:
            max_dd = max(max_dd, (peak - v) / peak * 100.0)
    return max_dd


def status_counts(day_results) -> Counter:
    return Counter(d.status for d in day_results)


def monthly_r(trades) -> dict:
    """{'YYYY-MM': total R} berdasarkan waktu exit."""
    out: dict[str, float] = {}
    for t in _sorted_by_exit(trades):
        key = t.exit_time.strftime("%Y-%m")
        out[key] = round(out.get(key, 0.0) + t.r_multiple, 4)
    return out
