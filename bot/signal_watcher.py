import logging
import time as time_module
from dataclasses import dataclass
from datetime import datetime, time
from typing import Callable
import pytz
import config
from money_management import is_drawdown_limit_reached, calculate_lot_size, position_risk_pct
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
        _raw_alert = on_alert or (lambda msg: None)

        def _logging_alert(msg):
            # Catat alert ke log (alasan skip London, dll) lalu teruskan ke Telegram.
            logger.info("ALERT: %s", msg)
            _raw_alert(msg)

        self.on_alert       = _logging_alert
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

        # Recover London Breakout state after restart
        now = datetime.now(WIB)
        current_time = now.time()
        asian_start = time(*config.ASIAN_RANGE_START)
        asian_end   = time(*config.ASIAN_RANGE_END)
        place_time  = time(*config.ORDERS_PLACE_TIME)
        expiry_time = time(*config.ORDERS_EXPIRY_TIME)
        if asian_start <= current_time < asian_end:
            self._london_state = 'COLLECTING'
            logger.info("Recovered COLLECTING state after restart")
        elif asian_end <= current_time < place_time:
            # Data Asian range hanya hidup di memori proses lama — restart di
            # jendela 14:00-14:50 WIB berarti range hari ini hilang dan tidak
            # bisa direkam ulang, jadi hari ini pasti tanpa order.
            self._london_state = 'EXPIRED'
            logger.warning("Restart between 14:00-14:50 WIB — Asian range lost, skipping today")
            self.on_alert(
                "⚠️ <b>Restart di jendela 14:00–14:50 WIB</b>\n"
                "Data Asian range hari ini hilang — London Breakout hari ini di-skip.\n"
                "Lain kali restart bot sebelum 14:00 atau setelah 17:00 WIB."
            )
        elif place_time <= current_time < expiry_time:
            pending = self.mt5.get_pending_orders(config.SYMBOL)
            buy_stops  = [o for o in pending if getattr(o, 'type', -1) == 4]
            sell_stops = [o for o in pending if getattr(o, 'type', -1) == 5]
            if buy_stops and sell_stops:
                self._pending_buy_ticket  = buy_stops[0].ticket
                self._pending_sell_ticket = sell_stops[0].ticket
                self._london_state = 'ORDERS_SET'
                logger.info(f"Recovered ORDERS_SET: buy={self._pending_buy_ticket}, sell={self._pending_sell_ticket}")
                self.on_alert(
                    f"♻️ Pending orders dipulihkan setelah restart\n"
                    f"Buy Stop #{self._pending_buy_ticket} | Sell Stop #{self._pending_sell_ticket}"
                )

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
        # Saat paused kondisi limit tetap true tiap tick — tanpa guard ini
        # alert terkirim ulang tiap 2 detik (flood Telegram).
        if self._paused:
            return False
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
        if self._paused:
            return False
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

        # Guard akun kecil: MIN_LOT bisa memaksa risiko jauh di atas RISK_PER_TRADE.
        # Jika risiko aktual melebihi MAX_RISK_PER_TRADE, skip — jangan trading oversized.
        risk_buy  = position_risk_pct(balance, lot_buy,  sl_pts_buy,  symbol_info.trade_tick_value)
        risk_sell = position_risk_pct(balance, lot_sell, sl_pts_sell, symbol_info.trade_tick_value)
        worst_risk = max(risk_buy, risk_sell)
        if worst_risk > config.MAX_RISK_PER_TRADE:
            self._london_state = 'EXPIRED'
            self.on_alert(
                f"⚠️ <b>Skip London Breakout — akun terlalu kecil untuk range ini</b>\n"
                f"Range {orders['range_size']:.2f} USD → risiko {worst_risk:.1f}% "
                f"(lot {lot_buy}) melebihi batas {config.MAX_RISK_PER_TRADE:.1f}%.\n"
                f"Order tidak dipasang. Akan otomatis lolos saat balance bertumbuh."
            )
            return

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

        if not buy_pending and not sell_pending:
            # Both stops filled before OCO could cancel one (fast whipsaw) —
            # we now hold opposite positions (hedged double-risk). Nothing left
            # to cancel; warn the operator so they can resolve it manually.
            self._london_state = 'EXPIRED'
            logger.warning("OCO: both Buy & Sell Stop triggered — hedged double position!")
            self.on_alert(
                "🚨 <b>Whipsaw — kedua order London Breakout kena!</b>\n"
                "Posisi BUY & SELL terbuka bersamaan (hedged double-risk).\n"
                "Cek terminal MT5 dan tutup salah satu posisi secara manual."
            )

        elif not buy_pending and sell_pending:
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
        direction = "BUY" if pos.type == 0 else "SELL"
        tp2       = getattr(pos, 'tp', 0) or 0
        # TP1 = midpoint between entry and TP2 — always in sync with TP2
        tp1_price = round((pos.price_open + tp2) / 2, 2) if tp2 > 0 else 0
        # Floor dalam satuan MIN_LOT: round() biasa membulatkan 0.005 → 0.01
        # sehingga posisi 0.01 lot tertutup 100% di TP1, bukan di-skip.
        half_vol  = round(int(round(pos.volume / config.MIN_LOT)) // 2 * config.MIN_LOT, 2)
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
                self.mt5.modify_position_sl(pos, info['entry'])
                logger.info(
                    f"TP1 reached {pos.ticket} but volume too small for partial close — "
                    f"keeping full position, SL → breakeven {info['entry']:.2f}"
                )
                self.on_alert(
                    f"🎯 TP1 hit #{pos.ticket} ({direction})\n"
                    f"Entry: {info['entry']:.2f} → TP1: {pos.price_current:.2f}\n"
                    f"Partial close di-skip (volume terlalu kecil) — "
                    f"SL → breakeven {info['entry']:.2f}, posisi penuh menuju TP2"
                )
                continue

            success = self.mt5.partial_close_position(pos, half_vol)
            if success:
                info['tp1_hit'] = True
                self.mt5.modify_position_sl(pos, info['entry'])
                logger.info(f"TP1 hit {pos.ticket}: closed {half_vol}lot @ {pos.price_current:.2f}, SL → breakeven {info['entry']:.2f}")
                tp2 = getattr(pos, 'tp', 0) or 0
                self.on_alert(
                    f"🎯 TP1 hit #{pos.ticket} ({direction})\n"
                    f"Entry: {info['entry']:.2f} → TP1: {pos.price_current:.2f}\n"
                    f"Closed {half_vol}lot — SL → breakeven {info['entry']:.2f}\n"
                    f"Sisa {half_vol}lot menuju TP2 @ {tp2:.2f}"
                )
