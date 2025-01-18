import logging
from apexbt.tweet.tweet import TwitterManager
from apexbt.database.database import init_database, save_tweet, is_tweet_processed
from apexbt.crypto.crypto import get_crypto_price_dexscreener
from apexbt.trade.trade import TradeManager
from apexbt.sheets.sheets import setup_google_sheets
from apexbt.sheets.sheets import save_tweet as save_tweet_to_sheets
from apexbt.telegram_bot.telegram import TelegramManager
from apexbt.config.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TWITTER_USERS
from apexbt.crypto.codex import Codex
from apexbt.signal.signal import SignalAPI
from apexbt.agent.agent import TradeAgent
from config.config import TRADE_UPDATE_INTERVAL_SECONDS

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def process_new_tweet(tweet):
    """Process a single new tweet in real-time"""
    try:
        # Skip if tweet has already been processed
        if is_tweet_processed(tweet.id, tweet.author):
            logger.info(
                f"Tweet {tweet.id} from {tweet.author} already processed, skipping..."
            )
            return

        # Extract ticker from tweet
        ticker, ticker_status = TwitterManager.extract_ticker(tweet.text)
        if not ticker:
            return

        # Only reject if we're confident about negative sentiment
        if not trade_agent.should_take_trade(tweet.text, ticker):
            logger.info("Trade rejected due to negative sentiment")
            return

        # Get price data for single ticker
        price_data = None
        if ticker_status == "Single ticker":
            # First get contract/network from DexScreener
            dex_data = get_crypto_price_dexscreener(ticker)

            if dex_data:
                contract_address = dex_data.get("contract_address")
                network = dex_data.get("network")
                market_cap = dex_data.get("market_cap")

                logger.info(
                    f"Found contract {contract_address} on network {network} for {ticker}"
                )

                # Use contract info to get current price from Codex
                price_data = Codex.get_crypto_price(contract_address, network)

                if price_data and price_data.get("price"):
                    # Add trade to manager
                    if trade_manager.add_trade(
                        ticker,
                        price_data["contract_address"],
                        str(tweet.id),
                        float(price_data["price"]),
                        tweet.author,
                        network,
                        entry_timestamp=tweet.created_at,
                        market_cap=market_cap,
                    ):
                        logger.info(
                            f"Opened new trade for {ticker} at {price_data['price']} by {tweet.author}"
                        )
                else:
                    logger.warning(f"No price data found from Codex for {ticker}")
            else:
                logger.warning(f"Could not find token info on DexScreener for {ticker}")

        # Save tweet to both database and sheets
        save_to_both(tweet, ticker, ticker_status, price_data, tweet.author, sheets)

    except Exception as e:
        logger.error(f"Error processing tweet: {str(e)}")


def save_to_both(tweet, ticker, ticker_status, price_data, ai_agent, sheets=None):
    """Save data to both database and Google Sheets"""
    # Save to database
    save_tweet(tweet, ticker, ticker_status, price_data, ai_agent)

    # Save to Google Sheets if available
    if sheets and "tweets" in sheets:
        save_tweet_to_sheets(
            sheets["tweets"], tweet, ticker, ticker_status, price_data, ai_agent
        )


def main():
    global trade_manager
    global trade_agent

    # Initialize components
    init_database()
    sheets = setup_google_sheets()

    twitter_manager = TwitterManager()

    trade_manager = TradeManager(update_interval=TRADE_UPDATE_INTERVAL_SECONDS)
    telegram_manager = TelegramManager(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    signal_api = SignalAPI()
    trade_manager.set_telegram_manager(telegram_manager)
    trade_manager.set_signal_api(signal_api)

    trade_agent = TradeAgent()

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
