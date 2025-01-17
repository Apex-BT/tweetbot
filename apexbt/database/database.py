# apexbt/apexbt/database/database.py
from apexbt.config.config import DATABASE_PATH, HISTORICAL_DATABASE_PATH
import sqlite3
from datetime import datetime
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@contextmanager
def get_db_connection(historical=False):
    """Get database connection with context manager"""
    db_path = HISTORICAL_DATABASE_PATH if historical else DATABASE_PATH
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_database(historical=False):
    """Initialize the database with required tables"""
    with get_db_connection(historical) as conn:
        cursor = conn.cursor()

        # Create tweets table
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
            current_price REAL,
            tweet_time_price REAL,
            volume_24h REAL,
            liquidity REAL,
            price_change_24h REAL,
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
            entry_price REAL,
            position_size REAL,
            direction TEXT,
            stop_loss REAL,
            take_profit REAL,
            tweet_id TEXT,
            status TEXT,
            exit_price REAL,
            exit_timestamp TIMESTAMP,
            exit_reason TEXT,
            pnl_amount REAL,
            pnl_percentage REAL,
            notes TEXT,
            contract_address TEXT,
            network TEXT,
            ath_price REAL,
            ath_timestamp TIMESTAMP,
            trade_duration TEXT,
            max_drawdown REAL,
            max_profit REAL,
            market_cap REAL,
            FOREIGN KEY(tweet_id) REFERENCES tweets(tweet_id)
        )
        """
        )

        # Create PNL table with contract_address
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS pnl (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ai_agent TEXT,
            ticker TEXT,
            entry_time TIMESTAMP,
            entry_price REAL,
            current_price REAL,
            price_change_percentage REAL,
            invested_amount REAL,
            current_value REAL,
            pnl REAL,
            contract_address TEXT
        )
        """
        )

        conn.commit()


def save_tweet(tweet, ticker, ticker_status, price_data, ai_agent, historical=False):
    """Save tweet to database"""
    try:
        with get_db_connection(historical) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
            INSERT INTO tweets (
                tweet_id, ai_agent, text, created_at, timestamp, ticker,
                ticker_status, current_price, tweet_time_price, volume_24h,
                liquidity, price_change_24h, dex, network, trading_pair,
                contract_address, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def is_tweet_processed(tweet_id: str, ai_agent: str, historical=False) -> bool:
    """Check if a tweet has already been processed"""
    with get_db_connection(historical) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM tweets WHERE tweet_id = ? AND ai_agent = ?",
            (str(tweet_id), ai_agent),
        )
        return cursor.fetchone() is not None


def get_latest_tweet_id_by_agent(ai_agent: str, historical=False) -> str:
    """Get the latest tweet ID for an AI agent"""
    with get_db_connection(historical) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT tweet_id FROM tweets WHERE ai_agent = ? ORDER BY created_at DESC LIMIT 1",
            (ai_agent,),
        )
        result = cursor.fetchone()
        return result[0] if result else None


def load_active_trades(historical=False):
    """Load active trades from database"""
    try:
        with get_db_connection(historical) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT ticker, entry_price, timestamp, ai_agent,
                       contract_address, network
                FROM trades
                WHERE status = 'Open'
            """
            )
            trades = cursor.fetchall()

            active_trades = []
            for trade in trades:
                try:
                    entry_timestamp = datetime.strptime(
                        trade["timestamp"], "%Y-%m-%d %H:%M:%S.%f"
                    )
                except ValueError:
                    entry_timestamp = datetime.strptime(
                        trade["timestamp"], "%Y-%m-%d %H:%M:%S"
                    )

                active_trades.append(
                    {
                        "ticker": trade["ticker"],
                        "entry_price": float(trade["entry_price"]),
                        "entry_timestamp": entry_timestamp,
                        "ai_agent": trade["ai_agent"],
                        "contract_address": trade["contract_address"],
                        "network": trade["network"],  # Add network
                        "status": "Open",
                    }
                )

            return active_trades

    except Exception as e:
        logger.error(f"Error loading active trades: {str(e)}")
        return []


def update_pnl_table(stats, historical=False):
    """Update PNL table in database"""
    try:
        with get_db_connection(historical) as conn:
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
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def save_trade(trade_data, historical=False):
    """Save trade information to the database"""
    try:
        with get_db_connection(historical) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trades (
                    trade_id, ai_agent, timestamp, ticker, contract_address,
                    entry_price, position_size, direction, tweet_id,
                    status, notes, network, market_cap
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def update_trade_exit(conn, trade_data):
    """Update trade record with exit information"""
    try:
        cursor = conn.cursor()
        result = cursor.execute(
            """
            UPDATE trades
            SET status = 'Closed',
                exit_price = ?,
                exit_timestamp = ?,
                exit_reason = ?,
                pnl_amount = ?,
                pnl_percentage = ?,
                trade_duration = ?,
                notes = ?,
                max_drawdown = ?,
                max_profit = ?
            WHERE ticker = ?
            AND contract_address = ?
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


def get_trade_statistics(historical=False):
    """Get comprehensive trade statistics"""
    with get_db_connection(historical) as conn:
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


def get_exit_reason_distribution(historical=False):
    """Get distribution of trade exit reasons"""
    with get_db_connection(historical) as conn:
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
