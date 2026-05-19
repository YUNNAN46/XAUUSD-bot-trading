from datetime import datetime, time
import pytz
import config
from money_management import is_daily_loss_limit_reached

WIB = pytz.timezone("Asia/Jakarta")


def is_active_trading_hour(now: datetime = None) -> bool:
    if now is None:
        now = datetime.now(WIB)
    elif now.tzinfo is None:
        now = WIB.localize(now)
    t = now.time()
    for sh, sm, eh, em in config.ACTIVE_HOURS:
        if time(sh, sm) <= t <= time(eh, em):
            return True
    return False


def is_spread_acceptable(spread_points: int) -> bool:
    return spread_points <= config.SPREAD_FILTER


def is_trade_valid(position) -> tuple[bool, str]:
    sl = getattr(position, "sl", 0)
    if not sl or sl < 0:
        return False, "SL tidak terpasang atau tidak valid"
    return True, ""


def can_open_trade(
    open_positions_count: int,
    daily_loss_pct: float,
    spread_points: int,
    now: datetime = None,
) -> tuple[bool, str]:
    if not is_active_trading_hour(now):
        return False, "Di luar jam trading aktif"
    if open_positions_count >= config.MAX_OPEN_TRADES:
        return False, f"Sudah ada {open_positions_count} trade terbuka (max {config.MAX_OPEN_TRADES})"
    if not is_spread_acceptable(spread_points):
        return False, f"Spread {spread_points} pts terlalu lebar (max {config.SPREAD_FILTER})"
    if is_daily_loss_limit_reached(daily_loss_pct):
        return False, f"Loss harian {daily_loss_pct:.1f}% sudah tercapai (max {config.MAX_LOSS_PER_DAY}%)"
    return True, ""
