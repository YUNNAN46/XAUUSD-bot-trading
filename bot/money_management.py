import config


def calculate_lot_size(balance: float, sl_points: int, tick_value_per_lot: float) -> float:
    if sl_points <= 0 or tick_value_per_lot <= 0:
        return config.MIN_LOT
    risk_usd = balance * config.RISK_PER_TRADE / 100
    lot = risk_usd / (sl_points * tick_value_per_lot)
    lot = round(lot, 2)
    return max(config.MIN_LOT, min(config.MAX_LOT, lot))


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
