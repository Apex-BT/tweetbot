import logging
import asyncio
from telegram import Bot
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

class TelegramManager:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.bot = Bot(token=bot_token)

    async def _send_message(self, message):
        await self.bot.send_message(
            chat_id=self.chat_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN
        )

    def send_trade_notification(self, ticker, contract_address, price, ai_agent):
        try:
            message = (
                f"🚨 New Trade Alert 🚨\n\n"
                f"Token: ${ticker}\n"
                f"Contract: `{contract_address}`\n"
                f"Entry Price: ${price:.8f}\n"
                f"Signal from: {ai_agent}"
            )

            # Create new event loop if there isn't one
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # Run the coroutine
            loop.run_until_complete(self._send_message(message))

            logger.info(f"Trade notification sent to Telegram for {ticker}")
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {str(e)}")
