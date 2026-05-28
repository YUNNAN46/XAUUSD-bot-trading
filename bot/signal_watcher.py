import logging
import time as time_module
from dataclasses import dataclass
from typing import Callable
import config
from money_management import (
    is_drawdown_limit_reached,
    calculate_lot_size,
    calculate_tp_price,
)
from trade_filter import can_open_trade, is_active_trading_hour
from signal_generator import SignalStateMachine

logger = logging.getLogger(__name__)

SIGNAL_COOLDOWN_SECONDS = 900  # 15 minutes — avoid re-entering same M15 candle


@dataclass
class TradeInfo:
    ticket: int
    type: int
    volume: float
    price_open: float
    sl: float
    tp: float


class SignalWatcher:
    def __init__(self, mt5, on_new_trade: Callable = None, on_trade_closed: Callable = None, on_alert: Callable = None):
        self.mt5 = mt5
        self.on_new_trade = on_new_trade or (lambda p: None)
        self.on_trade_closed = on_trade_closed or (lambda ticket, profit: None)
        self.on_alert = on_alert or (lambda msg: None)
        self._known_tickets: set[int] = set()
        self._last_known_profits: dict[int, float] = {}
        self._paused: bool = False
        self._peak_balance: float = 0.0
        self._day_start_balance: float = 0.0
        self._last_signal_time: float = 0.0
        self._tick_count: int = 0
        self._in_news_blackout: bool = False
        self._in_active_hours: bool = False
        self._state_machine: SignalStateMachine = SignalStateMachine()
        # Tracks TP1/breakeven state per open trade opened by this bot
        # {ticket: {'tp1': float, 'entry': float, 'type': int, 'half_vol': float, 'tp1_hit': bool}}
        self._managed_trades: dict[int, dict] = {}

    def initialize(self):
        balance = self.mt5.get_balance()
        self._peak_balance = balance
        self._day_start_balance = balance
        positions = self.mt5.get_positions(config.SYMBOL)
        self._known_tickets = {p.ticket for p in positions}
        self._last_known_profits = {p.ticket: p.profit for p in positions}
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

        # Notifikasi saat masuk/keluar jam trading aktif
        active_now = is_active_trading_hour()
        if active_now and not self._in_active_hours:
            self._in_active_hours = True
            self.on_alert("🟢 Sesi trading dimulai — bot aktif mencari sinyal")
        elif not active_now and self._in_active_hours:
            self._in_active_hours = False
            self.on_alert("🔴 Sesi trading selesai — bot standby hingga sesi berikutnya")

        current_positions = self.mt5.get_positions(config.SYMBOL)
        current_tickets = {p.ticket for p in current_positions}
        position_profits = {p.ticket: p.profit for p in current_positions}

        # Detect closed positions (SL/TP hit or manually closed)
        closed_tickets = self._known_tickets - current_tickets
        for ticket in closed_tickets:
            profit = self._last_known_profits.get(ticket, 0.0)
            logger.info(f"Position {ticket} closed, profit={profit:.2f}")
            self.on_trade_closed(ticket, profit)
            self._managed_trades.pop(ticket, None)

        # Monitor TP1 and move SL to breakeven for managed trades
        self._check_tp1(current_positions)

        if not self._paused:
            self._try_generate_signal(len(current_positions))

        self._known_tickets = current_tickets
        self._last_known_profits = position_profits

        self._tick_count += 1
        if self._tick_count % 60 == 0:  # heartbeat every ~5 minutes
            balance = self.mt5.get_balance()
            logger.info(f"Heartbeat: balance={balance:.2f}, positions={len(current_positions)}, paused={self._paused}")

    def reset_day(self, balance: float):
        self._day_start_balance = balance
        if balance > self._peak_balance:
            self._peak_balance = balance

    def _check_tp1(self, positions):
        """Partial close 50% at TP1 (TP1_RR from config) and move SL to breakeven."""
        for pos in positions:
            info = self._managed_trades.get(pos.ticket)
            if not info or info['tp1_hit']:
                continue

            tp1 = info['tp1']
            tp1_reached = (
                (info['type'] == 0 and pos.price_current >= tp1) or
                (info['type'] == 1 and pos.price_current <= tp1)
            )
            if not tp1_reached:
                continue

            half_vol = info['half_vol']
            direction = "BUY" if info['type'] == 0 else "SELL"

            # If half_vol is too small (position was minimum lot), skip partial — let TP2 close it
            if half_vol < config.MIN_LOT:
                info['tp1_hit'] = True
                logger.info(f"TP1 reached {pos.ticket} but volume too small to partial close — keeping full")
                return

            success = self.mt5.partial_close_position(pos, half_vol)
            if success:
                info['tp1_hit'] = True
                self.mt5.modify_position_sl(pos, info['entry'])
                logger.info(f"TP1 hit {pos.ticket}: closed {half_vol}lot, SL moved to breakeven {info['entry']:.2f}")
                self.on_alert(
                    f"🎯 TP1 hit #{pos.ticket} ({direction})\n"
                    f"Closed {half_vol}lot — profit secured\n"
                    f"SL moved to breakeven {info['entry']:.2f}\n"
                    f"Remaining {half_vol}lot running to TP2"
                )

    def _try_generate_signal(self, open_count: int):
        spread = self.mt5.get_spread(config.SYMBOL)
        balance = self.mt5.get_balance()
        daily_loss_pct = max(0.0, (self._day_start_balance - balance) / max(self._day_start_balance, 1) * 100)

        allowed, reason = can_open_trade(open_count, daily_loss_pct, spread)

        is_blackout_now = reason.startswith("Blackout berita:")
        if is_blackout_now and not self._in_news_blackout:
            self._in_news_blackout = True
            self.on_alert(f"📰 {reason}\nTrading diblokir sementara hingga berita berlalu.")
        elif self._in_news_blackout and not is_blackout_now:
            self._in_news_blackout = False
            self.on_alert("✅ Blackout berita selesai — bot melanjutkan trading")

        if not allowed:
            logger.debug(f"Trade blocked: {reason}")
            return

        # Cooldown: skip if last signal was within one M15 candle (15 min)
        if time_module.time() - self._last_signal_time < SIGNAL_COOLDOWN_SECONDS:
            return

        signal, sl_price = self._state_machine.tick(self.mt5, config.SYMBOL)
        logger.info(f"Signal: {signal}")

        if signal == 'NONE' or sl_price is None:
            return

        self._last_signal_time = time_module.time()

        tick = self.mt5.get_tick(config.SYMBOL)
        symbol_info = self.mt5.get_symbol_info(config.SYMBOL)
        if not tick or not symbol_info or not symbol_info.point:
            return

        entry_price = tick.ask if signal == 'BUY' else tick.bid
        order_type = 0 if signal == 'BUY' else 1
        sl_distance = abs(entry_price - sl_price)

        sl_points = round(sl_distance / symbol_info.point)
        lot = calculate_lot_size(balance, sl_points, symbol_info.trade_tick_value)

        # TP2: main take profit (uses TARGET_RR from config, e.g. 2.5x)
        tp2_price = calculate_tp_price(entry_price, sl_price, order_type)
        # TP1: partial close at TP1_RR, then move SL to breakeven
        tp1_price = round(
            entry_price + sl_distance * config.TP1_RR if order_type == 0
            else entry_price - sl_distance * config.TP1_RR, 2
        )
        # Half volume for partial close at TP1
        half_vol = max(config.MIN_LOT, round(lot / 2, 2))

        logger.info(
            f"Opening {signal}: lot={lot}, entry≈{entry_price:.2f}, "
            f"SL={sl_price:.2f}, TP1={tp1_price:.2f}, TP2={tp2_price:.2f}"
        )

        ticket = self.mt5.open_position(config.SYMBOL, order_type, lot, sl_price, tp2_price)
        if ticket:
            self._managed_trades[ticket] = {
                'tp1': tp1_price,
                'entry': entry_price,
                'type': order_type,
                'half_vol': half_vol,
                'tp1_hit': False,
            }
            self.on_new_trade(TradeInfo(
                ticket=ticket,
                type=order_type,
                volume=lot,
                price_open=entry_price,
                sl=sl_price,
                tp=tp2_price,
            ))
        else:
            logger.error(f"Failed to open {signal} order")
