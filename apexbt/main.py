import logging
from apexbt.tweet.tweet import TwitterManager
from apexbt.database.database import Database
from apexbt.trade.trade import TradeManager
from apexbt.sheets.sheets import setup_google_sheets
from apexbt.sheets.sheets import save_tweet as save_tweet_to_sheets
from apexbt.crypto.codex import Codex
from apexbt.signal.signal import SignalAPI
from apexbt.agent.agent import TradeAgent
from apexbt.crypto.dexscreener import DexScreener
from apexbt.config.config import config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Apexbt:
    def __init__(self):
        self.db = Database()
        self.sheets = None
        self.trade_manager = None
        self.trade_agent = None
        self.twitter_manager = None
        self.dex_screener = DexScreener()

    def initialize(self):
        """Initialize all components"""
        # Initialize database
        self.db.init_database()

        # Initialize Google Sheets
        self.sheets = setup_google_sheets()

        # Initialize Twitter manager
        self.twitter_manager = TwitterManager(self.db)

        # Initialize Trade manager and Signal API
        self.trade_manager = TradeManager(
                    db=self.db,
                    update_interval=config.TRADE_UPDATE_INTERVAL_SECONDS
                )
        SignalAPI.initialize(config.SIGNAL_API_USERNAME, config.SIGNAL_API_PASSWORD)
        signal_api = SignalAPI()
        self.trade_manager.set_signal_api(signal_api)

        # Initialize Trade agent
        self.trade_agent = TradeAgent()

    def process_new_tweet(self, tweet):
        """Process a single new tweet in real-time"""
        try:
            # Skip if tweet has already been processed
            if self.db.is_tweet_processed(tweet.id, tweet.author):
                logger.info(
                    f"Tweet {tweet.id} from {tweet.author} already processed, skipping..."
                )
                return

            # Extract ticker from tweet
            ticker, ticker_status = TwitterManager.extract_ticker(tweet.text)
            if not ticker:
                return

            # Only reject if we're confident about negative sentiment
            if not self.trade_agent.should_take_trade(tweet.text, ticker):
                logger.info("Trade rejected due to negative sentiment")
                return

            # Get price data for single ticker
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

                    # Use contract info to get current price from Codex
                    price_data = Codex.get_crypto_price(contract_address, network)

                    if price_data and price_data.get("price"):
                        # Add trade to manager
                        if self.trade_manager.add_trade(
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
            self.save_to_both(tweet, ticker, ticker_status, price_data, tweet.author)

        except Exception as e:
            logger.error(f"Error processing tweet: {str(e)}")

    def save_to_both(self, tweet, ticker, ticker_status, price_data, ai_agent):
        """Save data to both database and Google Sheets"""
        # Save to database
        self.db.save_tweet(tweet, ticker, ticker_status, price_data, ai_agent)

        # Save to Google Sheets if available
        if self.sheets and "tweets" in self.sheets:
            save_tweet_to_sheets(
                self.sheets["tweets"], tweet, ticker, ticker_status, price_data, ai_agent
            )

    def run(self):
        """Main execution method"""
        # Initialize all components
        self.initialize()

        # Verify Twitter credentials
        if not self.twitter_manager.verify_credentials():
            logger.error("Failed to verify Twitter credentials. Exiting...")
            return

        # Start trade manager
        self.trade_manager.start_monitoring(sheets=self.sheets)
        logger.info("Trade manager started successfully")

        logger.info(f"Starting to monitor tweets from: {', '.join(config.TWITTER_USERS)}")

        try:
            # Start monitoring tweets
            self.twitter_manager.monitor_multiple_users(
                usernames=config.TWITTER_USERS,
                callback=self.process_new_tweet,
            )

        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
            self.trade_manager.stop_monitoring()
        except Exception as e:
            logger.error(f"An error occurred: {str(e)}")
            self.trade_manager.stop_monitoring()


def main():
    apexbt = Apexbt()
    apexbt.run()


if __name__ == "__main__":
    main()
