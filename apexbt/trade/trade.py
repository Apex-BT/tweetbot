# apexbt/apexbt/trade/trade.py
import time
import threading
import logging
from dataclasses import dataclass
from typing import List
from datetime import datetime
import apexbt.database.database as db
from apexbt.crypto.codex import Codex
from config.config import STOP_LOSS_PERCENTAGE

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
    market_cap: float = None

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
        """Calculate stop loss based on ATH price"""
        self.stop_loss = self.ath_price * STOP_LOSS_PERCENTAGE

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
        self.telegram_manager = None
        self.signal_api = None
        self.load_active_trades()

    def set_signal_api(self, signal_api):
        self.signal_api = signal_api

    def set_telegram_manager(self, telegram_manager):
        self.telegram_manager = telegram_manager

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
            trades_to_exit = []

            # Get closed trades first
            closed_trades = db.load_closed_trades(self.historical)

            # Process all active trades first before any updates
            trades_to_process = self.active_trades.copy()

            for trade in trades_to_process:
                price_data = Codex.get_crypto_price(
                    contract_address=trade.contract_address, network=trade.network
                )

                if price_data and price_data.get("price"):
                    current_price = float(price_data["price"])

                    # Check stop loss
                    if trade.check_stop_loss(current_price):
                        trades_to_exit.append(
                            {
                                "ticker": trade.ticker,
                                "contract_address": trade.contract_address,
                                "entry_price": trade.entry_price,
                                "exit_price": current_price,
                                "stop_loss": trade.stop_loss,
                                "ath_price": trade.ath_price,
                                "pnl_amount": 100
                                * ((current_price / trade.entry_price) - 1),
                                "pnl_percentage": (
                                    (current_price / trade.entry_price) - 1
                                )
                                * 100,
                                "ai_agent": trade.ai_agent,
                                "network": trade.network,
                                "duration": current_time - trade.entry_timestamp,
                            }
                        )
                        continue

                    # Check and update ATH if necessary
                    ath_updated = trade.update_ath(current_price, current_time)
                    if ath_updated:
                        trades_to_update.append(
                            {
                                "ticker": trade.ticker,
                                "contract_address": trade.contract_address,
                                "ath_price": trade.ath_price,
                                "ath_timestamp": trade.ath_timestamp,
                                "stop_loss": trade.stop_loss,
                            }
                        )

                    # Calculate statistics
                    price_change = (
                        (current_price - trade.entry_price) / trade.entry_price
                    ) * 100
                    invested_amount = 100.0
                    current_value = invested_amount * (1 + price_change / 100)
                    pnl = current_value - invested_amount

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
                            "ath_timestamp": trade.ath_timestamp.strftime(
                                "%Y-%m-%d %H:%M:%S"
                            ),
                            "price_change": f"{price_change:.2f}%",
                            "invested_amount": invested_amount,
                            "current_value": current_value,
                            "pnl_dollars": pnl,
                            "contract_address": trade.contract_address,
                            "status": "Open",
                        }
                    )

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

            # Add closed trades to stats
            stats.extend(closed_trades)

            # Update agent totals with closed trades
            for trade in closed_trades:
                agent = trade["ai_agent"]
                if agent not in agent_totals:
                    agent_totals[agent] = {
                        "invested_amount": 0,
                        "current_value": 0,
                        "pnl_dollars": 0,
                    }
                agent_totals[agent]["invested_amount"] += trade["invested_amount"]
                agent_totals[agent]["current_value"] += trade["current_value"]
                agent_totals[agent]["pnl_dollars"] += trade["pnl_dollars"]

            # Process any trades that need to be exited
            for trade in trades_to_exit:
                self.exit_trade(
                    next(t for t in trades_to_process if t.ticker == trade["ticker"]),
                    trade["exit_price"],
                    "Stop Loss",
                )

            # Add agent totals to stats
            for agent, totals in agent_totals.items():
                stats.append({"type": "agent_total", "agent": agent, **totals})
                grand_total["invested_amount"] += totals["invested_amount"]
                grand_total["current_value"] += totals["current_value"]
                grand_total["pnl_dollars"] += totals["pnl_dollars"]

            # Add grand total
            stats.append({"type": "grand_total", **grand_total})

            # Single update to PNL
            self.sync_pnl_updates(stats, sheets)

            # Update trades worksheet if needed
            if trades_to_update and self.sheets and "trades" in self.sheets:
                from apexbt.sheets.sheets import update_trades_worksheet

                update_trades_worksheet(self.sheets["trades"], trades_to_update)

            # Update agent summary if sheets available
            if sheets and "agent_summary" in sheets:
                from apexbt.sheets.sheets import update_agent_summary

                update_agent_summary(sheets["agent_summary"], stats)

        except Exception as e:
            logger.error(f"Error updating trade prices: {str(e)}")
            logger.exception("Full traceback:")

    def send_trade_notification(
        self,
        ticker: str,
        contract_address: str,
        entry_price: float,
        ai_agent: str,
        network: str,
        market_cap: float = None,
    ):
        """Send notification for new trade via Telegram"""
        if self.historical:
            return

        try:
            if self.telegram_manager:
                # Format market cap to be more readable
                market_cap_str = ""
                if market_cap:
                    if market_cap >= 1_000_000:
                        market_cap_str = f"${market_cap/1_000_000:.2f}M"
                    else:
                        market_cap_str = f"${market_cap:.2f}"

                message = (
                    f"🔥 New signal just dropped 💥\n\n"
                    f"Token: <code>${ticker}</code>\n"
                    f"Chain: <code>{network.lower()}</code>\n"
                    f"CA: <code>{contract_address}</code>\n"
                    f"Current price: <code>${entry_price:.8f}</code>"
                )

                if market_cap_str:
                    message += f"\nCurrent MC: <code>{market_cap_str}</code>"

                self.telegram_manager.send_message(message)
                logger.info(f"Trade notification sent for {ticker}")
        except Exception as e:
            logger.error(f"Error sending trade notification: {str(e)}")

    def notify_trade_exit(self, trade_data):
        """Send notification for trade exit via Telegram"""
        if self.historical:
            return

        try:
            duration_str = str(trade_data["duration"]).split(".")[
                0
            ]  # Remove microseconds
            message = (
                f"💀 Position Closed 💀\n\n"
                f"Token: <code>${trade_data['ticker']}</code>\n"
                f"Chain: <code>{trade_data['network'].lower()}</code>\n"
                f"CA: <code>{trade_data['contract_address']}</code>\n"
                f"Exit price: <code>${trade_data['exit_price']:.8f}</code>\n"
                f"PNL: <code>{trade_data['pnl_percentage']:.2f}%</code>\n"
                f"Duration: <code>{duration_str}</code>"
            )

            if hasattr(self, "telegram_manager"):
                self.telegram_manager.send_message(message)

        except Exception as e:
            logger.error(f"Error sending trade exit notification: {str(e)}")

    def send_trade_signal(
        self,
        ticker: str,
        contract_address: str,
        entry_price: float,
        signal_from: str,
        network: str,
        market_cap: float = None,  # Add market_cap parameter
    ):
        """Send trade signal to signal bot"""
        if self.historical:
            return

        try:
            if self.signal_api:
                logger.info(f"Sending signal for {ticker} to signal bot...")
                signal_response = self.signal_api.send_signal(
                    token=ticker,
                    contract=contract_address,
                    entry_price=entry_price,
                    signal_from=signal_from,
                    chain=network,
                    market_cap=market_cap,  # Add market_cap
                )
                logger.info(f"Signal API response: {signal_response}")
                return signal_response
            else:
                logger.warning("Signal API not configured")
                return None
        except Exception as e:
            logger.error(f"Error sending trade signal: {str(e)}")
            return None

    def update_trade_ath_and_stop_loss(
        self,
        ticker: str,
        contract_address: str,
        ath_price: float,
        ath_timestamp: datetime,
        stop_loss: float,
    ):
        """Update ATH and stop loss values in database"""
        try:
            with db.get_db_connection(self.historical) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE trades
                    SET ath_price = ?, ath_timestamp = ?, stop_loss = ?
                    WHERE ticker = ? AND contract_address = ? AND status = 'Open'
                """,
                    (ath_price, ath_timestamp, stop_loss, ticker, contract_address),
                )
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
        """Display current trading statistics using logger"""
        logger.info("\nCurrent Trading Statistics:")
        logger.info("-" * 120)

        # Display individual trades with ATH and Stop Loss
        logger.info("Individual Trades:")
        logger.info(
            f"{'AI Agent':<12} {'Ticker':<10} {'Current':<12} {'ATH':<12} {'Stop Loss':<12} "
            f"{'Entry':<12} {'Change':<8} {'From ATH':<8} {'To SL':<8} {'MC':<10}"
        )
        logger.info("-" * 120)

        for position in stats:
            if position["type"] == "trade":
                current_price = position["current_price"]
                ath_price = position["ath_price"]
                stop_loss = ath_price * STOP_LOSS_PERCENTAGE
                from_ath = ((current_price - ath_price) / ath_price * 100) if ath_price else 0
                to_stop_loss = (current_price - stop_loss) / current_price * 100

                # Format market cap
                market_cap_str = ""
                if "market_cap" in position and position["market_cap"]:
                    if position["market_cap"] >= 1_000_000:
                        market_cap_str = f"${position['market_cap']/1_000_000:.2f}M"
                    else:
                        market_cap_str = f"${position['market_cap']:.2f}"

                logger.info(
                    f"{position['ai_agent']:<12} "
                    f"{position['ticker']:<10} "
                    f"${current_price:<11.8f} "
                    f"${ath_price:<11.8f} "
                    f"${stop_loss:<11.8f} "
                    f"${position['entry_price']:<11.8f} "
                    f"{position['price_change']:<8} "
                    f"{from_ath:>7.2f}% "
                    f"{to_stop_loss:>7.2f}% "
                    f"{market_cap_str:<10}"
                )

        # Display totals by agent
        logger.info("\nAgent Totals:")
        logger.info("-" * 40)
        for position in stats:
            if position["type"] == "agent_total":
                logger.info(f"{position['agent']}: ${position['pnl_dollars']:.2f}")

        # Display grand total
        logger.info("\nPortfolio Summary:")
        logger.info("-" * 40)
        for position in stats:
            if position["type"] == "grand_total":
                logger.info(f"Total Portfolio PNL: ${position['pnl_dollars']:.2f}")
        logger.info("-" * 80)

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
        market_cap: float = None,
    ) -> bool:
        """Add a new trade, send notification and signal"""
        if self.has_open_trade(ticker):
            logger.warning(f"Trade for {ticker} already exists - skipping")
            return False

        if entry_timestamp is None:
            entry_timestamp = datetime.now()

        # Ensure timestamp is timezone-naive
        entry_timestamp = entry_timestamp.replace(tzinfo=None)

        # Initialize ATH with entry price
        ath_price = entry_price
        ath_timestamp = entry_timestamp
        stop_loss = ath_price * STOP_LOSS_PERCENTAGE

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
            "market_cap": market_cap,
        }

        # Save to database
        success = db.save_trade(trade_data, self.historical)

        if success:
            # Save to sheets if available
            if self.sheets and "trades" in self.sheets:
                from apexbt.sheets.sheets import save_trade as save_trade_to_sheets

                save_trade_to_sheets(
                    self.sheets["trades"], trade_data, self.sheets.get("pnl")
                )

            # Add to active trades
            self.active_trades.append(
                TradePosition(
                    ticker=ticker,
                    entry_price=entry_price,
                    entry_timestamp=entry_timestamp,
                    status="Open",
                    ai_agent=ai_agent,
                    contract_address=contract_address,
                    network=network,
                    market_cap=market_cap
                )
            )

            # Only send signals if not historical
            if not self.historical:
                # Send signal to signal bot
                self.send_trade_signal(
                    ticker=ticker,
                    contract_address=contract_address,
                    entry_price=entry_price,
                    signal_from=ai_agent,
                    network=network,
                    market_cap=market_cap,
                )

        return success

    def exit_trade(
        self, trade: TradePosition, exit_price: float, exit_reason: str = "Stop Loss"
    ) -> bool:
        """
        Exit a trade with enhanced tracking of exit statistics
        """
        try:
            # Ensure both datetimes are timezone-naive
            exit_timestamp = datetime.now().replace(tzinfo=None)
            entry_timestamp = trade.entry_timestamp
            if entry_timestamp.tzinfo:
                entry_timestamp = entry_timestamp.replace(tzinfo=None)

            # Calculate trade duration with consistent timezone-naive datetimes
            trade_duration = exit_timestamp - entry_timestamp

            # Rest of the code remains the same
            pnl_amount = 100 * ((exit_price / trade.entry_price) - 1)
            pnl_percentage = ((exit_price / trade.entry_price) - 1) * 100

            max_drawdown = (
                (trade.ath_price - min(trade.ath_price, exit_price)) / trade.ath_price
            ) * 100
            max_profit = (
                (trade.ath_price - trade.entry_price) / trade.entry_price
            ) * 100

            # Send sell signal if not in historical mode
            if not self.historical and self.signal_api:
                res = self.signal_api.send_signal(
                    token=trade.ticker,
                    contract=trade.contract_address,
                    entry_price=exit_price,
                    signal_from=trade.ai_agent,
                    chain=trade.network,
                    tx_type="sell",
                    market_cap=trade.market_cap
                )
                logger.info(f"Sent sell signal for {trade.ticker}")
                logger.info(res)

            trade_data = {
                "exit_price": exit_price,
                "exit_timestamp": exit_timestamp,
                "exit_reason": exit_reason,
                "pnl_amount": pnl_amount,
                "pnl_percentage": pnl_percentage,
                "trade_duration": str(trade_duration),
                "notes": f"Trade closed due to {exit_reason}",
                "max_drawdown": max_drawdown,
                "max_profit": max_profit,
                "ticker": trade.ticker,
                "contract_address": trade.contract_address,
            }

            # Update database with comprehensive exit information
            with db.get_db_connection(self.historical) as conn:
                db.update_trade_exit(conn, trade_data)

            if self.sheets and "trades" in self.sheets:
                exit_data = {
                    "ticker": trade.ticker,
                    "contract_address": trade.contract_address,
                    "exit_price": exit_price,
                    "exit_timestamp": exit_timestamp,
                    "exit_reason": exit_reason,
                    "pnl_amount": pnl_amount,
                    "pnl_percentage": pnl_percentage,
                }
                from apexbt.sheets.sheets import update_trade_exit

                update_trade_exit(self.sheets["trades"], exit_data)

            # Remove from active trades list
            self.active_trades = [
                t
                for t in self.active_trades
                if t.contract_address != trade.contract_address
            ]

            logger.info(
                f"Exited trade for {trade.ticker} at ${exit_price:.8f}. "
                f"PNL: ${pnl_amount:.2f} ({pnl_percentage:.2f}%). "
                f"Reason: {exit_reason}. Duration: {trade_duration}"
            )

            return True

        except Exception as e:
            logger.error(f"Error exiting trade: {str(e)}")
            return False
