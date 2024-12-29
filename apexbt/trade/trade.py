# apexbt/apexbt/trade/trade.py
import time
import threading
import logging
from dataclasses import dataclass
from apexbt.crypto.crypto import get_current_price
from typing import List
from datetime import datetime
from apexbt.database.database import get_db_connection

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
    def __init__(self, update_interval=60):
        self.update_interval = update_interval
        self.active_trades: List[TradePosition] = []
        self.is_running = False
        self.update_thread = None
        self.last_update = 0
        self.MIN_UPDATE_INTERVAL = 2
        self.load_active_trades()

    def load_active_trades(self):
        """Load active trades from database"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT ticker, entry_price, timestamp, ai_agent
                    FROM trades
                    WHERE status = 'Open'
                """)
                trades = cursor.fetchall()

                self.active_trades = []
                for trade in trades:
                    try:
                        entry_timestamp = datetime.strptime(trade['timestamp'],
                                                          "%Y-%m-%d %H:%M:%S.%f")
                    except ValueError:
                        entry_timestamp = datetime.strptime(trade['timestamp'],
                                                          "%Y-%m-%d %H:%M:%S")

                    self.active_trades.append(TradePosition(
                        ticker=trade['ticker'],
                        entry_price=float(trade['entry_price']),
                        entry_timestamp=entry_timestamp,
                        ai_agent=trade['ai_agent']
                    ))

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

    def update_pnl(self, stats, sheets=None):
        """Update PNL in both database and Google Sheets"""
        # Update database
        self.update_pnl_table(stats)

        # Update Google Sheets if available
        if sheets and 'pnl' in sheets:
            from apexbt.sheets.sheets import update_pnl_sheet
            update_pnl_sheet(sheets['pnl'], stats)

    def update_pnl_table(self, stats):
        """Update PNL table in database"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()

                # Clear existing PNL data
                cursor.execute("DELETE FROM pnl")

                # Insert new PNL data
                for stat in stats:
                    if stat['type'] == 'trade':
                        cursor.execute("""
                            INSERT INTO pnl (
                                ai_agent, ticker, entry_time, entry_price,
                                current_price, price_change_percentage,
                                invested_amount, current_value, pnl,
                                contract_address
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            stat['ai_agent'],
                            stat['ticker'],
                            stat['entry_time'],
                            stat['entry_price'],
                            stat['current_price'],
                            float(stat['price_change'].rstrip('%')),
                            stat['invested_amount'],
                            stat['current_value'],
                            stat['pnl_dollars'],
                            stat.get('contract_address', None)  # Add contract address
                        ))

                conn.commit()
                self.last_update = time.time()

        except Exception as e:
            logger.error(f"Error updating PNL table: {str(e)}")
            raise

    def update_trade_prices(self, sheets=None):
        """Update current prices for all active trades"""
        try:
            stats = []
            agent_totals = {}
            grand_total = {'invested_amount': 0, 'current_value': 0, 'pnl_dollars': 0}

            # Process trades by agent
            for trade in self.active_trades:
                price_data = get_current_price(trade.ticker)
                if price_data and price_data.get("price"):
                    current_price = float(price_data["price"])
                    price_change = ((current_price - trade.entry_price) / trade.entry_price) * 100

                    invested_amount = 100.0
                    current_value = invested_amount * (1 + price_change/100)
                    pnl = current_value - invested_amount

                    # Update agent totals
                    if trade.ai_agent not in agent_totals:
                        agent_totals[trade.ai_agent] = {
                            'invested_amount': 0,
                            'current_value': 0,
                            'pnl_dollars': 0
                        }

                    agent_totals[trade.ai_agent]['invested_amount'] += invested_amount
                    agent_totals[trade.ai_agent]['current_value'] += current_value
                    agent_totals[trade.ai_agent]['pnl_dollars'] += pnl

                    # Add trade stats
                    stats.append({
                        'type': 'trade',
                        'ai_agent': trade.ai_agent,
                        'ticker': trade.ticker,
                        'entry_time': trade.entry_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        'entry_price': trade.entry_price,
                        'current_price': current_price,
                        'price_change': f"{price_change:.2f}%",
                        'invested_amount': invested_amount,
                        'current_value': current_value,
                        'pnl_dollars': pnl,
                        'contract_address': price_data.get('contract_address')  # Add contract address
                    })

            # Add agent totals
            for agent, totals in agent_totals.items():
                stats.append({
                    'type': 'agent_total',
                    'agent': agent,
                    **totals
                })
                grand_total['invested_amount'] += totals['invested_amount']
                grand_total['current_value'] += totals['current_value']
                grand_total['pnl_dollars'] += totals['pnl_dollars']

            # Add grand total
            stats.append({
                'type': 'grand_total',
                **grand_total
            })

            # Update database
            self.update_pnl(stats, sheets)
            logger.info("Updated prices for all active trades")

        except Exception as e:
            logger.error(f"Error updating trade prices: {str(e)}")

    def get_current_stats(self):
        """Get current statistics from database"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM pnl ORDER BY ai_agent, ticker")
                rows = cursor.fetchall()

                stats = []
                current_agent = None
                agent_totals = {'invested_amount': 0, 'current_value': 0, 'pnl_dollars': 0}

                for row in rows:
                    stats.append({
                        'type': 'trade',
                        'ai_agent': row['ai_agent'],
                        'ticker': row['ticker'],
                        'contract_address': row['contract_address'],
                        'entry_time': row['entry_time'],
                        'entry_price': row['entry_price'],
                        'current_price': row['current_price'],
                        'price_change': f"{row['price_change_percentage']:.2f}%",
                        'invested_amount': row['invested_amount'],
                        'current_value': row['current_value'],
                        'pnl_dollars': row['pnl']
                    })

                return stats

        except Exception as e:
            logger.error(f"Error getting current stats: {str(e)}")
            return []

    def has_open_trade(self, ticker: str) -> bool:
        """Check if there's already an open trade for the given ticker"""
        return any(trade.ticker.lower() == ticker.lower() and trade.status == "Open"
                  for trade in self.active_trades)

    def add_trade(self, ticker: str, entry_price: float, ai_agent: str, entry_timestamp: datetime = None) -> bool:
        """Add a new trade to active trades"""
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

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO trades (
                        trade_id, ai_agent, timestamp, ticker,
                        entry_price, position_size, direction,
                        status, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"T{entry_timestamp.strftime('%Y%m%d%H%M%S')}",
                    ai_agent,
                    entry_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    ticker,
                    entry_price,
                    100.0,  # Fixed position size
                    "Long",  # Default direction
                    "Open",
                    "Auto trade based on tweet signal"
                ))
                conn.commit()

            self.active_trades.append(trade)
            logger.info(f"Added new trade for {ticker} at price {entry_price}")
            return True

        except Exception as e:
            logger.error(f"Error adding trade to database: {str(e)}")
            return False
