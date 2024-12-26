import time
import threading
import logging
from dataclasses import dataclass
from apexbt.crypto.crypto import get_current_price
from typing import List
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class TradePosition:
    ticker: str
    entry_price: float
    entry_timestamp: datetime
    ai_agent: str
    status: str = "Open"

class TradeManager:
    def __init__(self, sheets_dict, update_interval=60):
        self.trades_sheet = sheets_dict["trades"]
        self.pnl_sheet = sheets_dict["pnl"]
        self.update_interval = update_interval
        self.active_trades: List[TradePosition] = []
        self.is_running = False
        self.update_thread = None
        self.last_update = 0  # Track last update time
        self.MIN_UPDATE_INTERVAL = 2  # Minimum seconds between updates
        self.load_active_trades()

    def load_active_trades(self):
        """Load active trades from trades sheet"""
        try:
            values = self.trades_sheet.get_all_values()
            if len(values) < 2:  # Only headers or empty
                return

            headers = values[0]
            status_idx = headers.index("Status")

            for row in values[1:]:
                if row[status_idx] == "Open":
                    timestamp_str = row[headers.index("Timestamp")]
                    try:
                        # First try with microseconds
                        entry_timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f")
                    except ValueError:
                        try:
                            # If that fails, try without microseconds
                            entry_timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            logger.warning(f"Invalid timestamp format for {row[headers.index('Ticker')]}: {timestamp_str}")
                            continue

                    trade = TradePosition(
                        ticker=row[headers.index("Ticker")],
                        entry_price=float(row[headers.index("Entry Price")]),
                        entry_timestamp=entry_timestamp,
                        ai_agent=row[headers.index("AI Agent")]
                    )
                    self.active_trades.append(trade)

            logger.info(f"Loaded {len(self.active_trades)} active trades")
        except Exception as e:
            logger.error(f"Error loading active trades: {str(e)}")

    def start_monitoring(self):
        """Start the monitoring thread"""
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
                self.update_trade_prices()
                time.sleep(self.update_interval)
            except Exception as e:
                logger.error(f"Error in trade monitoring: {str(e)}")
                time.sleep(60)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    def update_sheets_with_backoff(self, rows):
        """Update sheets with retry and backoff"""
        # Ensure minimum time between updates
        time_since_last = time.time() - self.last_update
        if time_since_last < self.MIN_UPDATE_INTERVAL:
            time.sleep(self.MIN_UPDATE_INTERVAL - time_since_last)

        self.pnl_sheet.clear()
        self.pnl_sheet.append_rows(rows)
        self.last_update = time.time()

    def update_trade_prices(self):
        """Update current prices for all active trades with per-agent grouping"""
        try:
            # Prepare header row
            rows = [["AI Agent", "Ticker", "Entry Time", "Entry Price", "Current Price",
                    "Price Change %", "Invested Amount ($)", "Current Value ($)", "PNL ($)"]]

            # Group trades by AI agent
            agent_trades = {}
            for trade in self.active_trades:
                if trade.ai_agent not in agent_trades:
                    agent_trades[trade.ai_agent] = []
                agent_trades[trade.ai_agent].append(trade)

            grand_total_invested = 0
            grand_total_current = 0
            grand_total_pnl = 0

            for agent, trades in agent_trades.items():
                agent_total_invested = 0
                agent_total_current = 0
                agent_total_pnl = 0

                for trade in trades:
                    price_data = get_current_price(trade.ticker)
                    if price_data and price_data.get("price"):
                        current_price = float(price_data["price"])
                        price_change = ((current_price - trade.entry_price) / trade.entry_price) * 100

                        invested_amount = 100.0  # Fixed investment amount
                        current_value = invested_amount * (1 + price_change/100)
                        pnl = current_value - invested_amount

                        agent_total_invested += invested_amount
                        agent_total_current += current_value
                        agent_total_pnl += pnl

                        rows.append([
                            agent,
                            trade.ticker,
                            trade.entry_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                            f"{trade.entry_price:.8f}",
                            f"{current_price:.8f}",
                            f"{price_change:.2f}",
                            f"{invested_amount:.2f}",
                            f"{current_value:.2f}",
                            f"{pnl:.2f}"
                        ])

                # Add agent totals
                if len(trades) > 0:
                    rows.append([""] * 9)  # Blank row
                    rows.append([
                        f"{agent} TOTALS",
                        "",
                        "",
                        "",
                        "",
                        "",
                        f"{agent_total_invested:.2f}",
                        f"{agent_total_current:.2f}",
                        f"{agent_total_pnl:.2f}"
                    ])
                    rows.append([""] * 9)  # Blank row

                    grand_total_invested += agent_total_invested
                    grand_total_current += agent_total_current
                    grand_total_pnl += agent_total_pnl

            # Add grand totals
            if grand_total_invested > 0:
                rows.append([
                    "GRAND TOTALS",
                    "",
                    "",
                    "",
                    "",
                    "",
                    f"{grand_total_invested:.2f}",
                    f"{grand_total_current:.2f}",
                    f"{grand_total_pnl:.2f}"
                ])

            # Update sheets with all rows at once
            if len(rows) > 1:
                self.update_sheets_with_backoff(rows)
                logger.info("Updated prices for all active trades")

        except Exception as e:
            logger.error(f"Error updating trade prices: {str(e)}")

    def get_current_stats(self):
        """Get current prices and changes for all active trades"""
        try:
            values = self.pnl_sheet.get_all_values()
            if len(values) < 2:  # Check if there's data beyond headers
                return []

            headers = values[0]
            stats = []
            current_agent = None
            agent_totals = {
                'invested_amount': 0,
                'current_value': 0,
                'pnl_dollars': 0
            }

            # Skip header row
            for row in values[1:]:
                if not any(row):  # Skip empty rows
                    continue

                # Check if this is a totals row
                if row[0].endswith('TOTALS'):
                    if row[0] == 'GRAND TOTALS':
                        stats.append({
                            'type': 'grand_total',
                            'invested_amount': float(row[6]) if row[6] else 0,
                            'current_value': float(row[7]) if row[7] else 0,
                            'pnl_dollars': float(row[8]) if row[8] else 0
                        })
                    else:
                        # Agent totals
                        agent = row[0].replace(' TOTALS', '')
                        stats.append({
                            'type': 'agent_total',
                            'agent': agent,
                            'invested_amount': float(row[6]) if row[6] else 0,
                            'current_value': float(row[7]) if row[6] else 0,
                            'pnl_dollars': float(row[8]) if row[8] else 0
                        })
                else:
                    # Regular trade row
                    try:
                        stats.append({
                            'type': 'trade',
                            'ai_agent': row[0],  # AI Agent column
                            'ticker': row[1],    # Ticker column
                            'entry_time': row[2],
                            'entry_price': float(row[3]),
                            'current_price': float(row[4]),
                            'price_change': row[5],
                            'invested_amount': float(row[6]),
                            'current_value': float(row[7]),
                            'pnl_dollars': float(row[8])
                        })
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Skipping invalid row: {row}. Error: {str(e)}")
                        continue

            return stats

        except Exception as e:
            logger.error(f"Error getting current stats: {str(e)}")
            return []

    def has_open_trade(self, ticker: str) -> bool:
        """Check if there's already an open trade for the given ticker"""
        return any(trade.ticker.lower() == ticker.lower() and trade.status == "Open"
                  for trade in self.active_trades)

    def add_trade(self, ticker: str, entry_price: float, ai_agent: str, entry_timestamp: datetime = None) -> bool:
        """
        Add a new trade to active trades
        Returns True if trade was added, False if trade already exists
        entry_timestamp: Optional timestamp for historical analysis (defaults to current time)
        """
        if self.has_open_trade(ticker):
            logger.warning(f"Trade for {ticker} already exists - skipping")
            return False

        if entry_timestamp is None:
            entry_timestamp = datetime.now()

        trade = TradePosition(
            ticker=ticker,
            entry_price=entry_price,
            entry_timestamp=entry_timestamp,
            status="Open",
            ai_agent=ai_agent
        )
        self.active_trades.append(trade)
        logger.info(f"Added new trade for {ticker} at price {entry_price} (entry time: {entry_timestamp})")
        return True
