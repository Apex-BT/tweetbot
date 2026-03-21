import logging
import asyncio
from apexbt.tweet.tweet import TwitterManager, MockTweet
from apexbt.database.database import Database
from apexbt.agent.agent import TradeAgent
from apexbt.crypto.dexscreener import DexScreener
from apexbt.crypto.token_validator import TokenValidator, ValidationCriteria
from apexbt.config.config import config
from apexbt.leaderboard import SignalRecorder, PriceTracker, LeaderboardBuilder
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Apexbt:
    def __init__(self):
        self.db = Database()
        self.dex_screener = DexScreener()
        self.twitter_manager = None
        self.trade_agent = None
        self.twitter_users = []
        self.twitter_validator = None

        # Leaderboard components
        self.signal_recorder = SignalRecorder()
        self.price_tracker = PriceTracker(
            interval_minutes=5,       # update prices every 5 min
            snapshot_interval_minutes=60,  # save snapshots every hour
        )
        self.leaderboard = LeaderboardBuilder()

    def initialize(self):
        """Initialize all components"""
        # Initialize database (legacy tables for backward compat)
        self.db.init_database()

        # Use config defaults for Twitter users
        # (leaderboard module handles its own Sheets connection)
        self.twitter_users = config.TWITTER_USERS
        logger.info(f"Monitoring {len(self.twitter_users)} Twitter accounts")

        # Initialize Twitter manager
        self.twitter_manager = TwitterManager(self.db)

        # Initialize Trade agent (Gemini sentiment analysis)
        self.trade_agent = TradeAgent()

        # Token validator (relaxed for leaderboard — we want to track everything)
        self.twitter_validator = TokenValidator(
            criteria=ValidationCriteria.twitter_default()
        )

        signal_count = self.signal_recorder.get_signal_count()
        agents = self.signal_recorder.get_all_agents()
        logger.info(
            f"Leaderboard initialized: {signal_count} signals from {len(agents)} agents"
        )

    # ------------------------------------------------------------------
    # Tweet processing (Twitter)
    # ------------------------------------------------------------------

    async def process_new_tweet(self, tweet):
        """Process a single new tweet — extract ticker, get price, record signal."""
        try:
            # Skip if already recorded
            if self.signal_recorder.is_duplicate(str(tweet.id)):
                return

            # Also check legacy DB
            if self.db.is_tweet_processed(tweet.id, tweet.author):
                return

            # Extract ticker from tweet
            ticker, ticker_status = TwitterManager.extract_ticker(tweet.text)
            if not ticker:
                return

            if ticker_status != "Single ticker":
                return

            # Run sentiment analysis
            sentiment = None
            sentiment_confidence = None
            try:
                should_trade = self.trade_agent.should_take_trade(tweet.text, ticker)
                if not should_trade:
                    logger.info(
                        f"Skipping ${ticker} by @{tweet.author} — negative sentiment"
                    )
                    return

                # Try to get sentiment details from the agent's last analysis
                sentiment = "POSITIVE"
                sentiment_confidence = 0.8
            except Exception as e:
                logger.debug(f"Sentiment analysis error for ${ticker}: {e}")
                # Continue anyway — we still want to record the signal

            # Get token data from DexScreener
            dex_data = self.dex_screener.get_token_by_ticker(ticker)

            if not dex_data:
                logger.warning(
                    f"Could not find token info on DexScreener for {ticker}"
                )
                return

            # Validate token
            is_valid, reason = self.twitter_validator.validate_token(dex_data)
            if not is_valid:
                logger.info(f"Token {ticker} validation failed: {reason}")
                return

            contract_address = dex_data.get("contract_address")
            network = dex_data.get("network")
            price = dex_data.get("current_price")

            if not price or float(price) <= 0:
                logger.warning(f"No valid price for {ticker}")
                return

            logger.info(
                f"Found ${ticker} at ${float(price):.8g} on {network} "
                f"(contract={contract_address})"
            )

            # Record signal
            signal = self.signal_recorder.record_signal_from_dex_data(
                agent=tweet.author,
                tweet_id=str(tweet.id),
                tweet_text=tweet.text,
                ticker=ticker,
                dex_data=dex_data,
                sentiment=sentiment,
                sentiment_confidence=sentiment_confidence,
            )

            if signal:
                pass  # Signal recorded — leaderboard handles the rest

        except Exception as e:
            logger.error(f"Error processing tweet: {str(e)}")

    # ------------------------------------------------------------------
    # Leaderboard update loop
    # ------------------------------------------------------------------

    async def leaderboard_update_loop(self):
        """Periodically recalculate leaderboard and write to Google Sheets."""
        logger.info("Leaderboard update loop started (every 5 minutes)")

        while True:
            try:
                # Run sheets update in a thread (it's synchronous + rate limited)
                await asyncio.to_thread(self.leaderboard.update_all)

                signal_count = self.signal_recorder.get_signal_count()
                agents = self.signal_recorder.get_all_agents()
                logger.info(
                    f"Leaderboard cycle complete: {signal_count} signals, "
                    f"{len(agents)} agents tracked"
                )
            except Exception as e:
                logger.error(f"Leaderboard update error: {e}")

            await asyncio.sleep(300)  # every 5 minutes

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------

    async def run_async(self):
        """Async version of run method"""
        self.initialize()

        # Verify Twitter credentials
        twitter_enabled = self.twitter_manager.verify_credentials()
        if not twitter_enabled:
            logger.warning(
                "Twitter credentials failed — Twitter monitoring disabled."
            )

        logger.info("Starting all monitoring tasks...")

        try:
            tasks = []

            # 1. Twitter monitoring
            if twitter_enabled:
                twitter_task = asyncio.create_task(
                    self.twitter_manager.monitor(
                        usernames=self.twitter_users,
                        callback=self.process_new_tweet,
                    )
                )
                tasks.append(twitter_task)
                logger.info(
                    f"Twitter monitoring: {len(self.twitter_users)} accounts"
                )
            else:
                logger.info("Skipping Twitter monitoring")

            # 2. Price tracker (updates prices for all active signals)
            tracker_task = asyncio.create_task(self.price_tracker.start())
            tasks.append(tracker_task)
            logger.info("Price tracker: active")

            # 3. Leaderboard updater (recalculates stats + writes to Sheets)
            leaderboard_task = asyncio.create_task(self.leaderboard_update_loop())
            tasks.append(leaderboard_task)
            logger.info("Leaderboard updater: active")

            logger.info(f"All {len(tasks)} tasks started. Bot is running.")
            await asyncio.gather(*tasks)

        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
            self.price_tracker.stop()
        except Exception as e:
            logger.error(f"An error occurred: {str(e)}")
            self.price_tracker.stop()

    def run(self):
        """Main execution method"""
        asyncio.run(self.run_async())




def main():
    apexbt = Apexbt()
    apexbt.run()


if __name__ == "__main__":
    main()
