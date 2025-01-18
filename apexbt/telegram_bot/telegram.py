import logging
from telegram import Bot, ParseMode
from telegram.error import TelegramError

logger = logging.getLogger(__name__)


class TelegramManager:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.bot = Bot(token=bot_token)

    def send_message(self, message):
        try:
            self.bot.send_message(
                chat_id=self.chat_id, text=message, parse_mode=ParseMode.HTML
            )
        except TelegramError as e:
            logger.error(f"Telegram API Error: {e}")
            raise
