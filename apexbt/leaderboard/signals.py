"""
SignalRecorder — saves token mentions from AI agents as trackable signals.

Each signal records: who called it, what token, at what price, and when.
Prices are fetched from DexScreener (free, no API key needed).
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any

import psycopg2
from psycopg2.extras import RealDictCursor

from apexbt.config.config import config
from apexbt.crypto.dexscreener import DexScreener

logger = logging.getLogger(__name__)


class SignalRecorder:
    """Records token signals from AI agents into the database."""

    def __init__(self):
        self.db_url = config.DATABASE_URL
        self.dex = DexScreener()

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    def _get_conn(self):
        return psycopg2.connect(self.db_url, cursor_factory=RealDictCursor)

    def _execute(self, query: str, params=None, fetch_one=False, fetch_all=False):
        conn = self._get_conn()
        cur = conn.cursor()
        try:
            cur.execute(query, params)
            if fetch_one:
                result = cur.fetchone()
            elif fetch_all:
                result = cur.fetchall()
            else:
                result = None
            conn.commit()
            return result
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cur.close()
            conn.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_signal(
        self,
        agent: str,
        tweet_id: str,
        tweet_text: str,
        ticker: str,
        contract_address: str,
        chain: str,
        entry_price: float,
        market_cap: float = None,
        volume_24h: float = None,
        liquidity: float = None,
        sentiment: str = None,
        sentiment_confidence: float = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Record a new signal in the database.

        Returns the inserted row dict, or None if it was a duplicate / error.
        """
        if not entry_price or entry_price <= 0:
            logger.warning(f"Skipping signal for {ticker} — invalid price {entry_price}")
            return None

        try:
            row = self._execute(
                """
                INSERT INTO signals (
                    agent, tweet_id, tweet_text, ticker,
                    contract_address, chain, entry_price, entry_time,
                    current_price, market_cap, volume_24h, liquidity,
                    sentiment, sentiment_confidence
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s
                )
                ON CONFLICT (tweet_id) DO NOTHING
                RETURNING *;
                """,
                (
                    agent,
                    str(tweet_id),
                    tweet_text,
                    ticker.upper(),
                    contract_address,
                    chain,
                    entry_price,
                    datetime.utcnow(),
                    entry_price,  # current_price starts as entry
                    market_cap,
                    volume_24h,
                    liquidity,
                    sentiment,
                    sentiment_confidence,
                ),
                fetch_one=True,
            )

            if row:
                logger.info(
                    f"📡 Signal recorded: {agent} → ${ticker} at ${entry_price:.8g} "
                    f"(chain={chain}, mc={market_cap})"
                )
                return dict(row)
            else:
                logger.debug(f"Duplicate signal skipped: {tweet_id}")
                return None

        except Exception as e:
            logger.error(f"Error recording signal: {e}")
            return None

    def record_signal_from_dex_data(
        self,
        agent: str,
        tweet_id: str,
        tweet_text: str,
        ticker: str,
        dex_data: Dict[str, Any],
        sentiment: str = None,
        sentiment_confidence: float = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Convenience method: record a signal using a DexScreener data dict
        (the format returned by DexScreener.get_token_by_ticker / get_token_by_address).
        """
        if not dex_data:
            logger.warning(f"No dex data for {ticker}, cannot record signal")
            return None

        return self.record_signal(
            agent=agent,
            tweet_id=tweet_id,
            tweet_text=tweet_text,
            ticker=ticker,
            contract_address=dex_data.get("contract_address", ""),
            chain=dex_data.get("network", "unknown"),
            entry_price=float(dex_data.get("current_price", 0)),
            market_cap=dex_data.get("market_cap"),
            volume_24h=dex_data.get("volume_24h"),
            liquidity=dex_data.get("liquidity"),
            sentiment=sentiment,
            sentiment_confidence=sentiment_confidence,
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_active_signals(self) -> list:
        """Get all signals that are still being tracked."""
        return self._execute(
            """
            SELECT * FROM signals
            WHERE status = 'active'
            ORDER BY entry_time DESC;
            """,
            fetch_all=True,
        ) or []

    def get_signals_by_agent(self, agent: str) -> list:
        """Get all signals for a specific agent."""
        return self._execute(
            """
            SELECT * FROM signals
            WHERE agent = %s
            ORDER BY entry_time DESC;
            """,
            (agent,),
            fetch_all=True,
        ) or []

    def get_signal_by_tweet_id(self, tweet_id: str) -> Optional[Dict]:
        """Look up a signal by its originating tweet."""
        return self._execute(
            "SELECT * FROM signals WHERE tweet_id = %s;",
            (str(tweet_id),),
            fetch_one=True,
        )

    def get_all_agents(self) -> list:
        """Get a list of all unique agents that have recorded signals."""
        rows = self._execute(
            "SELECT DISTINCT agent FROM signals ORDER BY agent;",
            fetch_all=True,
        ) or []
        return [r["agent"] for r in rows]

    def get_signal_count(self) -> int:
        """Total number of signals recorded."""
        row = self._execute("SELECT COUNT(*) as cnt FROM signals;", fetch_one=True)
        return row["cnt"] if row else 0

    def is_duplicate(self, tweet_id: str) -> bool:
        """Check if a signal for this tweet already exists."""
        row = self._execute(
            "SELECT 1 FROM signals WHERE tweet_id = %s LIMIT 1;",
            (str(tweet_id),),
            fetch_one=True,
        )
        return row is not None

    def mark_signal_closed(self, signal_id: int, reason: str = "manual") -> None:
        """Mark a signal as closed (e.g. token rugged, too old, etc.)."""
        self._execute(
            "UPDATE signals SET status = %s WHERE id = %s;",
            (f"closed:{reason}", signal_id),
        )
        logger.info(f"Signal {signal_id} closed (reason={reason})")

    def update_signal_price(
        self,
        signal_id: int,
        current_price: float,
        pnl_percent: float,
    ) -> None:
        """Update the current price and PNL for a signal (called by PriceTracker)."""
        self._execute(
            """
            UPDATE signals
            SET current_price = %s,
                pnl_percent = %s,
                price_updated_at = %s
            WHERE id = %s;
            """,
            (current_price, pnl_percent, datetime.utcnow(), signal_id),
        )

    def save_snapshot(
        self,
        signal_id: int,
        current_price: float,
        pnl_percent: float,
        hours_since_signal: float,
    ) -> None:
        """Save a price snapshot for historical tracking."""
        self._execute(
            """
            INSERT INTO signal_snapshots
                (signal_id, current_price, pnl_percent, hours_since_signal)
            VALUES (%s, %s, %s, %s);
            """,
            (signal_id, current_price, pnl_percent, hours_since_signal),
        )
