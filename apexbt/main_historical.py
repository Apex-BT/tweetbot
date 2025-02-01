from datetime import datetime, timezone, timedelta
from apexbt.database.database import Database
from apexbt.crypto.codex import Codex
from apexbt.crypto.dexscreener import DexScreener
from apexbt.trade.trade import TradeManager
from apexbt.tweet.tweet import TwitterManager
from apexbt.sheets.sheets import setup_google_sheets, save_tweet as save_tweet_to_sheets
import time
import logging
from apexbt.config.config import config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ApexbtHistorical:
    def __init__(self):
        self.db = Database(historical=True)
        self.sheets = None
        self.trade_manager = None
        self.twitter_manager = None
        self.dex_screener = DexScreener()

    def initialize(self):
        """Initialize components"""
        self.db.init_database()
        self.sheets = setup_google_sheets(historical=True)
        self.twitter_manager = TwitterManager(self.db)
        self.trade_manager = TradeManager(
            db=self.db,
            update_interval=config.TRADE_UPDATE_INTERVAL_SECONDS,
            historical=True
        )

    def save_to_both(self, tweet, ticker, ticker_status, price_data, ai_agent):
        """Save data to both historical database and historical Google Sheets"""
        # Save to historical database
        self.db.save_tweet(tweet, ticker, ticker_status, price_data, ai_agent)

        # Save to historical Google Sheets if available
        if self.sheets and "tweets" in self.sheets:
            save_tweet_to_sheets(
                self.sheets["tweets"], tweet, ticker, ticker_status, price_data, ai_agent
            )

    def process_tweets(self, tweets):
        """Process a list of tweets and save to historical database"""
        self.trade_manager.start_monitoring(self.sheets)

        for tweet in tweets:
            try:
                # Check historical database
                if self.db.is_tweet_processed(tweet.id, tweet.author):
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
                    dex_data = self.dex_screener.get_token_market_data(ticker)

                    if dex_data:
                        contract_address = dex_data.get("contract_address")
                        network = dex_data.get("network")
                        market_cap = dex_data.get("market_cap")
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
                            historical_price_data = price_data[0]

                            if self.trade_manager.add_trade(
                                ticker,
                                historical_price_data["contract_address"],
                                str(tweet.id),
                                float(historical_price_data["price"]),
                                tweet.author,
                                network,
                                entry_timestamp=tweet.created_at,
                                market_cap=market_cap,
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
                self.save_to_both(tweet, ticker, ticker_status, price_data, tweet.author)
                time.sleep(1)

            except Exception as e:
                logger.error(f"Error processing historical tweet: {str(e)}")
                time.sleep(2)
                continue

    def process_user_historical_tweets(self, username, start_date, current_user_num, total_users):
        """Process historical tweets for a single user"""
        logger.info(
            f"\nProcessing historical data for user {current_user_num}/{total_users}: @{username}"
        )

        user_tweets = self.twitter_manager.fetch_historical_tweets(username, start_date)
        if user_tweets:
            user_tweets.sort(key=lambda x: x.created_at)
            logger.info(f"Found {len(user_tweets)} historical tweets from @{username}")
            self.process_tweets(user_tweets)
        else:
            logger.info(f"No historical tweets found for @{username}")

        if current_user_num < total_users:
            delay = 60
            logger.info(
                f"Waiting {delay}s before processing next user's historical data..."
            )
            time.sleep(delay)

    def run_historical_analysis(self, start_date=None):
        """Run analysis on historical tweets from multiple users"""
        if start_date is None:
            start_date = datetime.now(timezone.utc) - timedelta(days=7)
        else:
            if start_date.tzinfo is None:
                start_date = start_date.replace(tzinfo=timezone.utc)

        logger.info(f"Starting historical analysis from {start_date} UTC")

        if self.twitter_manager.verify_credentials():
            self.trade_manager.start_monitoring(self.sheets)

            for i, username in enumerate(config.TWITTER_USERS, 1):
                try:
                    self.process_user_historical_tweets(
                        username,
                        start_date,
                        i,
                        len(config.TWITTER_USERS)
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
                self.trade_manager.stop_monitoring()
        else:
            logger.error("Failed to authenticate with Twitter API")

def main():
    apexbt = ApexbtHistorical()
    apexbt.initialize()
    start_date = datetime(2025, 2, 1, tzinfo=timezone.utc)
    apexbt.run_historical_analysis(start_date)

if __name__ == "__main__":
    main()
