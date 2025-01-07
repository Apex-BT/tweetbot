# apexbt/apexbt/trade/trade.py
import time
import threading
import logging
from dataclasses import dataclass
from typing import List
from datetime import datetime
import apexbt.database.database as db
from apexbt.crypto.codex import Codex

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TradePosition:
    ticker: str
    entry_price: float
    entry_timestamp: datetime
    ai_agent: str
    contract_address: str
    network: str
    status: str = "Open"


class TradeManager:
    def __init__(self, update_interval=60, historical=False):
        self.update_interval = update_interval
        self.historical = historical
        self.active_trades: List[TradePosition] = []
        self.is_running = False
        self.update_thread = None
        self.last_update = 0
        self.MIN_UPDATE_INTERVAL = 2
        self.sheets = None
        self.load_active_trades()

    def load_active_trades(self):
        """Load active trades from database"""
        trades = db.load_active_trades(self.historical)
        self.active_trades = [TradePosition(**trade) for trade in trades]
        logger.info(f"Loaded {len(self.active_trades)} active trades")

    def start_monitoring(self, sheets=None):
        """Start the monitoring thread with optional sheets connection"""
        self.sheets = sheets
        if not self.is_running:
            self.is_running = True
            self.update_thread = threading.Thread(target=self._monitor_trades)
            self.update_thread.start()
            logger.info("Trade monitoring started")

    def stop_monitoring(self):
        """Stop the monitoring thread"""
        self.is_running = False
        if self.update_thread:
            self.update_thread.join()
            logger.info("Trade monitoring stopped")

    def _monitor_trades(self):
        """Monitor trades and update prices periodically"""
        while self.is_running:
            try:
                self.update_trade_prices(sheets=self.sheets)
                time.sleep(self.update_interval)
            except Exception as e:
                logger.error(f"Error in trade monitoring: {str(e)}")
                time.sleep(60)

    def update_pnl(self, stats, sheets=None):
        """Update PNL in both database and Google Sheets"""
        # Update database
        db.update_pnl_table(stats, self.historical)

        # Update Google Sheets if available
        if sheets and "pnl" in sheets:
            from apexbt.sheets.sheets import update_pnl_sheet

            update_pnl_sheet(sheets["pnl"], stats)

    def update_trade_prices(self, sheets=None):
        """Update current prices and PNL in both database and sheets"""
        try:
            stats = []
            agent_totals = {}
            grand_total = {"invested_amount": 0, "current_value": 0, "pnl_dollars": 0}

            # Process trades by agent
            for trade in self.active_trades:
                price_data = Codex.get_crypto_price(
                    contract_address=trade.contract_address, network=trade.network
                )

                if price_data and price_data.get("price"):
                    current_price = float(price_data["price"])
                    price_change = (
                        (current_price - trade.entry_price) / trade.entry_price
                    ) * 100

                    invested_amount = 100.0
                    current_value = invested_amount * (1 + price_change / 100)
                    pnl = current_value - invested_amount

                    # Update agent totals
                    if trade.ai_agent not in agent_totals:
                        agent_totals[trade.ai_agent] = {
                            "invested_amount": 0,
                            "current_value": 0,
                            "pnl_dollars": 0,
                        }

                    agent_totals[trade.ai_agent]["invested_amount"] += invested_amount
                    agent_totals[trade.ai_agent]["current_value"] += current_value
                    agent_totals[trade.ai_agent]["pnl_dollars"] += pnl

                    # Add trade stats
                    stats.append(
                        {
                            "type": "trade",
                            "ai_agent": trade.ai_agent,
                            "ticker": trade.ticker,
                            "entry_time": trade.entry_timestamp.strftime(
                                "%Y-%m-%d %H:%M:%S"
                            ),
                            "entry_price": trade.entry_price,
                            "current_price": current_price,
                            "price_change": f"{price_change:.2f}%",
                            "invested_amount": invested_amount,
                            "current_value": current_value,
                            "pnl_dollars": pnl,
                            "contract_address": trade.contract_address,
                        }
                    )

            # Add agent totals
            for agent, totals in agent_totals.items():
                stats.append({"type": "agent_total", "agent": agent, **totals})
                grand_total["invested_amount"] += totals["invested_amount"]
                grand_total["current_value"] += totals["current_value"]
                grand_total["pnl_dollars"] += totals["pnl_dollars"]

            # Add grand total
            stats.append({"type": "grand_total", **grand_total})

            # Update both database and sheets ONCE after processing all trades
            self.sync_pnl_updates(stats, sheets)

            # Update agent summary if sheets available
            if sheets and "agent_summary" in sheets:
                from apexbt.sheets.sheets import update_agent_summary

                update_agent_summary(sheets["agent_summary"], stats)

        except Exception as e:
            logger.error(f"Error updating trade prices: {str(e)}")

    def sync_pnl_updates(self, stats, sheets=None):
        """Sync PNL updates to both database and sheets"""
        try:
            # Update database
            db.update_pnl_table(stats, self.historical)

            # Update Google Sheets if available
            if sheets and "pnl" in sheets:
                from apexbt.sheets.sheets import update_pnl_sheet

                update_pnl_sheet(sheets["pnl"], stats)

            self.last_update = time.time()
            logger.info("PNL updated successfully in both database and sheets")

            # Display stats in console
            self.display_stats(stats)

        except Exception as e:
            logger.error(f"Error syncing PNL updates: {str(e)}")

    def display_stats(self, stats):
        """Display current trading statistics in console"""
        print("\nCurrent Trading Statistics:")
        print("-" * 50)

        # Display individual trades
        for position in stats:
            if position["type"] == "trade":
                print(
                    f"{position['ai_agent']} - {position['ticker']}: {position['price_change']} "
                    f"(Entry: ${position['entry_price']:.8f}, Current: ${position['current_price']:.8f})"
                )

        # Display totals by agent
        print("\nAgent Totals:")
        for position in stats:
            if position["type"] == "agent_total":
                print(f"{position['agent']}: ${position['pnl_dollars']:.2f}")

        # Display grand total
        for position in stats:
            if position["type"] == "grand_total":
                print(f"\nTotal Portfolio PNL: ${position['pnl_dollars']:.2f}")
        print("-" * 50)

    def get_current_stats(self):
        """Get current statistics from database"""
        try:
            with db.get_db_connection(self.historical) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM pnl ORDER BY ai_agent, ticker")
                rows = cursor.fetchall()

                stats = []
                current_agent = None
                agent_totals = {
                    "invested_amount": 0,
                    "current_value": 0,
                    "pnl_dollars": 0,
                }

                for row in rows:
                    stats.append(
                        {
                            "type": "trade",
                            "ai_agent": row["ai_agent"],
                            "ticker": row["ticker"],
                            "contract_address": row["contract_address"],
                            "entry_time": row["entry_time"],
                            "entry_price": row["entry_price"],
                            "current_price": row["current_price"],
                            "price_change": f"{row['price_change_percentage']:.2f}%",
                            "invested_amount": row["invested_amount"],
                            "current_value": row["current_value"],
                            "pnl_dollars": row["pnl"],
                        }
                    )

                return stats

        except Exception as e:
            logger.error(f"Error getting current stats: {str(e)}")
            return []

    def has_open_trade(self, ticker: str) -> bool:
        """Check if there's already an open trade for the given ticker"""
        return any(
            trade.ticker.lower() == ticker.lower() and trade.status == "Open"
            for trade in self.active_trades
        )

    def add_trade(
        self,
        ticker: str,
        contract_address: str,
        tweet_id: str,
        entry_price: float,
        ai_agent: str,
        network: str = "ethereum",
        entry_timestamp: datetime = None,
    ) -> bool:
        """Add a new trade to both database and sheets"""
        if self.has_open_trade(ticker):
            logger.warning(f"Trade for {ticker} already exists - skipping")
            return False

        if entry_timestamp is None:
            entry_timestamp = datetime.now()

        trade_data = {
            "trade_id": f"T{entry_timestamp.strftime('%Y%m%d%H%M%S%f')}",
            "ai_agent": ai_agent,
            "timestamp": entry_timestamp,
            "ticker": ticker,
            "contract_address": contract_address,
            "network": network,
            "entry_price": entry_price,
            "position_size": 100.0,
            "direction": "Long",
            "tweet_id": tweet_id,
            "status": "Open",
            "notes": "Auto trade based on tweet signal",
        }

        # Save to database
        success = db.save_trade(trade_data, self.historical)

        # Save to sheets if available
        if success and self.sheets and "trades" in self.sheets:
            from apexbt.sheets.sheets import save_trade as save_trade_to_sheets

            save_trade_to_sheets(
                self.sheets["trades"], trade_data, self.sheets.get("pnl")
            )

        if success:
            self.active_trades.append(
                TradePosition(
                    ticker=ticker,
                    entry_price=entry_price,
                    entry_timestamp=entry_timestamp,
                    status="Open",
                    ai_agent=ai_agent,
                    contract_address=contract_address,
                    network=network,
                )
            )

        return success
