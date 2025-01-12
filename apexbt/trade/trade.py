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
    ath_price: float = None
    ath_timestamp: datetime = None
    stop_loss: float = None

    def __post_init__(self):
        # Initialize ATH with entry price if not set
        if self.ath_price is None:
            self.ath_price = self.entry_price
        if self.ath_timestamp is None:
            self.ath_timestamp = self.entry_timestamp
        self.update_stop_loss()

    def update_ath(self, current_price: float, current_time: datetime) -> bool:
            """Update ATH and stop loss if current price is higher"""
            if current_price > self.ath_price:
                self.ath_price = current_price
                self.ath_timestamp = current_time
                self.update_stop_loss()
                return True
            return False

    def update_stop_loss(self):
            """Calculate stop loss as 75% of ATH price (25% below ATH)"""
            self.stop_loss = self.ath_price * 0.75

    def check_stop_loss(self, current_price: float) -> bool:
            """Check if current price has hit stop loss"""
            return current_price <= self.stop_loss


class TradeManager:
    def __init__(self, update_interval=300, historical=False):
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
            current_time = datetime.now()

            # Track trades that need updating in sheets
            trades_to_update = []

            # Process trades by agent
            for trade in self.active_trades:
                price_data = Codex.get_crypto_price(
                    contract_address=trade.contract_address, network=trade.network
                )

                if price_data and price_data.get("price"):
                    current_price = float(price_data["price"])

                    # Check stop loss
                    if trade.check_stop_loss(current_price):
                        logger.warning(
                            f"🚨 STOP LOSS ALERT: {trade.ticker} has hit stop loss at ${current_price:.8f}"
                            f" (Stop Loss: ${trade.stop_loss:.8f}, ATH: ${trade.ath_price:.8f})"
                        )

                    # Check and update ATH if necessary
                    ath_updated = trade.update_ath(current_price, current_time)
                    if ath_updated:
                        # Update ATH in database
                        self.update_trade_ath_and_stop_loss(
                            trade.ticker,
                            trade.contract_address,
                            trade.ath_price,
                            trade.ath_timestamp,
                            trade.stop_loss
                        )
                        logger.info(
                            f"New ATH for {trade.ticker}: ${trade.ath_price:.8f}, "
                            f"New Stop Loss: ${trade.stop_loss:.8f}"
                        )
                        # Add to trades that need updating in sheets
                        trades_to_update.append({
                            'ticker': trade.ticker,
                            'contract_address': trade.contract_address,
                            'ath_price': trade.ath_price,
                            'ath_timestamp': trade.ath_timestamp,
                            'stop_loss': trade.stop_loss
                        })

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
                            "ath_price": trade.ath_price,
                            "ath_timestamp": trade.ath_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
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

            # Update trades worksheet if needed
            if trades_to_update and sheets and "trades" in sheets:
                from apexbt.sheets.sheets import update_trades_worksheet
                update_trades_worksheet(sheets["trades"], trades_to_update)

            # Update agent summary if sheets available
            if sheets and "agent_summary" in sheets:
                from apexbt.sheets.sheets import update_agent_summary

                update_agent_summary(sheets["agent_summary"], stats)

        except Exception as e:
            logger.error(f"Error updating trade prices: {str(e)}")

    def update_trade_ath_and_stop_loss(self, ticker: str, contract_address: str,
                                      ath_price: float, ath_timestamp: datetime,
                                      stop_loss: float):
        """Update ATH and stop loss values in database"""
        try:
            with db.get_db_connection(self.historical) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE trades
                    SET ath_price = ?, ath_timestamp = ?, stop_loss = ?
                    WHERE ticker = ? AND contract_address = ? AND status = 'Open'
                """, (ath_price, ath_timestamp, stop_loss, ticker, contract_address))
                conn.commit()
        except Exception as e:
            logger.error(f"Error updating trade ATH and stop loss: {str(e)}")

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
        print("-" * 100)  # Made wider to accommodate more info

        # Display individual trades with ATH and Stop Loss
        print("Individual Trades:")
        print(f"{'AI Agent':<12} {'Ticker':<10} {'Current':<12} {'ATH':<12} {'Stop Loss':<12} {'Entry':<12} {'Change':<8} {'From ATH':<8} {'To SL':<8}")
        print("-" * 100)

        for position in stats:
            if position["type"] == "trade":
                current_price = position['current_price']
                ath_price = position['ath_price']
                stop_loss = ath_price * 0.75  # 25% below ATH
                from_ath = ((current_price - ath_price) / ath_price * 100) if ath_price else 0
                to_stop_loss = ((current_price - stop_loss) / current_price * 100)

                print(
                    f"{position['ai_agent']:<12} "
                    f"{position['ticker']:<10} "
                    f"${current_price:<11.8f} "
                    f"${ath_price:<11.8f} "
                    f"${stop_loss:<11.8f} "
                    f"${position['entry_price']:<11.8f} "
                    f"{position['price_change']:<8} "
                    f"{from_ath:>7.2f}% "
                    f"{to_stop_loss:>7.2f}%"
                )

        # Display totals by agent
        print("\nAgent Totals:")
        print("-" * 40)
        for position in stats:
            if position["type"] == "agent_total":
                print(f"{position['agent']}: ${position['pnl_dollars']:.2f}")

        # Display grand total
        print("\nPortfolio Summary:")
        print("-" * 40)
        for position in stats:
            if position["type"] == "grand_total":
                print(f"Total Portfolio PNL: ${position['pnl_dollars']:.2f}")
        print("-" * 80)

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

        # Initialize ATH with entry price
        ath_price = entry_price
        ath_timestamp = entry_timestamp
        stop_loss = ath_price * 0.75  # 25% below ATH

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
            "ath_price": ath_price,
            "ath_timestamp": ath_timestamp,
            "stop_loss": stop_loss,
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
