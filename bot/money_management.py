import math

import config


def calculate_lot_size(balance: float, sl_points: int, tick_value_per_lot: float) -> float:
    """Hitung lot berdasarkan RISK_PER_TRADE. Return 0.0 = jangan trade
    (input tidak valid, atau lot < MIN_LOT — floor ke MIN_LOT akan
    membuat risiko riil melebihi RISK_PER_TRADE)."""
    if sl_points <= 0 or tick_value_per_lot <= 0:
        return 0.0
    risk_usd = balance * config.RISK_PER_TRADE / 100
    lot = risk_usd / (sl_points * tick_value_per_lot)
    # Bulatkan ke BAWAH (2 desimal) — risiko riil tidak boleh melebihi budget
    lot = math.floor(lot * 100 + 1e-9) / 100
    if lot < config.MIN_LOT:
        return 0.0
    return min(config.MAX_LOT, lot)


def calculate_tp_price(entry_price: float, sl_price: float, order_type: int) -> float:
    if order_type not in (0, 1):
        raise ValueError(f"order_type harus 0 (BUY) atau 1 (SELL), dapat: {order_type}")
    sl_distance = abs(entry_price - sl_price)
    if sl_distance == 0:
        raise ValueError("entry_price dan sl_price tidak boleh sama")
    tp_distance = sl_distance * config.TARGET_RR
    if order_type == 0:  # BUY
        return round(entry_price + tp_distance, 2)
    return round(entry_price - tp_distance, 2)


def is_daily_loss_limit_reached(daily_loss_pct: float) -> bool:
    return daily_loss_pct >= config.MAX_LOSS_PER_DAY


def is_drawdown_limit_reached(current_balance: float, peak_balance: float) -> bool:
    if peak_balance <= 0:
        return False
    drawdown_pct = (peak_balance - current_balance) / peak_balance * 100
    return drawdown_pct >= config.MAX_DRAWDOWN
