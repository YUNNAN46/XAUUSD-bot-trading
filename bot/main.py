import asyncio
import logging
from datetime import datetime
import pytz
import config
from logger import setup_logger
from mt5_connector import MT5Connector
from signal_watcher import SignalWatcher
from telegram_alert import TelegramAlert

setup_logger()
logger = logging.getLogger(__name__)
WIB = pytz.timezone("Asia/Jakarta")


class TradingBot:
    def __init__(self):
        self.mt5 = MT5Connector()
        self.telegram = TelegramAlert()
        self.watcher = SignalWatcher(
            mt5=self.mt5,
            on_new_trade=self._on_new_trade,
            on_trade_closed=self._on_trade_closed,
            on_alert=self._on_alert,
        )
        self._running = False
        self._daily_profits: list[float] = []
        self._daily_profit_total: float = 0.0

    def _on_new_trade(self, position):
        self.telegram.send_sync(self.telegram.format_trade_open(position))

    def _on_trade_closed(self, ticket: int, profit: float):
        balance = self.mt5.get_balance()
        self.telegram.send_sync(self.telegram.format_trade_close(ticket, profit, balance))
        self._daily_profits.append(profit)
        self._daily_profit_total += profit

    def _on_alert(self, message: str):
        self.telegram.send_sync(message)

    def _get_status(self) -> str:
        balance = self.mt5.get_balance()
        equity = self.mt5.get_equity()
        status = "⏸ Pause" if self.watcher.is_paused else "▶️ Aktif"
        n_pos = len(self.mt5.get_positions(config.SYMBOL))
        return (
            f"Status: {status}\n"
            f"Balance: {balance:.2f} USD\n"
            f"Equity: {equity:.2f} USD\n"
            f"Open Trades: {n_pos}\n"
        )

    def _get_trades_text(self) -> str:
        positions = self.mt5.get_positions(config.SYMBOL)
        if not positions:
            return "Tidak ada trade terbuka"
        lines = ["<b>Trade Terbuka:</b>"]
        for p in positions:
            direction = "BUY" if p.type == 0 else "SELL"
            lines.append(f"#{p.ticket} {direction} {p.volume}lot @ {p.price_open:.2f} | P&L: {p.profit:.2f}")
        return "\n".join(lines)

    def _get_laporan(self) -> str:
        wins = sum(1 for p in self._daily_profits if p > 0)
        return self.telegram.format_daily_report(
            total_trades=len(self._daily_profits),
            win_trades=wins,
            total_profit=self._daily_profit_total,
            balance=self.mt5.get_balance(),
        )

    def _reset_daily(self):
        self._daily_profits = []
        self._daily_profit_total = 0.0
        self.watcher._day_start_balance = self.mt5.get_balance()
        if self.watcher.is_paused:
            self.watcher.resume()
            self.telegram.send_sync("🌅 Hari baru — bot dilanjutkan otomatis")

    async def run(self):
        logger.info("Bot starting...")
        if not self.mt5.connect():
            logger.error("Cannot connect to MT5. Exiting.")
            return

        self.telegram.set_callbacks(
            get_status=self._get_status,
            pause=self.watcher.pause,
            resume=self.watcher.resume,
            get_trades=self._get_trades_text,
            get_laporan=self._get_laporan,
        )

        self.watcher.initialize()
        await self.telegram.start_polling()
        await self.telegram.send(f"🤖 Bot XAU/USD aktif! Balance: {self.mt5.get_balance():.2f} USD")

        self._running = True
        today = datetime.now(WIB).date()
        last_report_date = None

        try:
            while self._running:
                now = datetime.now(WIB)

                if now.date() != today:
                    self._reset_daily()
                    today = now.date()

                if now.hour == 23 and now.minute == 59 and last_report_date != now.date():
                    await self.telegram.send(self._get_laporan())
                    last_report_date = now.date()

                self.watcher.tick()
                await asyncio.sleep(config.POLL_INTERVAL_SECONDS)

        except asyncio.CancelledError:
            pass
        finally:
            await self.telegram.send("🔴 Bot berhenti.")
            await self.telegram.stop()
            self.mt5.disconnect()


if __name__ == "__main__":
    bot = TradingBot()
    asyncio.run(bot.run())
