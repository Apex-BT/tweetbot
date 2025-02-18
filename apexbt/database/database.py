import psycopg2
from psycopg2.extras import DictCursor
from apexbt.config.config import config
from datetime import datetime
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, historical=False):
        self.historical = historical
        self.db_url = config.DATABASE_URL
        if not self.db_url:
            raise ValueError("Database URL not configured")

    @contextmanager
    def get_connection(self):
        """Get database connection with context manager"""
        conn = None
        try:
            conn = psycopg2.connect(self.db_url)
            yield conn
        except psycopg2.Error as e:
            logger.error(f"Database connection error: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()

    def init_database(self):
        """Initialize the database with required tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tweets (
                    tweet_id TEXT PRIMARY KEY,
                    ai_agent TEXT,
                    text TEXT,
                    created_at TIMESTAMP,
                    timestamp TIMESTAMP,
                    ticker TEXT,
                    ticker_status TEXT,
                    current_price DECIMAL,
                    tweet_time_price DECIMAL,
                    volume_24h DECIMAL,
                    liquidity DECIMAL,
                    price_change_24h DECIMAL,
                    dex TEXT,
                    network TEXT,
                    trading_pair TEXT,
                    contract_address TEXT,
                    last_updated TIMESTAMP
                )
            """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    trade_id TEXT PRIMARY KEY,
                    ai_agent TEXT,
                    timestamp TIMESTAMP,
                    ticker TEXT,
                    entry_price DECIMAL,
                    position_size DECIMAL,
                    direction TEXT,
                    stop_loss DECIMAL,
                    take_profit DECIMAL,
                    tweet_id TEXT,
                    status TEXT,
                    exit_price DECIMAL,
                    exit_timestamp TIMESTAMP,
                    exit_reason TEXT,
                    pnl_amount DECIMAL,
                    pnl_percentage DECIMAL,
                    notes TEXT,
                    contract_address TEXT,
                    network TEXT,
                    ath_price DECIMAL,
                    ath_timestamp TIMESTAMP,
                    trade_duration TEXT,
                    max_drawdown DECIMAL,
                    max_profit DECIMAL,
                    market_cap DECIMAL,
                    FOREIGN KEY(tweet_id) REFERENCES tweets(tweet_id)
                )
            """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS pnl (
                    id SERIAL PRIMARY KEY,
                    ai_agent TEXT,
                    ticker TEXT,
                    entry_time TIMESTAMP,
                    entry_price DECIMAL,
                    current_price DECIMAL,
                    price_change_percentage DECIMAL,
                    invested_amount DECIMAL,
                    current_value DECIMAL,
                    pnl DECIMAL,
                    contract_address TEXT
                )
            """
            )

            conn.commit()

    def save_tweet(self, tweet, ticker, ticker_status, price_data, ai_agent):
        """Save tweet to database"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO tweets (
                        tweet_id, ai_agent, text, created_at, timestamp, ticker,
                        ticker_status, current_price, tweet_time_price, volume_24h,
                        liquidity, price_change_24h, dex, network, trading_pair,
                        contract_address, last_updated
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(tweet.id),
                        ai_agent,
                        tweet.text,
                        tweet.created_at,
                        datetime.now(),
                        ticker if ticker else "N/A",
                        ticker_status,
                        price_data.get("current_price") if price_data else None,
                        price_data.get("tweet_time_price") if price_data else None,
                        price_data.get("volume_24h") if price_data else None,
                        price_data.get("liquidity") if price_data else None,
                        price_data.get("percent_change_24h") if price_data else None,
                        price_data.get("dex") if price_data else None,
                        price_data.get("network") if price_data else None,
                        price_data.get("pair_name") if price_data else None,
                        price_data.get("contract_address") if price_data else None,
                        price_data.get("last_updated") if price_data else None,
                    ),
                )
                conn.commit()
                logger.info(f"Tweet saved to database: {tweet.id}")
        except Exception as e:
            logger.error(f"Error saving tweet to database: {str(e)}")

    def is_tweet_processed(self, tweet_id: str, ai_agent: str) -> bool:
        """Check if a tweet has already been processed"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM tweets WHERE tweet_id = %s AND ai_agent = %s",
                (str(tweet_id), ai_agent),
            )
            return cursor.fetchone() is not None

    def get_latest_tweet_id_by_agent(self, ai_agent: str) -> str:
        """Get the latest tweet ID for an AI agent"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT tweet_id FROM tweets WHERE ai_agent = %s ORDER BY created_at DESC LIMIT 1",
                (ai_agent,),
            )
            result = cursor.fetchone()
            return result[0] if result else None

    def load_active_trades(self):
        """Load active trades from database"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=DictCursor)
                cursor.execute(
                    """
                    SELECT ticker, entry_price, timestamp, ai_agent,
                           contract_address, network, market_cap
                    FROM trades
                    WHERE status = 'Open'
                """
                )
                trades = cursor.fetchall()

                active_trades = []
                for trade in trades:
                    try:
                        entry_timestamp = datetime.strptime(
                            trade["timestamp"].strftime("%Y-%m-%d %H:%M:%S.%f"),
                            "%Y-%m-%d %H:%M:%S.%f",
                        )
                    except ValueError:
                        entry_timestamp = datetime.strptime(
                            trade["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                            "%Y-%m-%d %H:%M:%S",
                        )

                    active_trades.append(
                        {
                            "ticker": trade["ticker"],
                            "entry_price": float(trade["entry_price"]),
                            "entry_timestamp": entry_timestamp,
                            "ai_agent": trade["ai_agent"],
                            "contract_address": trade["contract_address"],
                            "network": trade["network"],
                            "market_cap": trade["market_cap"],
                            "status": "Open",
                        }
                    )

                return active_trades

        except Exception as e:
            logger.error(f"Error loading active trades: {str(e)}")
            return []

    def update_pnl_table(self, stats):
        """Update PNL table in database"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Clear existing PNL data
                cursor.execute("DELETE FROM pnl")

                # Insert new PNL data
                for stat in stats:
                    if stat["type"] == "trade":
                        cursor.execute(
                            """
                            INSERT INTO pnl (
                                ai_agent, ticker, entry_time, entry_price,
                                current_price, price_change_percentage,
                                invested_amount, current_value, pnl,
                                contract_address
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                stat["ai_agent"],
                                stat["ticker"],
                                stat["entry_time"],
                                stat["entry_price"],
                                stat["current_price"],
                                float(stat["price_change"].rstrip("%")),
                                stat["invested_amount"],
                                stat["current_value"],
                                stat["pnl_dollars"],
                                stat.get("contract_address", None),
                            ),
                        )

                conn.commit()

        except Exception as e:
            logger.error(f"Error updating PNL table: {str(e)}")
            raise

    def save_trade(self, trade_data):
        """Save trade information to the database"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO trades (
                        trade_id, ai_agent, timestamp, ticker, contract_address,
                        entry_price, position_size, direction, tweet_id,
                        status, notes, network, market_cap
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        trade_data["trade_id"],
                        trade_data["ai_agent"],
                        trade_data["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                        trade_data["ticker"],
                        trade_data["contract_address"],
                        trade_data["entry_price"],
                        trade_data["position_size"],
                        trade_data["direction"],
                        trade_data["tweet_id"],
                        trade_data["status"],
                        trade_data["notes"],
                        trade_data["network"],
                        trade_data["market_cap"],
                    ),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error saving trade to database: {str(e)}")
            return False

    def update_trade_exit(self, trade_data):
        """Update trade record with exit information"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                result = cursor.execute(
                    """
                    UPDATE trades
                    SET status = 'Closed',
                        exit_price = %s,
                        exit_timestamp = %s,
                        exit_reason = %s,
                        pnl_amount = %s,
                        pnl_percentage = %s,
                        trade_duration = %s,
                        notes = %s,
                        max_drawdown = %s,
                        max_profit = %s
                    WHERE ticker = %s
                    AND contract_address = %s
                    AND status = 'Open'
                    """,
                    (
                        trade_data["exit_price"],
                        trade_data["exit_timestamp"],
                        trade_data["exit_reason"],
                        trade_data["pnl_amount"],
                        trade_data["pnl_percentage"],
                        trade_data["trade_duration"],
                        trade_data["notes"],
                        trade_data["max_drawdown"],
                        trade_data["max_profit"],
                        trade_data["ticker"],
                        trade_data["contract_address"],
                    ),
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error in update_trade_exit: {str(e)}")
            return False

    def get_trade_statistics(self):
        """Get comprehensive trade statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            return cursor.execute(
                """
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN status = 'Closed' THEN 1 ELSE 0 END) as closed_trades,
                    SUM(CASE WHEN exit_reason = 'Stop Loss' THEN 1 ELSE 0 END) as stopped_trades,
                    AVG(CASE WHEN exit_reason = 'Stop Loss' THEN pnl_percentage ELSE NULL END) as avg_stop_loss_pnl,
                    AVG(CASE WHEN status = 'Closed' THEN pnl_percentage ELSE NULL END) as avg_closed_trade_pnl,
                    MIN(pnl_percentage) as worst_trade,
                    MAX(pnl_percentage) as best_trade,
                    AVG(max_drawdown) as avg_max_drawdown,
                    AVG(max_profit) as avg_max_profit
                FROM trades
            """
            ).fetchone()

    def get_exit_reason_distribution(self):
        """Get distribution of trade exit reasons"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            return cursor.execute(
                """
                SELECT
                    exit_reason,
                    COUNT(*) as count,
                    AVG(pnl_percentage) as avg_pnl,
                    AVG(trade_duration) as avg_duration
                FROM trades
                WHERE status = 'Closed'
                GROUP BY exit_reason
            """
            ).fetchall()

    def load_closed_trades(self):
        """Load closed trades from database"""
        try:
            with self.get_connection() as conn:
                # Use DictCursor to get results as dictionaries
                cursor = conn.cursor(cursor_factory=DictCursor)
                cursor.execute(
                    """
                    SELECT ticker, entry_price, timestamp as entry_timestamp,
                           ai_agent, contract_address, network,
                           exit_price, exit_timestamp, exit_reason,
                           pnl_amount, pnl_percentage, ath_price,
                           ath_timestamp, market_cap
                    FROM trades
                    WHERE status = 'Closed'
                    ORDER BY exit_timestamp DESC
                """
                )
                trades = cursor.fetchall()

                closed_trades = []
                for trade in trades:
                    try:
                        entry_timestamp = datetime.strptime(
                            trade["entry_timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                            "%Y-%m-%d %H:%M:%S",
                        )
                    except ValueError:
                        entry_timestamp = trade["entry_timestamp"]

                    try:
                        exit_timestamp = datetime.strptime(
                            trade["exit_timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                            "%Y-%m-%d %H:%M:%S",
                        )
                    except ValueError:
                        exit_timestamp = trade["exit_timestamp"]

                    closed_trades.append(
                        {
                            "type": "trade",
                            "ai_agent": trade["ai_agent"],
                            "ticker": trade["ticker"],
                            "contract_address": trade["contract_address"],
                            "network": trade["network"],
                            "market_cap": trade["market_cap"],
                            "entry_time": entry_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                            "entry_price": float(trade["entry_price"]),
                            "current_price": float(trade["exit_price"]),
                            "ath_price": (
                                float(trade["ath_price"])
                                if trade["ath_price"]
                                else float(trade["exit_price"])
                            ),
                            "ath_timestamp": trade["ath_timestamp"],
                            "price_change": f"{float(trade['pnl_percentage']):.2f}%",
                            "invested_amount": 100.0,
                            "current_value": 100.0
                            * (1 + float(trade["pnl_percentage"]) / 100),
                            "pnl_dollars": float(trade["pnl_amount"]),
                            "status": "Closed",
                            "exit_price": float(trade["exit_price"]),
                            "exit_timestamp": exit_timestamp,
                            "exit_reason": trade["exit_reason"],
                        }
                    )

                return closed_trades

        except Exception as e:
            logger.error(f"Error loading closed trades: {str(e)}")
            return []

    def get_active_user_trades_with_stop_loss(self):
        """Get all active user trades with stop loss set"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=DictCursor)
                cursor.execute(
                    """
                    SELECT
                        ut.id,
                        ut.user_id,
                        ut.token_address,
                        ut.chain,
                        ut.entry_price,
                        ut.stop_loss_price,
                        ut.quantity,
                        ut.status
                    FROM user_trades ut
                    WHERE ut.status = 'open'
                    AND ut.stop_loss_price IS NOT NULL
                """
                )
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error fetching user trades with stop loss: {str(e)}")
            return []

    def get_active_user_trades_with_take_profit(self):
        """Get all active user trades with take profit set"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=DictCursor)
                cursor.execute(
                    """
                    SELECT
                        ut.id,
                        ut.user_id,
                        ut.token_address,
                        ut.chain,
                        ut.entry_price,
                        ut.take_profit_price,
                        ut.take_profit_amount,
                        ut.quantity,
                        ut.status
                    FROM user_trades ut
                    WHERE ut.status = 'open'
                    AND ut.take_profit_price IS NOT NULL
                """
                )
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error fetching user trades with take profit: {str(e)}")
            return []
