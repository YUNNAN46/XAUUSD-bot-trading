import logging
from typing import Callable
import config
from money_management import is_drawdown_limit_reached, calculate_tp_price
from trade_filter import can_open_trade, is_trade_valid

logger = logging.getLogger(__name__)


class SignalWatcher:
    def __init__(self, mt5, on_new_trade: Callable = None, on_trade_closed: Callable = None, on_alert: Callable = None):
        self.mt5 = mt5
        self.on_new_trade = on_new_trade or (lambda p: None)
        self.on_trade_closed = on_trade_closed or (lambda ticket, profit: None)
        self.on_alert = on_alert or (lambda msg: None)
        self._known_tickets: set[int] = set()
        self._paused: bool = False
        self._peak_balance: float = 0.0
        self._day_start_balance: float = 0.0

    def initialize(self):
        balance = self.mt5.get_balance()
        self._peak_balance = balance
        self._day_start_balance = balance
        self._known_tickets = {p.ticket for p in self.mt5.get_positions(config.SYMBOL)}
        logger.info(f"Watcher init: balance={balance}, positions={len(self._known_tickets)}")

    @property
    def is_paused(self) -> bool:
        return self._paused

    def pause(self):
        self._paused = True
        logger.info("Bot paused")

    def resume(self):
        self._paused = False
        logger.info("Bot resumed")

    def check_drawdown(self) -> bool:
        balance = self.mt5.get_balance()
        if balance > self._peak_balance:
            self._peak_balance = balance
        if is_drawdown_limit_reached(balance, self._peak_balance):
            msg = f"DRAWDOWN LIMIT! Balance={balance:.2f}, Peak={self._peak_balance:.2f}"
            logger.critical(msg)
            self.on_alert(f"🚨 {msg} — Bot berhenti total!")
            self.pause()
            return True
        return False

    def check_daily_loss(self) -> bool:
        balance = self.mt5.get_balance()
        if self._day_start_balance <= 0:
            return False
        daily_loss_pct = (self._day_start_balance - balance) / self._day_start_balance * 100
        if daily_loss_pct >= config.MAX_LOSS_PER_DAY:
            self.on_alert(f"⚠️ Loss harian {daily_loss_pct:.1f}% tercapai — Bot pause sampai besok")
            self.pause()
            return True
        return False

    def tick(self):
        if not self.mt5.is_connected:
            self.on_alert("⚠️ Koneksi MT5 terputus!")
            return

        if self.check_drawdown():
            return

        if self.check_daily_loss():
            return

        current_positions = self.mt5.get_positions(config.SYMBOL)
        current_tickets = {p.ticket for p in current_positions}

        # Deteksi posisi yang ditutup
        closed_tickets = self._known_tickets - current_tickets
        for ticket in closed_tickets:
            logger.info(f"Position {ticket} closed")
            self.on_trade_closed(ticket, 0.0)

        # Deteksi posisi baru
        new_tickets = current_tickets - self._known_tickets
        current_open_count = len(current_tickets) - len(new_tickets)

        for position in current_positions:
            if position.ticket not in new_tickets:
                continue
            if self._paused:
                logger.info(f"Bot paused — closing {position.ticket}")
                self.mt5.close_position(position)
                continue
            self._handle_new_position(position, current_open_count)

        self._known_tickets = current_tickets

    def _handle_new_position(self, position, open_count: int):
        spread = self.mt5.get_spread(config.SYMBOL)
        balance = self.mt5.get_balance()
        daily_loss_pct = max(0.0, (self._day_start_balance - balance) / max(self._day_start_balance, 1) * 100)

        allowed, reason = can_open_trade(open_count, daily_loss_pct, spread)
        if not allowed:
            logger.info(f"Filter blocked {position.ticket}: {reason}")
            self.mt5.close_position(position)
            return

        valid, reason = is_trade_valid(position)
        if not valid:
            logger.info(f"Invalid trade {position.ticket}: {reason}")
            self.mt5.close_position(position)
            return

        new_tp = calculate_tp_price(position.price_open, position.sl, position.type)
        self.mt5.modify_position_tp(position, new_tp)
        logger.info(f"Position {position.ticket} accepted, TP -> {new_tp}")
        self.on_new_trade(position)
