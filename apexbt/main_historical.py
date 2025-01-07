from datetime import datetime, timezone, timedelta
from apexbt.database.database import init_database, save_tweet, is_tweet_processed
from apexbt.crypto.codex import Codex
from apexbt.crypto.crypto import get_crypto_price_dexscreener
from apexbt.trade.trade import TradeManager
from apexbt.tweet.tweet import TwitterManager
from apexbt.utils.sample_tweets import sample_tweets
from apexbt.sheets.sheets import setup_google_sheets, save_tweet as save_tweet_to_sheets
import time
import logging
from config.config import TWITTER_USERS

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def save_to_both_historical(
    tweet, ticker, ticker_status, price_data, ai_agent, sheets=None
):
    """Save data to both historical database and historical Google Sheets"""
    # Save to historical database
    save_tweet(tweet, ticker, ticker_status, price_data, ai_agent, historical=True)

    # Save to historical Google Sheets if available
    if sheets and "tweets" in sheets:
        save_tweet_to_sheets(
            sheets["tweets"], tweet, ticker, ticker_status, price_data, ai_agent
        )


def process_tweets(tweets, trade_manager, sheets=None):
    """Process a list of tweets and save to historical database"""
    trade_manager.start_monitoring(sheets)

    for tweet in tweets:
        try:
            # Check historical database
            if is_tweet_processed(tweet.id, tweet.author, historical=True):
                logger.info(
                    f"Tweet {tweet.id} from {tweet.author} already processed, skipping..."
                )
                continue

            ticker, ticker_status = TwitterManager.extract_ticker(tweet.text)
            if not ticker:
                continue

            price_data = None
            if ticker_status == "Single ticker":
                # First get contract/network from DexScreener
                dex_data = get_crypto_price_dexscreener(ticker)

                if dex_data:
                    contract_address = dex_data.get("contract_address")
                    network = dex_data.get("network")
                    logger.info(
                        f"Found contract {contract_address} on network {network} for {ticker}"
                    )

                    # Convert tweet creation time to Unix timestamp
                    tweet_timestamp = int(tweet.created_at.timestamp())

                    # Use contract info to get historical price from Codex
                    price_data = Codex.get_historical_prices(
                        contract_address, [tweet_timestamp], network
                    )

                    if price_data and len(price_data) > 0:
                        historical_price_data = price_data[0]  # Get first price point

                        if trade_manager.add_trade(
                            ticker,
                            historical_price_data["contract_address"],
                            str(tweet.id),
                            float(historical_price_data["price"]),
                            tweet.author,
                            network,
                            entry_timestamp=tweet.created_at,
                        ):
                            logger.info(
                                f"Opened new historical trade for {ticker} at {historical_price_data['price']}"
                            )

                        # Use the historical price data for saving
                        price_data = historical_price_data
                    else:
                        logger.warning(
                            f"No historical price data found from Codex for {ticker}"
                        )
                else:
                    logger.warning(
                        f"Could not find token info on DexScreener for {ticker}"
                    )

            # Save to both historical database and sheets
            save_to_both_historical(
                tweet, ticker, ticker_status, price_data, tweet.author, sheets
            )
            time.sleep(1)

        except Exception as e:
            logger.error(f"Error processing historical tweet: {str(e)}")
            time.sleep(2)
            continue


def process_sample_tweets(sheets=None):
    """Process the sample tweets for testing purposes"""
    logger.info("Processing sample tweets...")

    # Initialize historical database and sheets
    init_database(historical=True)
    # Get historical sheets if not provided
    if not sheets:
        sheets = setup_google_sheets(historical=True)

    logger.info(f"Number of sample tweets: {len(sample_tweets)}")
    # Create trade manager here
    trade_manager = TradeManager()
    trade_manager.start_monitoring()

    logger.info(f"Number of sample tweets: {len(sample_tweets)}")
    process_tweets(sample_tweets, sheets)

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Stopping historical trade manager...")
        trade_manager.stop_monitoring()


def run_historical_analysis(start_date=None, sheets=None):
    """Run analysis on historical tweets from multiple users"""
    if start_date is None:
        start_date = datetime.now(timezone.utc) - timedelta(days=7)
    else:
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)

    logger.info(f"Starting historical analysis from {start_date} UTC")

    twitter_manager = TwitterManager()
    if twitter_manager.verify_credentials():
        # Initialize historical database
        init_database(historical=True)

        # Get historical sheets if not provided
        if not sheets:
            sheets = setup_google_sheets(historical=True)

        trade_manager = TradeManager(update_interval=60, historical=True)
        trade_manager.start_monitoring(sheets)

        for i, username in enumerate(TWITTER_USERS, 1):
            try:
                process_user_historical_tweets(
                    twitter_manager,
                    trade_manager,
                    username,
                    start_date,
                    i,
                    len(TWITTER_USERS),
                    sheets,
                )
            except Exception as e:
                logger.error(
                    f"Error processing historical data for @{username}: {str(e)}"
                )
                continue

        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Stopping historical trade manager...")
            trade_manager.stop_monitoring()
    else:
        logger.error("Failed to authenticate with Twitter API")


def process_user_historical_tweets(
    twitter_manager,
    trade_manager,
    username,
    start_date,
    current_user_num,
    total_users,
    sheets=None,
):
    """Process historical tweets for a single user"""
    logger.info(
        f"\nProcessing historical data for user {current_user_num}/{total_users}: @{username}"
    )

    user_tweets = twitter_manager.fetch_historical_tweets(username, start_date)
    if user_tweets:
        user_tweets.sort(key=lambda x: x.created_at)
        logger.info(f"Found {len(user_tweets)} historical tweets from @{username}")
        process_tweets(user_tweets, trade_manager, sheets)
    else:
        logger.info(f"No historical tweets found for @{username}")

    if current_user_num < total_users:
        delay = 60
        logger.info(
            f"Waiting {delay}s before processing next user's historical data..."
        )
        time.sleep(delay)


if __name__ == "__main__":
    # Initialize Historical Google Sheets
    sheets = setup_google_sheets(historical=True)

    # Choose one of these modes:
    # 1. Process sample tweets with historical database
    # process_sample_tweets(sheets)

    # 2. Historical analysis
    start_date = datetime(2024, 12, 1, tzinfo=timezone.utc)
    run_historical_analysis(start_date, sheets)

    # 3. Just monitor existing historical trades
    # trade_manager = TradeManager()
    # trade_manager.start_monitoring(sheets)
    # try:
    #     while True:
    #         time.sleep(60)
    # except KeyboardInterrupt:
    #     trade_manager.stop_monitoring()
