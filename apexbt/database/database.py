# apexbt/apexbt/database/database.py
import sqlite3
from datetime import datetime
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DATABASE_PATH = "apexbt.db"

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_database():
    """Initialize the database with required tables"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Create tweets table
        cursor.execute('''
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
        ''')

        # Create trades table
        cursor.execute('''
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
            pnl_amount REAL,
            pnl_percentage REAL,
            notes TEXT,
            FOREIGN KEY(tweet_id) REFERENCES tweets(tweet_id)
        )
        ''')

        # Create PNL table with contract_address
        cursor.execute('''
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
        ''')

        conn.commit()

def save_tweet(tweet, ticker, ticker_status, price_data, ai_agent):
    """Save tweet to database"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO tweets (
                tweet_id, ai_agent, text, created_at, timestamp, ticker,
                ticker_status, current_price, tweet_time_price, volume_24h,
                liquidity, price_change_24h, dex, network, trading_pair,
                contract_address, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
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
                price_data.get("last_updated") if price_data else None
            ))
            conn.commit()
            logger.info(f"Tweet saved to database: {tweet.id}")
    except Exception as e:
        logger.error(f"Error saving tweet to database: {str(e)}")

def save_trade(trade_data):
    """Save trade to database"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO trades (
                trade_id, ai_agent, timestamp, ticker, entry_price,
                position_size, direction, stop_loss, take_profit,
                tweet_id, status, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                trade_data["trade_id"],
                trade_data["ai_agent"],
                trade_data["timestamp"],
                trade_data["ticker"],
                trade_data["entry_price"],
                trade_data["position_size"],
                trade_data["direction"],
                trade_data["stop_loss"],
                trade_data["take_profit"],
                trade_data["tweet_id"],
                "Open",
                trade_data["notes"]
            ))
            conn.commit()
            logger.info(f"Trade saved to database: {trade_data['trade_id']}")
    except Exception as e:
        logger.error(f"Error saving trade to database: {str(e)}")

def is_tweet_processed(tweet_id: str, ai_agent: str) -> bool:
    """Check if a tweet has already been processed"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM tweets WHERE tweet_id = ? AND ai_agent = ?",
            (str(tweet_id), ai_agent)
        )
        return cursor.fetchone() is not None

def get_latest_tweet_id_by_agent(ai_agent: str) -> str:
    """Get the latest tweet ID for an AI agent"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT tweet_id FROM tweets WHERE ai_agent = ? ORDER BY created_at DESC LIMIT 1",
            (ai_agent,)
        )
        result = cursor.fetchone()
        return result[0] if result else None
