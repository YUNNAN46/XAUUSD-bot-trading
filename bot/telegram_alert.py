import asyncio
import logging
from typing import Callable
import config

logger = logging.getLogger(__name__)


class TelegramAlert:
    def __init__(self, token: str = None, chat_id: str = None):
        self.token = token or config.TELEGRAM_TOKEN
        self.chat_id = chat_id or config.TELEGRAM_CHAT_ID
        self._bot = None
        self._app = None
        self._get_status: Callable = None
        self._pause: Callable = None
        self._resume: Callable = None
        self._get_trades: Callable = None
        self._get_laporan: Callable = None

    def set_callbacks(self, get_status=None, pause=None, resume=None, get_trades=None, get_laporan=None):
        self._get_status = get_status
        self._pause = pause
        self._resume = resume
        self._get_trades = get_trades
        self._get_laporan = get_laporan

    async def send(self, text: str):
        if not self._bot:
            logger.warning(f"[Telegram not connected] {text}")
            return
        try:
            await self._bot.send_message(chat_id=self.chat_id, text=text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Telegram send error: {e}")

    def send_sync(self, text: str):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(self.send(text), loop)
            else:
                loop.run_until_complete(self.send(text))
        except Exception as e:
            logger.error(f"send_sync error: {e}")

    def format_trade_open(self, position) -> str:
        direction = "BUY 📈" if position.type == 0 else "SELL 📉"
        sl_dist = abs(position.price_open - position.sl)
        tp1 = round(
            position.price_open + sl_dist if position.type == 0 else position.price_open - sl_dist, 2
        )
        return (
            f"<b>Trade Baru — {config.SYMBOL}</b>\n"
            f"Arah: {direction}\n"
            f"Lot: {position.volume}\n"
            f"Entry: {position.price_open:.2f}\n"
            f"SL: {position.sl:.2f}\n"
            f"TP1: {tp1:.2f} (50% close + breakeven)\n"
            f"TP2: {position.tp:.2f} (sisa 50%)\n"
        )

    def format_trade_close(self, ticket: int, profit: float, balance: float) -> str:
        emoji = "✅" if profit >= 0 else "❌"
        sign = "+" if profit >= 0 else ""
        return (
            f"{emoji} <b>Trade Ditutup #{ticket}</b>\n"
            f"P&L: {sign}{profit:.2f} USD\n"
            f"Balance: {balance:.2f} USD\n"
        )

    def format_daily_report(self, total_trades: int, win_trades: int, total_profit: float, balance: float) -> str:
        win_rate = win_trades / total_trades * 100 if total_trades > 0 else 0
        sign = "+" if total_profit >= 0 else ""
        return (
            f"📊 <b>Laporan Harian</b>\n"
            f"Total Trade: {total_trades}\n"
            f"Win Rate: {win_rate:.1f}%\n"
            f"Total P&L: {sign}{total_profit:.2f} USD\n"
            f"Balance: {balance:.2f} USD\n"
        )

    def _is_authorized(self, update) -> bool:
        return str(update.effective_chat.id) == str(self.chat_id)

    async def start_polling(self):
        from telegram import Update
        from telegram.ext import Application, CommandHandler, ContextTypes

        async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            if not self._is_authorized(update):
                return
            text = self._get_status() if self._get_status else "Status tidak tersedia"
            await update.message.reply_text(text)

        async def cmd_pause(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            if not self._is_authorized(update):
                return
            if self._pause:
                self._pause()
            await update.message.reply_text("⏸ Bot di-pause")

        async def cmd_resume(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            if not self._is_authorized(update):
                return
            if self._resume:
                self._resume()
            await update.message.reply_text("▶️ Bot dilanjutkan")

        async def cmd_laporan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            if not self._is_authorized(update):
                return
            text = self._get_laporan() if self._get_laporan else "Laporan tidak tersedia"
            await update.message.reply_text(text, parse_mode="HTML")

        async def cmd_trades(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            if not self._is_authorized(update):
                return
            text = self._get_trades() if self._get_trades else "Tidak ada trade terbuka"
            await update.message.reply_text(text, parse_mode="HTML")

        self._app = Application.builder().token(self.token).build()
        self._bot = self._app.bot
        self._app.add_handler(CommandHandler("status", cmd_status))
        self._app.add_handler(CommandHandler("pause", cmd_pause))
        self._app.add_handler(CommandHandler("resume", cmd_resume))
        self._app.add_handler(CommandHandler("laporan", cmd_laporan))
        self._app.add_handler(CommandHandler("trades", cmd_trades))
        try:
            await self._app.initialize()
            await self._app.start()
            await self._app.updater.start_polling()
        except Exception as e:
            logger.error(f"Telegram bot failed to start: {e}")
            raise

    async def stop(self):
        if self._app:
            try:
                await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
            except Exception as e:
                logger.error(f"Telegram bot stop error: {e}")
