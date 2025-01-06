import logging
from apexbt.tweet.tweet import TwitterManager
from apexbt.database.database import init_database, save_tweet, is_tweet_processed
from apexbt.crypto.crypto import get_crypto_price_dexscreener as get_crypto_price
from apexbt.trade.trade import TradeManager
from apexbt.sheets.sheets import setup_google_sheets
from apexbt.sheets.sheets import save_tweet as save_tweet_to_sheets
from apexbt.telegram_bot.telegram import TelegramManager
from apexbt.config.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Twitter users to monitor
TWITTER_USERS = [
    "Vader_AI_",
    "freysa_ai",
    "aixbt_agent",
    "tri_sigma_",
    "gekko_agent"
]

def process_new_tweet(tweet):
    """Process a single new tweet in real-time"""
    try:
        # Skip if tweet has already been processed
        if is_tweet_processed(tweet.id, tweet.author):
            logger.info(f"Tweet {tweet.id} from {tweet.author} already processed, skipping...")
            return

        # Extract ticker from tweet
        ticker, ticker_status = TwitterManager.extract_ticker(tweet.text)
        if not ticker:
            return

        # Get price data for single ticker
        price_data = None
        if ticker_status == "Single ticker":
            price_data = get_crypto_price(ticker)

            if price_data and price_data.get("current_price"):
                # Add trade to manager
                if trade_manager.add_trade(ticker, price_data["contract_address"], str(tweet.id), float(price_data["current_price"]),
                                         tweet.author):
                    logger.info(f"Opened new trade for {ticker} at {price_data['current_price']} by {tweet.author}")
                    # Send Telegram notification
                    telegram_manager.send_trade_notification(
                        ticker,
                        price_data["contract_address"],
                        float(price_data["current_price"]),
                        tweet.author
                    )

        # Save tweet to both database and sheets
        save_to_both(tweet, ticker, ticker_status, price_data, tweet.author, sheets)

    except Exception as e:
        logger.error(f"Error processing tweet: {str(e)}")

def save_to_both(tweet, ticker, ticker_status, price_data, ai_agent, sheets=None):
    """Save data to both database and Google Sheets"""
    # Save to database
    save_tweet(tweet, ticker, ticker_status, price_data, ai_agent)

    # Save to Google Sheets if available
    if sheets and 'tweets' in sheets:
        save_tweet_to_sheets(sheets['tweets'], tweet, ticker, ticker_status, price_data, ai_agent)

def main():
    global trade_manager  # Make trade_manager accessible to process_new_tweet
    global sheets
    global telegram_manager


    # Initialize components
    init_database()
    twitter_manager = TwitterManager()
    trade_manager = TradeManager()
    sheets = setup_google_sheets()
    telegram_manager = TelegramManager(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

    # Verify Twitter credentials
    if not twitter_manager.verify_credentials():
        logger.error("Failed to verify Twitter credentials. Exiting...")
        return

    # Start trade manager
    trade_manager.start_monitoring(sheets=sheets)
    logger.info("Trade manager started successfully")

    logger.info(f"Starting to monitor tweets from: {', '.join(TWITTER_USERS)}")

    try:
        # Start monitoring tweets
        twitter_manager.monitor_multiple_users(
            usernames=TWITTER_USERS,
            callback=process_new_tweet,
        )

    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
        trade_manager.stop_monitoring()
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        trade_manager.stop_monitoring()

if __name__ == "__main__":
    main()
