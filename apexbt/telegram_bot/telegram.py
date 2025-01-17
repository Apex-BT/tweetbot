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

    def send_trade_notification(
        self,
        ticker,
        contract_address,
        price,
        ai_agent,
        network="ethereum",
        tx_type="buy",
        market_cap=None,
    ):
        try:
            formatted_mcap = "N/A"
            if market_cap:
                if market_cap >= 1_000_000:
                    formatted_mcap = f"${market_cap/1_000_000:.1f}M"
                else:
                    formatted_mcap = f"${market_cap/1_000:.1f}K"

            message = (
                f"🚨 New Trade Alert 🚨\n\n"
                f"Token: <code>${ticker}</code>\n"
                f"Contract: <code>{contract_address}</code>\n"
                f"Market Cap: <code>{formatted_mcap}</code>\n"
                f"Entry Price: <code>${price:.8f}</code>\n"
                f"Signal From: <code>{ai_agent}</code>\n"
                f"Chain: <code>{network.lower()}</code>\n"
                f"Type: <code>{tx_type}</code>"
            )

            self.send_message(message)
            logger.info(f"Trade notification sent to Telegram for {ticker}")
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {str(e)}")
