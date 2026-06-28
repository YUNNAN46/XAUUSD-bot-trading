import logging
import time as time_module
from dataclasses import dataclass
from datetime import datetime, time
from typing import Callable
import pytz
import config
from money_management import is_drawdown_limit_reached, calculate_lot_size
from trade_filter import can_open_trade, is_active_trading_hour
from signal_generator import LondonBreakoutStrategy

logger = logging.getLogger(__name__)
WIB = pytz.timezone("Asia/Jakarta")


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
        self.on_new_trade   = on_new_trade   or (lambda p: None)
        self.on_trade_closed = on_trade_closed or (lambda ticket, profit: None)
        self.on_alert       = on_alert       or (lambda msg: None)
        self._known_tickets:      set[int]        = set()
        self._last_known_profits: dict[int, float] = {}
        self._paused:      bool  = False
        self._peak_balance: float = 0.0
        self._day_start_balance: float = 0.0
        self._tick_count:  int   = 0
        self._in_active_hours:   bool = False
        self._algo_trading_disabled: bool = False
        self._strategy:  LondonBreakoutStrategy = LondonBreakoutStrategy()
        self._london_state:         str       = 'IDLE'   # IDLE|COLLECTING|ORDERS_SET|EXPIRED
        self._pending_buy_ticket:   int | None = None
        self._pending_sell_ticket:  int | None = None
        self._managed_trades: dict[int, dict] = {}

    def initialize(self):
        balance = self.mt5.get_balance()
        self._peak_balance       = balance
        self._day_start_balance  = balance
        positions = self.mt5.get_positions(config.SYMBOL)
        self._known_tickets      = {p.ticket for p in positions}
        self._last_known_profits = {p.ticket: p.profit for p in positions}
        logger.info(f"Watcher init: balance={balance}, positions={len(self._known_tickets)}")
        if not self.mt5.is_algo_trading_enabled():
            self._algo_trading_disabled = True
            logger.warning("AutoTrading disabled in MT5 terminal at startup")
            self.on_alert(
                "⚠️ <b>AutoTrading MT5 nonaktif!</b>\n"
                "Buka VNC terminal MT5 → klik tombol 'Algo Trading' (hijau di toolbar).\n"
                "Bot tidak bisa buka order sampai diaktifkan."
            )

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
        if balance <= 0:
            return False
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
        if balance <= 0:
            return False
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

        # Position management runs regardless of drawdown/pause state
        current_positions = self.mt5.get_positions(config.SYMBOL)
        current_tickets   = {p.ticket for p in current_positions}
        position_profits  = {p.ticket: p.profit for p in current_positions}

        closed_tickets = self._known_tickets - current_tickets
        for ticket in closed_tickets:
            profit = self._last_known_profits.get(ticket, 0.0)
            logger.info(f"Position {ticket} closed, profit={profit:.2f}")
            self.on_trade_closed(ticket, profit)
            self._managed_trades.pop(ticket, None)

        new_tickets = current_tickets - self._known_tickets
        for ticket in new_tickets:
            pos = next((p for p in current_positions if p.ticket == ticket), None)
            if pos:
                self._on_position_opened(pos)

        self._check_tp1(current_positions)

        self._known_tickets      = current_tickets
        self._last_known_profits = position_profits

        if self.check_drawdown():
            return
        if self.check_daily_loss():
            return

        now = datetime.now(WIB)

        active_now = is_active_trading_hour(now)
        if active_now and not self._in_active_hours:
            self._in_active_hours = True
            self.on_alert("🟢 Window London Breakout dimulai — bot aktif memantau")
        elif not active_now and self._in_active_hours:
            self._in_active_hours = False
            self.on_alert("🔴 Window London Breakout selesai — bot standby")

        if not self._paused:
            self._update_london_breakout(now)

        self._tick_count += 1
        if self._tick_count % 150 == 0:
            algo_on = self.mt5.is_algo_trading_enabled()
            if not algo_on and not self._algo_trading_disabled:
                self._algo_trading_disabled = True
                self.on_alert(
                    "⚠️ <b>AutoTrading MT5 nonaktif!</b>\n"
                    "Buka VNC terminal MT5 → klik tombol 'Algo Trading' (hijau di toolbar).\n"
                    "Bot tidak bisa buka order sampai diaktifkan."
                )
            elif algo_on and self._algo_trading_disabled:
                self._algo_trading_disabled = False
                self.on_alert("✅ AutoTrading MT5 aktif kembali — bot siap buka order.")
        if self._tick_count % 60 == 0:
            balance = self.mt5.get_balance()
            logger.info(
                f"Heartbeat: balance={balance:.2f}, positions={len(current_positions)}, "
                f"paused={self._paused}, london_state={self._london_state}"
            )

    def reset_day(self, balance: float):
        self._day_start_balance = balance
        if balance > self._peak_balance:
            self._peak_balance = balance
        self._strategy.reset()
        self._london_state        = 'IDLE'
        self._pending_buy_ticket  = None
        self._pending_sell_ticket = None
        logger.info("Daily reset: London Breakout state cleared")

    # ------------------------------------------------------------------
    # London Breakout time-based state machine
    # ------------------------------------------------------------------

    def _update_london_breakout(self, now: datetime):
        current_time = now.time()
        asian_start  = time(*config.ASIAN_RANGE_START)
        asian_end    = time(*config.ASIAN_RANGE_END)
        place_time   = time(*config.ORDERS_PLACE_TIME)
        expiry_time  = time(*config.ORDERS_EXPIRY_TIME)

        # COLLECTING: accumulate Asian range from live tick
        if asian_start <= current_time < asian_end:
            if self._london_state == 'IDLE':
                self._london_state = 'COLLECTING'
            tick = self.mt5.get_tick(config.SYMBOL)
            if tick:
                self._strategy.update_asian_range(float(tick.ask), float(tick.bid))
            return

        # ORDER PLACEMENT: once when entering the placement window
        if place_time <= current_time < expiry_time and self._london_state == 'COLLECTING':
            self._place_london_orders(now)
            return

        # OCO MONITORING: check if one order triggered and cancel the other
        elif place_time <= current_time < expiry_time and self._london_state == 'ORDERS_SET':
            self._check_oco()
            return

        # EXPIRY: cancel any remaining pending orders at 17:00 WIB
        if current_time >= expiry_time and self._london_state == 'ORDERS_SET':
            self._expire_pending_orders()

    def _place_london_orders(self, now: datetime):
        orders = self._strategy.get_pending_orders()
        if orders is None:
            r = self._strategy.range_size
            if r is None:
                label = 'tidak ada data'
            elif r < config.RANGE_MIN_USD:
                label = f'{r:.2f} USD — terlalu sempit'
            else:
                label = f'{r:.2f} USD — terlalu lebar'
            self.on_alert(f"⚠️ Skip London Breakout hari ini — range Asian tidak valid ({label})")
            self._london_state = 'EXPIRED'
            return

        balance       = self.mt5.get_balance()
        daily_loss_pct = max(0.0, (self._day_start_balance - balance) / max(self._day_start_balance, 1) * 100)
        spread        = self.mt5.get_spread(config.SYMBOL)
        open_count    = len(self.mt5.get_positions(config.SYMBOL))

        allowed, reason = can_open_trade(open_count, daily_loss_pct, spread, now)
        if not allowed:
            self.on_alert(f"⚠️ London Breakout skip — {reason}")
            self._london_state = 'EXPIRED'
            return

        if not self.mt5.is_algo_trading_enabled():
            self.on_alert("⚠️ AutoTrading nonaktif — tidak bisa pasang pending orders")
            self._london_state = 'EXPIRED'
            return

        symbol_info = self.mt5.get_symbol_info(config.SYMBOL)
        if not symbol_info or not getattr(symbol_info, 'trade_tick_value', None):
            self._london_state = 'EXPIRED'
            self.on_alert("🚨 Gagal ambil info symbol — pending orders tidak dipasang hari ini")
            return

        point = getattr(symbol_info, 'point', 0.01) or 0.01

        sl_dist_buy  = abs(orders['buy_price']  - orders['sl_buy'])
        sl_dist_sell = abs(orders['sell_price'] - orders['sl_sell'])
        sl_pts_buy   = round(sl_dist_buy  / point)
        sl_pts_sell  = round(sl_dist_sell / point)
        lot_buy  = calculate_lot_size(balance, sl_pts_buy,  symbol_info.trade_tick_value)
        lot_sell = calculate_lot_size(balance, sl_pts_sell, symbol_info.trade_tick_value)

        buy_ticket  = self.mt5.place_stop_order(
            config.SYMBOL, 0, lot_buy,
            orders['buy_price'], orders['sl_buy'], orders['tp_buy'],
        )
        sell_ticket = self.mt5.place_stop_order(
            config.SYMBOL, 1, lot_sell,
            orders['sell_price'], orders['sl_sell'], orders['tp_sell'],
        )

        if buy_ticket and sell_ticket:
            self._pending_buy_ticket  = buy_ticket
            self._pending_sell_ticket = sell_ticket
            self._london_state = 'ORDERS_SET'
            self.on_alert(
                f"📊 <b>Asian Range Terkunci — XAUUSD</b>\n"
                f"High: {self._strategy.asian_high:.2f} | Low: {self._strategy.asian_low:.2f}\n"
                f"Range: {orders['range_size']:.2f} USD\n"
                f"Buy Stop:  {orders['buy_price']:.2f}  | SL: {orders['sl_buy']:.2f}  | TP: {orders['tp_buy']:.2f}\n"
                f"Sell Stop: {orders['sell_price']:.2f} | SL: {orders['sl_sell']:.2f} | TP: {orders['tp_sell']:.2f}\n"
                f"Orders dipasang — menunggu breakout sampai 17:00 WIB"
            )
        else:
            if buy_ticket:
                self.mt5.cancel_order(buy_ticket)
            if sell_ticket:
                self.mt5.cancel_order(sell_ticket)
            self._london_state = 'EXPIRED'
            retcode, comment = self.mt5.last_order_error or (None, '')
            self.on_alert(f"🚨 Gagal pasang pending orders: retcode={retcode}, {comment}")

    def _check_oco(self):
        pending_tickets = {o.ticket for o in self.mt5.get_pending_orders(config.SYMBOL)}
        buy_pending  = self._pending_buy_ticket  in pending_tickets if self._pending_buy_ticket  else False
        sell_pending = self._pending_sell_ticket in pending_tickets if self._pending_sell_ticket else False

        if not buy_pending and sell_pending:
            self.mt5.cancel_order(self._pending_sell_ticket)
            self._london_state = 'EXPIRED'
            logger.info(f"OCO: Buy triggered, cancelled Sell Stop {self._pending_sell_ticket}")

        elif not sell_pending and buy_pending:
            self.mt5.cancel_order(self._pending_buy_ticket)
            self._london_state = 'EXPIRED'
            logger.info(f"OCO: Sell triggered, cancelled Buy Stop {self._pending_buy_ticket}")

    def _expire_pending_orders(self):
        cancelled = 0
        for ticket in [self._pending_buy_ticket, self._pending_sell_ticket]:
            if ticket and self.mt5.cancel_order(ticket):
                cancelled += 1
        self._london_state = 'EXPIRED'
        self.on_alert(
            f"⏱ <b>London Breakout Expired — XAUUSD</b>\n"
            f"Tidak ada breakout dalam window 14:50–17:00 WIB.\n"
            f"{cancelled} pending order dihapus."
        )

    # ------------------------------------------------------------------
    # Position management (TP1 / breakeven)
    # ------------------------------------------------------------------

    def _on_position_opened(self, pos):
        direction   = "BUY" if pos.type == 0 else "SELL"
        sl_distance = abs(pos.price_open - pos.sl) if getattr(pos, 'sl', 0) else 0
        tp1_price   = round(
            pos.price_open + sl_distance * config.TP1_RR if pos.type == 0
            else pos.price_open - sl_distance * config.TP1_RR, 2
        ) if sl_distance > 0 else 0
        half_vol = round(pos.volume / 2, 2)
        self._managed_trades[pos.ticket] = {
            'tp1':      tp1_price,
            'entry':    pos.price_open,
            'type':     pos.type,
            'half_vol': half_vol,
            'tp1_hit':  False,
        }
        self.on_new_trade(TradeInfo(
            ticket=pos.ticket, type=pos.type, volume=pos.volume,
            price_open=pos.price_open, sl=pos.sl, tp=pos.tp,
        ))
        logger.info(f"New position: ticket={pos.ticket} {direction} @ {pos.price_open:.2f} SL={pos.sl:.2f} TP={pos.tp:.2f}")

    def _check_tp1(self, positions):
        for pos in positions:
            info = self._managed_trades.get(pos.ticket)
            if not info or info['tp1_hit'] or not info['tp1']:
                continue

            tp1 = info['tp1']
            tp1_reached = (
                (info['type'] == 0 and pos.price_current >= tp1) or
                (info['type'] == 1 and pos.price_current <= tp1)
            )
            if not tp1_reached:
                continue

            half_vol  = info['half_vol']
            direction = "BUY" if info['type'] == 0 else "SELL"

            if half_vol < config.MIN_LOT:
                info['tp1_hit'] = True
                logger.info(f"TP1 reached {pos.ticket} but volume too small — keeping full position")
                continue

            success = self.mt5.partial_close_position(pos, half_vol)
            if success:
                info['tp1_hit'] = True
                self.mt5.modify_position_sl(pos, info['entry'])
                logger.info(f"TP1 hit {pos.ticket}: closed {half_vol}lot, SL → breakeven {info['entry']:.2f}")
                self.on_alert(
                    f"🎯 TP1 hit #{pos.ticket} ({direction})\n"
                    f"Closed {half_vol}lot — profit secured\n"
                    f"SL moved to breakeven {info['entry']:.2f}\n"
                    f"Remaining {half_vol}lot running to TP2"
                )
