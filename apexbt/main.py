import logging
import asyncio
from apexbt.tweet.tweet import TwitterManager, MockTweet
from apexbt.database.database import Database
from apexbt.trade.trade import TradeManager
from apexbt.sheets.sheets import setup_google_sheets, get_twitter_accounts
from apexbt.sheets.sheets import save_tweet as save_tweet_to_sheets
from apexbt.crypto.codex import Codex
from apexbt.trade_signal.trade_signal import SignalAPI
from apexbt.agent.agent import TradeAgent
from apexbt.crypto.dexscreener import DexScreener
from apexbt.crypto.token_validator import TokenValidator, ValidationCriteria
from apexbt.config.config import config
from apexbt.pumpfun.pumpfun import PumpFunManager
from apexbt.virtuals.virtuals import VirtualsManager
from datetime import datetime

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
        self.pumpfun_manager = None
        self.virtuals_manager = None
        self.dex_screener = DexScreener()
        self.twitter_users = []
        self.twitter_validator = None
        self.pumpfun_validator = None
        self.virtuals_validator = None

    def initialize(self):
        """Initialize all components"""
        # Initialize database
        self.db.init_database()

        # Initialize Google Sheets
        self.sheets = setup_google_sheets()

        if self.sheets and "accounts" in self.sheets:
            self.twitter_users = get_twitter_accounts(self.sheets["accounts"])
            if not self.twitter_users:
                logger.warning(
                    "No Twitter accounts found in Accounts sheet. Using config defaults."
                )
                self.twitter_users = config.TWITTER_USERS
        else:
            logger.warning("Accounts sheet not available. Using config defaults.")
            self.twitter_users = config.TWITTER_USERS

        # Initialize Twitter manager
        self.twitter_manager = TwitterManager(self.db)

        # Initialize PumpFun manager
        self.pumpfun_manager = PumpFunManager(callback=self.process_new_token)

        # Initialize Virtuals manager
        self.virtuals_manager = VirtualsManager(callback=self.process_new_token)

        # Initialize Trade manager and Signal API
        self.trade_manager = TradeManager(
            db=self.db, update_interval=config.TRADE_UPDATE_INTERVAL_SECONDS
        )
        SignalAPI.initialize(config.SIGNAL_API_USERNAME, config.SIGNAL_API_PASSWORD)
        signal_api = SignalAPI()
        self.trade_manager.set_signal_api(signal_api)

        # Initialize Trade agent
        self.trade_agent = TradeAgent()

        # Create two validators with different criteria
        self.twitter_validator = TokenValidator(
            criteria=ValidationCriteria.twitter_default()
        )
        self.pumpfun_validator = TokenValidator(
            criteria=ValidationCriteria.pumpfun_default()
        )
        self.virtuals_validator = TokenValidator(
            criteria=ValidationCriteria.virtuals_default()
        )

    async def process_new_token(self, token_info):
        """Process new tokens from PumpFun"""
        try:
            # Get basic info from token_info
            contract_address = token_info["token_address"]
            network = token_info["network"]
            symbol = token_info.get("symbol", "UNKNOWN")

            # Ensure proper timestamp handling
            created_at = token_info.get("created_at")
            if not created_at:
                created_at = datetime.now()
            elif isinstance(created_at, str):
                try:
                    created_at = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    created_at = datetime.now()

            # Update token_info with validated timestamp
            token_info["created_at"] = created_at

            # Skip if already processed
            if self.db.is_tweet_processed(token_info["id"], token_info["author"]):
                logger.info(
                    f"Token {contract_address} from {token_info['author']} already processed, skipping..."
                )
                return

            # Get token data from DexScreener
            dex_data = self.dex_screener.get_token_by_address(contract_address, network)

            if dex_data:
                dex_data["address"] = contract_address
                # Select appropriate validator based on author
                if token_info["author"] == "pump.fun":
                    validator = self.pumpfun_validator
                elif token_info["author"] == "virtuals":
                    validator = self.virtuals_validator
                else:
                    logger.warning(f"Unknown token source: {token_info['author']}")
                    return

                # Validate token
                symbol = dex_data.get("token_symbol", "NOT FOUND")
                is_valid, reason = validator.validate_token(dex_data)
                if not is_valid:
                    logger.info(f"Token {symbol} validation failed: {reason}")
                    return

                market_cap = dex_data.get("market_cap")

                # Get holders data from Codex
                holders_data = Codex.get_token_holders(
                    contract_address=contract_address,
                    network=network,
                )

                holder_count = holders_data.get("total_count", 0) if holders_data else 0

                # Get price data from Codex
                price_data = Codex.get_crypto_price(contract_address, network)

                if price_data and price_data.get("price"):
                    # Create mock tweet for compatibility
                    mock_tweet = MockTweet(
                        id=token_info["id"],
                        text=token_info["text"],
                        created_at=token_info["created_at"],
                        author=token_info["author"],
                    )

                    # Save to database and sheets
                    self.save_to_both(
                        mock_tweet,
                        symbol,
                        "Single ticker",
                        price_data,
                        token_info["author"],
                    )

                    # Add trade
                    if self.trade_manager.add_trade(
                        symbol,
                        contract_address,
                        str(token_info["id"]),
                        float(price_data["price"]),
                        token_info["author"],
                        network,
                        entry_timestamp=token_info["created_at"],
                        market_cap=market_cap,
                        holder_count=holder_count,
                    ):
                        logger.info(
                            f"Opened new trade for {symbol} at {price_data['price']}"
                        )
                else:
                    logger.warning(f"No price data found from Codex for {symbol}")
            else:
                logger.warning(f"Could not find token info on DexScreener for {symbol}")

        except Exception as e:
            logger.error(f"Error processing PumpFun token: {str(e)}")

    async def process_new_tweet(self, tweet):
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
                dex_data = self.dex_screener.get_token_by_ticker(ticker)

                if dex_data:
                    is_valid, reason = self.twitter_validator.validate_token(dex_data)
                    if not is_valid:
                        logger.info(f"Token {ticker} validation failed: {reason}")
                        return
                    contract_address = dex_data.get("contract_address")
                    network = dex_data.get("network")
                    market_cap = dex_data.get("market_cap")

                    logger.info(
                        f"Found contract {contract_address} on network {network} for {ticker}"
                    )

                    # Use contract info to get current price from Codex
                    price_data = Codex.get_crypto_price(contract_address, network)

                    holders_data = Codex.get_token_holders(
                        contract_address=contract_address,
                        network=network,
                    )
                    holder_count = (
                        holders_data.get("total_count", 0) if holders_data else 0
                    )

                    if price_data and price_data.get("price"):
                        # Save tweet to both database and sheets
                        self.save_to_both(
                            tweet, ticker, ticker_status, price_data, tweet.author
                        )

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
                            holder_count=holder_count,
                        ):
                            logger.info(
                                f"Opened new trade for {ticker} at {price_data['price']} by {tweet.author}"
                            )
                    else:
                        logger.warning(f"No price data found from Codex for {ticker}")
                else:
                    logger.warning(
                        f"Could not find token info on DexScreener for {ticker}"
                    )

        except Exception as e:
            logger.error(f"Error processing tweet: {str(e)}")

    async def run_async(self):
        """Async version of run method"""
        # Initialize all components
        self.initialize()

        # Verify Twitter credentials
        if not self.twitter_manager.verify_credentials():
            logger.error("Failed to verify Twitter credentials. Exiting...")
            return

        # Start trade manager
        self.trade_manager.start_monitoring(sheets=self.sheets)
        logger.info("Trade manager started successfully")

        try:
            twitter_task = asyncio.create_task(
                self.twitter_manager.monitor(
                    usernames=self.twitter_users,
                    callback=self.process_new_tweet,
                )
            )
            pumpfun_task = asyncio.create_task(self.pumpfun_manager.monitor())
            virtuals_task = asyncio.create_task(self.virtuals_manager.monitor())
            await asyncio.gather(twitter_task, pumpfun_task, virtuals_task)

        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
            self.trade_manager.stop_monitoring()
            self.pumpfun_manager.stop()
            self.virtuals_manager.stop()
        except Exception as e:
            logger.error(f"An error occurred: {str(e)}")
            self.trade_manager.stop_monitoring()
            self.pumpfun_manager.stop()
            self.virtuals_manager.stop()

    def run(self):
        """Main execution method"""
        asyncio.run(self.run_async())

    def save_to_both(self, tweet, ticker, ticker_status, price_data, ai_agent):
        """Save data to both database and Google Sheets"""
        # Save to database
        self.db.save_tweet(tweet, ticker, ticker_status, price_data, ai_agent)

        # Save to Google Sheets if available
        if self.sheets and "tweets" in self.sheets:
            save_tweet_to_sheets(
                self.sheets["tweets"],
                tweet,
                ticker,
                ticker_status,
                price_data,
                ai_agent,
            )


def main():
    apexbt = Apexbt()
    apexbt.run()


if __name__ == "__main__":
    main()
