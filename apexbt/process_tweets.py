from datetime import datetime
from apexbt.sheets.sheets import save_tweet, save_trade, setup_google_sheets, is_tweet_processed
from apexbt.crypto.crypto import get_crypto_price
from datetime import timedelta
from apexbt.trade.trade import TradeManager
from apexbt.tweet.tweet import TwitterManager
from apexbt.utils.sample_tweets import sample_tweets
import time
from datetime import timezone
import logging

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
    """Process a list of tweets and write to Google Sheet"""
    sheets = setup_google_sheets()
    tweets_sheet = sheets["tweets"]
    trades_sheet = sheets["trades"]
    pnl_sheet = sheets["pnl"]

    trade_manager = TradeManager(sheets)
    trade_manager.start_monitoring()

    for tweet in tweets:
        try:
            # Skip if tweet has already been processed for this AI agent
            if is_tweet_processed(tweets_sheet, tweet.id, tweet.author):
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
                        save_trade(trades_sheet, trade_data, pnl_sheet)
                        print(f"Opened new trade for {ticker} at {price_data['tweet_time_price']} by {tweet.author}")

            save_tweet(tweets_sheet, tweet, ticker, ticker_status, price_data, tweet.author)

            time.sleep(1)

        except Exception as e:
            print(f"Error processing tweet: {str(e)}")
            time.sleep(2)
            continue

    return trade_manager

def process_sample_tweets():
    """Process the sample tweets for testing purposes"""
    print("Processing sample tweets...")
    print(f"Number of sample tweets: {len(sample_tweets)}")

    try:
        trade_manager = process_tweets(sample_tweets)

        try:
            while True:
                time.sleep(10)
                stats = trade_manager.get_current_stats()
                if stats:
                    print("\nCurrent Positions:")

                    # Track current agent for grouping
                    current_agent = None

                    for position in stats:
                        if position['type'] == 'trade':
                            # Print agent header if changed
                            if position['ai_agent'] != current_agent:
                                current_agent = position['ai_agent']
                                print(f"\n{current_agent}'s Positions:")

                            print(f"{position['ticker']}: {position['price_change']}% "
                                  f"(Entry: ${position['entry_price']:.8f}, "
                                  f"Current: ${position['current_price']:.8f}, "
                                  f"PNL: ${position['pnl_dollars']:.2f})")

                        elif position['type'] == 'agent_total':
                            print(f"\n{position['agent']} Totals:")
                            print(f"Invested: ${position['invested_amount']:.2f}")
                            print(f"Current Value: ${position['current_value']:.2f}")
                            print(f"Total PNL: ${position['pnl_dollars']:.2f}")
                            print("-" * 30)

                        elif position['type'] == 'grand_total':
                            print("\nPortfolio Totals:")
                            print(f"Total Invested: ${position['invested_amount']:.2f}")
                            print(f"Total Current Value: ${position['current_value']:.2f}")
                            print(f"Total PNL: ${position['pnl_dollars']:.2f}")

                print("-" * 50)

        except KeyboardInterrupt:
            print("Stopping trade manager...")
            trade_manager.stop_monitoring()

    except Exception as e:
        print(f"Error processing sample tweets: {str(e)}")

def run_historical_analysis(start_date=None):
    """Run analysis on historical tweets from multiple users - processing per user"""
    if start_date is None:
        start_date = datetime.now(timezone.utc) - timedelta(days=7)
    else:
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)

    end_date = datetime.now(timezone.utc)

    logger.info(f"Fetching historical tweets from {start_date.strftime('%Y-%m-%d %H:%M:%S')} "
          f"to {end_date.strftime('%Y-%m-%d %H:%M:%S')} UTC")

    twitter_manager = TwitterManager()

    if twitter_manager.verify_credentials():
        sheets = setup_google_sheets()
        trade_manager = TradeManager(sheets)
        trade_manager.start_monitoring()

        total_users = len(TWITTER_USERS)
        total_processed = 0

        try:
            for i, username in enumerate(TWITTER_USERS, 1):
                try:
                    logger.info(f"\nProcessing user {i}/{total_users}: @{username}")
                    user_tweets = twitter_manager.fetch_historical_tweets(
                        username,
                        start_date,
                        tweets_sheet=sheets["tweets"]
                    )

                    if user_tweets:
                        # Sort user's tweets by creation date
                        user_tweets.sort(key=lambda x: x.created_at)
                        logger.info(f"Found {len(user_tweets)} tweets from @{username}")

                        # Process this user's tweets immediately
                        logger.info(f"Processing tweets for @{username}...")
                        process_tweets(user_tweets)

                        total_processed += len(user_tweets)
                        logger.info(f"Completed processing {len(user_tweets)} tweets for @{username}")
                    else:
                        logger.info(f"No tweets found for @{username}")

                    if i < total_users:
                        delay = 60  # 1 minute between users
                        logger.info(f"Waiting {delay}s before processing next user...")
                        time.sleep(delay)

                except Exception as e:
                    logger.error(f"Error processing @{username}: {str(e)}")
                    continue

            logger.info(f"\nCompleted processing all users. Total tweets processed: {total_processed}")

            # Monitor positions
            try:
                while True:
                    time.sleep(10)
                    stats = trade_manager.get_current_stats()
                    if stats:
                        print("\nCurrent Positions:")
                        current_agent = None

                        for position in stats:
                            if position['type'] == 'trade':
                                if position['ai_agent'] != current_agent:
                                    current_agent = position['ai_agent']
                                    print(f"\n{current_agent}'s Positions:")

                                print(f"{position['ticker']}: {position['price_change']}% "
                                      f"(Entry: ${position['entry_price']:.8f}, "
                                      f"Current: ${position['current_price']:.8f}, "
                                      f"PNL: ${position['pnl_dollars']:.2f})")

                            elif position['type'] == 'agent_total':
                                print(f"\n{position['agent']} Totals:")
                                print(f"Invested: ${position['invested_amount']:.2f}")
                                print(f"Current Value: ${position['current_value']:.2f}")
                                print(f"Total PNL: ${position['pnl_dollars']:.2f}")
                                print("-" * 30)

                            elif position['type'] == 'grand_total':
                                print("\nPortfolio Totals:")
                                print(f"Total Invested: ${position['invested_amount']:.2f}")
                                print(f"Total Current Value: ${position['current_value']:.2f}")
                                print(f"Total PNL: ${position['pnl_dollars']:.2f}")

                        print("-" * 50)

            except KeyboardInterrupt:
                print("Stopping trade manager...")
                trade_manager.stop_monitoring()

        except KeyboardInterrupt:
            logger.info("Process interrupted by user")
            trade_manager.stop_monitoring()

    else:
        logger.error("Failed to authenticate with Twitter API")

def run_realtime_monitoring():
    """Run real-time monitoring of multiple Twitter users"""
    twitter_manager = TwitterManager()
    sheets = setup_google_sheets()

    # Create TradeManager instance
    trade_manager = TradeManager(sheets)
    trade_manager.start_monitoring()

    def process_new_tweet(tweet):
        """Callback function to process new tweets"""
        try:
            ticker, ticker_status = TwitterManager.extract_ticker(tweet.text)
            if not ticker:
                return

            price_data = None
            if ticker_status == "Single ticker":
                price_data = get_crypto_price(ticker, tweet.created_at, include_historical=False)

                if price_data and price_data.get("tweet_time_price"):
                    trade_data = {
                        "trade_id": f"T{tweet.created_at.strftime('%Y%m%d%H%M%S')}",
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

                    if trade_manager.add_trade(ticker, float(price_data["tweet_time_price"]), tweet.created_at):
                        save_trade(sheets["trades"], trade_data, sheets["pnl"])
                        print(f"Opened new trade for {ticker} at {price_data['tweet_time_price']}")
                    else:
                        print(f"Could not open trade for {ticker} - position already exists")

            save_tweet(sheets["tweets"], tweet, ticker, ticker_status, price_data)

        except Exception as e:
            print(f"Error processing new tweet: {str(e)}")

    if twitter_manager.verify_credentials():
        print("Starting real-time monitoring of Twitter users...")
        try:
            twitter_manager.monitor_multiple_users(TWITTER_USERS, process_new_tweet)
        except KeyboardInterrupt:
            print("Stopping monitoring...")
            trade_manager.stop_monitoring()
    else:
        print("Failed to authenticate with Twitter API")

def run_trade_manager_only():
    """Run only the trade manager to monitor existing positions"""
    sheets = setup_google_sheets()

    # Create TradeManager instance
    trade_manager = TradeManager(sheets)
    trade_manager.start_monitoring()

    try:
        print("Trade manager started. Monitoring existing positions...")
        while True:
            time.sleep(10)  # Update every 10 seconds
            stats = trade_manager.get_current_stats()
            if stats:
                print("\nCurrent Positions:")

                # Track current agent for grouping
                current_agent = None

                for position in stats:
                    if position['type'] == 'trade':
                        # Print agent header if changed
                        if position['ai_agent'] != current_agent:
                            current_agent = position['ai_agent']
                            print(f"\n{current_agent}'s Positions:")

                        print(f"{position['ticker']}: {position['price_change']}% "
                              f"(Entry: ${position['entry_price']:.8f}, "
                              f"Current: ${position['current_price']:.8f}, "
                              f"PNL: ${position['pnl_dollars']:.2f})")

                    elif position['type'] == 'agent_total':
                        print(f"\n{position['agent']} Totals:")
                        print(f"Invested: ${position['invested_amount']:.2f}")
                        print(f"Current Value: ${position['current_value']:.2f}")
                        print(f"Total PNL: ${position['pnl_dollars']:.2f}")
                        print("-" * 30)

                    elif position['type'] == 'grand_total':
                        print("\nPortfolio Totals:")
                        print(f"Total Invested: ${position['invested_amount']:.2f}")
                        print(f"Total Current Value: ${position['current_value']:.2f}")
                        print(f"Total PNL: ${position['pnl_dollars']:.2f}")

                print("-" * 50)

    except KeyboardInterrupt:
        print("Stopping trade manager...")
        trade_manager.stop_monitoring()

if __name__ == "__main__":
    # Add this option to run sample tweets processing
    # Choose one of these modes:
    # 1. Process sample tweets
    # process_sample_tweets()

    # 2. Historical analysis
    start_date = datetime(2024, 12, 1)
    run_historical_analysis(start_date)

    # 3. Real-time monitoring
    # run_realtime_monitoring()

    # 4. Just monitor existing trades
    # run_trade_manager_only()
