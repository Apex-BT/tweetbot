from datetime import datetime, timezone, timedelta
from apexbt.database.database import init_database, save_tweet, save_trade, is_tweet_processed
from apexbt.crypto.crypto import get_crypto_price
from apexbt.trade.trade import TradeManager
from apexbt.tweet.tweet import TwitterManager
from apexbt.utils.sample_tweets import sample_tweets
import time
import logging
from apexbt.sheets.sheets import setup_google_sheets
from apexbt.database.database import get_db_connection

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TWITTER_USERS = [
    "Vader_AI_",
    "freysa_ai",
    "aixbt_agent",
    "tri_sigma_",
    "gekko_agent"
]

def process_tweets(tweets):
    """Process a list of tweets and save to database"""
    trade_manager = TradeManager()
    trade_manager.start_monitoring()

    for tweet in tweets:
        try:
            # Skip if tweet has already been processed for this AI agent
            if is_tweet_processed(tweet.id, tweet.author):
                logger.info(f"Tweet {tweet.id} from {tweet.author} already processed, skipping...")
                continue

            ticker, ticker_status = TwitterManager.extract_ticker(tweet.text)
            if not ticker:
                continue

            price_data = None
            if ticker_status == "Single ticker":
                price_data = get_crypto_price(ticker, tweet.created_at, include_historical=False)

                if price_data and price_data.get("tweet_time_price"):
                    trade_data = {
                        "trade_id": f"T{tweet.created_at.strftime('%Y%m%d%H%M%S')}",
                        "ai_agent": tweet.author,
                        "ticker": ticker,
                        "entry_price": price_data["tweet_time_price"],
                        "position_size": 100,
                        "direction": "Long",
                        "stop_loss": float(price_data["tweet_time_price"]) * 0.95,
                        "take_profit": float(price_data["tweet_time_price"]) * 1.15,
                        "tweet_id": tweet.id,
                        "notes": "Auto trade based on tweet signal",
                        "timestamp": tweet.created_at
                    }

                    if trade_manager.add_trade(ticker, float(price_data["tweet_time_price"]),
                                             tweet.author, tweet.created_at):
                        save_trade(trade_data)
                        logger.info(f"Opened new trade for {ticker} at {price_data['tweet_time_price']} by {tweet.author}")

            save_tweet(tweet, ticker, ticker_status, price_data, tweet.author)
            time.sleep(1)

        except Exception as e:
            logger.error(f"Error processing tweet: {str(e)}")
            time.sleep(2)
            continue

    return trade_manager

def reprocess_null_price_tweets():
    """Reprocess tweets with NULL prices in the database"""
    logger.info("Reprocessing tweets with NULL prices...")

    try:
        # Initialize trade manager
        trade_manager = TradeManager()
        trade_manager.start_monitoring()

        # Get tweets with NULL prices from database
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT tweet_id, ai_agent, text, created_at, ticker, ticker_status
                FROM tweets
                WHERE current_price IS NULL
                AND ticker IS NOT NULL
                AND ticker != 'N/A'
                ORDER BY created_at
            """)
            null_price_tweets = cursor.fetchall()

        logger.info(f"Found {len(null_price_tweets)} tweets to reprocess")

        for tweet in null_price_tweets:
            try:
                # Parse created_at with multiple format attempts
                created_at = None
                datetime_formats = [
                    "%Y-%m-%d %H:%M:%S.%f",
                    "%Y-%m-%d %H:%M:%S%z",
                    "%Y-%m-%d %H:%M:%S+00:00",
                    "%Y-%m-%d %H:%M:%S"
                ]

                for dt_format in datetime_formats:
                    try:
                        created_at = datetime.strptime(tweet['created_at'], dt_format)
                        break
                    except ValueError:
                        continue

                if not created_at:
                    logger.error(f"Could not parse datetime for tweet {tweet['tweet_id']}: {tweet['created_at']}")
                    continue

                # Get current price data
                price_data = get_crypto_price(tweet['ticker'], created_at, include_historical=False)

                if price_data and price_data.get("tweet_time_price"):
                    # Update tweet price data
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE tweets
                            SET current_price = ?,
                                tweet_time_price = ?,
                                volume_24h = ?,
                                liquidity = ?,
                                price_change_24h = ?,
                                dex = ?,
                                network = ?,
                                trading_pair = ?,
                                contract_address = ?,
                                last_updated = ?
                            WHERE tweet_id = ?
                        """, (
                            price_data.get("current_price"),
                            price_data.get("tweet_time_price"),
                            price_data.get("volume_24h"),
                            price_data.get("liquidity"),
                            price_data.get("percent_change_24h"),
                            price_data.get("dex"),
                            price_data.get("network"),
                            price_data.get("pair_name"),
                            price_data.get("contract_address"),
                            datetime.now(),
                            tweet['tweet_id']
                        ))
                        conn.commit()

                    # Create trade if not exists
                    trade_data = {
                        "trade_id": f"T{created_at.strftime('%Y%m%d%H%M%S')}",
                        "ai_agent": tweet['ai_agent'],
                        "ticker": tweet['ticker'],
                        "entry_price": price_data["tweet_time_price"],
                        "position_size": 100,
                        "direction": "Long",
                        "stop_loss": float(price_data["tweet_time_price"]) * 0.95,
                        "take_profit": float(price_data["tweet_time_price"]) * 1.15,
                        "tweet_id": tweet['tweet_id'],
                        "notes": "Auto trade based on reprocessed tweet",
                        "timestamp": created_at
                    }

                    if trade_manager.add_trade(tweet['ticker'],
                                             float(price_data["tweet_time_price"]),
                                             tweet['ai_agent'],
                                             created_at):
                        save_trade(trade_data)
                        logger.info(f"Created new trade for {tweet['ticker']} at {price_data['tweet_time_price']}")

                    logger.info(f"Updated price data for tweet {tweet['tweet_id']}")
                else:
                    logger.warning(f"No price data found for {tweet['ticker']}")

                time.sleep(1)  # Rate limiting

            except Exception as e:
                logger.error(f"Error processing tweet {tweet['tweet_id']}: {str(e)}")
                continue

        logger.info("Completed reprocessing tweets")

        try:
            monitor_positions(trade_manager)
        except KeyboardInterrupt:
            logger.info("Stopping trade manager...")
            trade_manager.stop_monitoring()

    except Exception as e:
        logger.error(f"Error during reprocessing: {str(e)}")
        if trade_manager:
            trade_manager.stop_monitoring()

def process_sample_tweets():
    """Process the sample tweets for testing purposes"""
    logger.info("Processing sample tweets...")
    logger.info(f"Number of sample tweets: {len(sample_tweets)}")

    try:
        init_database()
        trade_manager = process_tweets(sample_tweets)

        try:
            monitor_positions(trade_manager)
        except KeyboardInterrupt:
            logger.info("Stopping trade manager...")
            trade_manager.stop_monitoring()

    except Exception as e:
        logger.error(f"Error processing sample tweets: {str(e)}")

def run_historical_analysis(start_date=None, sheets=None):
    """Run analysis on historical tweets from multiple users"""
    if start_date is None:
        start_date = datetime.now(timezone.utc) - timedelta(days=7)
    else:
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)

    end_date = datetime.now(timezone.utc)
    logger.info(f"Fetching historical tweets from {start_date} to {end_date} UTC")

    twitter_manager = TwitterManager()
    if twitter_manager.verify_credentials():
        init_database()
        trade_manager = TradeManager()
        trade_manager.start_monitoring()

        process_historical_tweets(twitter_manager, trade_manager, start_date, sheets)

    else:
        logger.error("Failed to authenticate with Twitter API")

def process_user_historical_tweets(twitter_manager, trade_manager, username, start_date, current_user_num, total_users):
    """Process historical tweets for a single user"""
    logger.info(f"\nProcessing user {current_user_num}/{total_users}: @{username}")

    user_tweets = twitter_manager.fetch_historical_tweets(
        username,
        start_date,
    )

    if user_tweets:
        # Sort user's tweets by creation date
        user_tweets.sort(key=lambda x: x.created_at)
        logger.info(f"Found {len(user_tweets)} tweets from @{username}")

        # Process this user's tweets immediately
        for tweet in user_tweets:
            try:
                if is_tweet_processed(tweet.id, username):
                    logger.info(f"Tweet {tweet.id} already processed, skipping...")
                    continue

                ticker, ticker_status = TwitterManager.extract_ticker(tweet.text)
                if not ticker:
                    continue

                price_data = None
                if ticker_status == "Single ticker":
                    price_data = get_crypto_price(ticker, tweet.created_at, include_historical=False)

                    if price_data and price_data.get("tweet_time_price"):
                        trade_data = {
                            "trade_id": f"T{tweet.created_at.strftime('%Y%m%d%H%M%S')}",
                            "ai_agent": username,
                            "ticker": ticker,
                            "entry_price": price_data["tweet_time_price"],
                            "position_size": 100,
                            "direction": "Long",
                            "stop_loss": float(price_data["tweet_time_price"]) * 0.95,
                            "take_profit": float(price_data["tweet_time_price"]) * 1.15,
                            "tweet_id": tweet.id,
                            "notes": "Auto trade based on tweet signal",
                            "timestamp": tweet.created_at
                        }

                        if trade_manager.add_trade(ticker, float(price_data["tweet_time_price"]),
                                                 username, tweet.created_at):
                            save_trade(trade_data)
                            logger.info(f"Opened new trade for {ticker} at {price_data['tweet_time_price']}")

                save_tweet(tweet, ticker, ticker_status, price_data, username)

            except Exception as e:
                logger.error(f"Error processing tweet {tweet.id}: {str(e)}")
                continue

        logger.info(f"Completed processing tweets for @{username}")
    else:
        logger.info(f"No tweets found for @{username}")

    if current_user_num < total_users:
        delay = 60  # 1 minute between users
        logger.info(f"Waiting {delay}s before processing next user...")
        time.sleep(delay)

def process_historical_tweets(twitter_manager, trade_manager, start_date, sheets=None):
    """Process historical tweets for all users"""
    total_users = len(TWITTER_USERS)
    total_processed = 0

    try:
        for i, username in enumerate(TWITTER_USERS, 1):
            try:
                process_user_historical_tweets(
                    twitter_manager, trade_manager, username, start_date, i, total_users
                )
            except Exception as e:
                logger.error(f"Error processing @{username}: {str(e)}")
                continue

        logger.info(f"\nCompleted processing all users. Total tweets processed: {total_processed}")
        monitor_positions(trade_manager, sheets)

    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
        trade_manager.stop_monitoring()

def monitor_positions(trade_manager, sheets=None):
    """Monitor trading positions"""
    try:
        while True:
            time.sleep(60)
            stats = trade_manager.get_current_stats()
            if stats:
                display_position_stats(stats)
                # Update Google Sheets if available
                if sheets and 'pnl' in sheets:
                    from apexbt.sheets.sheets import update_pnl_sheet
                    update_pnl_sheet(sheets['pnl'], stats)

    except KeyboardInterrupt:
        logger.info("Stopping trade manager...")
        trade_manager.stop_monitoring()

def display_position_stats(stats):
    """Display current position statistics"""
    print("\nCurrent Positions:")
    current_agent = None

    for position in stats:
        if position['type'] == 'trade':
            if position['ai_agent'] != current_agent:
                current_agent = position['ai_agent']
                print(f"\n{current_agent}'s Positions:")
            print_trade_position(position)

        elif position['type'] == 'agent_total':
            print_agent_totals(position)

        elif position['type'] == 'grand_total':
            print_portfolio_totals(position)

    print("-" * 50)

def print_trade_position(position):
    """Print individual trade position details"""
    print(f"{position['ticker']}: {position['price_change']}% "
          f"(Entry: ${position['entry_price']:.8f}, "
          f"Current: ${position['current_price']:.8f}, "
          f"PNL: ${position['pnl_dollars']:.2f})")

def print_agent_totals(position):
    """Print agent total statistics"""
    print(f"\n{position['agent']} Totals:")
    print(f"Invested: ${position['invested_amount']:.2f}")
    print(f"Current Value: ${position['current_value']:.2f}")
    print(f"Total PNL: ${position['pnl_dollars']:.2f}")
    print("-" * 30)

def print_portfolio_totals(position):
    """Print overall portfolio statistics"""
    print("\nPortfolio Totals:")
    print(f"Total Invested: ${position['invested_amount']:.2f}")
    print(f"Total Current Value: ${position['current_value']:.2f}")
    print(f"Total PNL: ${position['pnl_dollars']:.2f}")

def run_trade_manager_only(sheets=None):
    """Run only the trade manager to monitor existing positions"""
    init_database()
    trade_manager = TradeManager()
    trade_manager.start_monitoring()

    try:
        logger.info("Trade manager started. Monitoring existing positions...")
        monitor_positions(trade_manager, sheets)
    except KeyboardInterrupt:
        logger.info("Stopping trade manager...")
        trade_manager.stop_monitoring()

if __name__ == "__main__":
    # Initialize Google Sheets
    sheets = setup_google_sheets()

    # Choose one of these modes:
    # 1. Process sample tweets
    # process_sample_tweets()

    # 2. Historical analysis
    # start_date = datetime(2024, 12, 1)
    # run_historical_analysis(start_date, sheets)

    # 3. Just monitor existing trades
    # run_trade_manager_only(sheets)

    # 4. Reprocess tweets with NULL prices
    reprocess_null_price_tweets()
