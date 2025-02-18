# sheets.py
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from apexbt.config.config import config
import logging
import time
from datetime import datetime, timedelta


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, max_requests_per_minute=60):
        self.max_requests = max_requests_per_minute
        self.requests = []
        self.last_cleanup = datetime.now()

    def wait_if_needed(self):
        now = datetime.now()

        # Cleanup old requests
        if (now - self.last_cleanup) > timedelta(minutes=1):
            self.requests = [
                t for t in self.requests if (now - t) < timedelta(minutes=1)
            ]
            self.last_cleanup = now

        # Check if we're at the limit
        if len(self.requests) >= self.max_requests:
            oldest_allowed = now - timedelta(minutes=1)
            self.requests = [t for t in self.requests if t > oldest_allowed]

            if len(self.requests) >= self.max_requests:
                sleep_time = (
                    self.requests[0] + timedelta(minutes=1) - now
                ).total_seconds()
                if sleep_time > 0:
                    logger.info(
                        f"Rate limit reached, waiting {sleep_time:.1f} seconds..."
                    )
                    time.sleep(sleep_time)

        self.requests.append(now)


# Create a global rate limiter instance
sheet_rate_limiter = RateLimiter(max_requests_per_minute=50)  # Conservative limit


def setup_google_sheets(historical=False):
    """Setup Google Sheets connection with multiple worksheets"""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]

    credentials = ServiceAccountCredentials.from_json_keyfile_dict(
        config.SHEETS_CREDENTIALS, scope
    )

    client = gspread.authorize(credentials)
    spreadsheet_name = (
        config.HISTORICAL_SPREADSHEET_NAME if historical else config.SPREADSHEET_NAME
    )
    spreadsheet = client.open(spreadsheet_name)

    # Add suffix to worksheet names for historical data
    suffix = "_Historical" if historical else ""

    # Setup Tweets worksheet
    try:
        tweets_sheet = spreadsheet.worksheet(f"Tweets{suffix}")
    except gspread.exceptions.WorksheetNotFound:
        try:
            sheet1 = spreadsheet.sheet1
            sheet1.update_title(f"Tweets{suffix}")
            tweets_sheet = sheet1
        except:
            tweets_sheet = spreadsheet.add_worksheet(f"Tweets{suffix}", 1000, 20)

    # Setup Trades worksheet
    try:
        trades_sheet = spreadsheet.worksheet(f"Trades{suffix}")
    except gspread.exceptions.WorksheetNotFound:
        trades_sheet = spreadsheet.add_worksheet(f"Trades{suffix}", 1000, 20)

    # Setup PNL worksheet
    try:
        pnl_sheet = spreadsheet.worksheet(f"PNL{suffix}")
    except gspread.exceptions.WorksheetNotFound:
        pnl_sheet = spreadsheet.add_worksheet(f"PNL{suffix}", 1000, 15)

    # Setup Agent Summary worksheet
    try:
        agent_summary_sheet = spreadsheet.worksheet(f"AgentSummary{suffix}")
    except gspread.exceptions.WorksheetNotFound:
        agent_summary_sheet = spreadsheet.add_worksheet(f"AgentSummary{suffix}", 100, 7)

    # Setup Summary worksheet
    try:
        summary_sheet = spreadsheet.worksheet(f"Summary{suffix}")
    except gspread.exceptions.WorksheetNotFound:
        summary_sheet = spreadsheet.add_worksheet(f"Summary{suffix}", 20, 2)

    try:
        accounts_sheet = spreadsheet.worksheet("Accounts")
    except gspread.exceptions.WorksheetNotFound:
        accounts_sheet = spreadsheet.add_worksheet("Accounts", 100, 1)

    # Setup all worksheets with headers
    setup_tweets_worksheet(tweets_sheet)
    setup_trades_worksheet(trades_sheet)
    setup_pnl_worksheet(pnl_sheet)
    setup_agent_summary_worksheet(agent_summary_sheet)
    setup_summary_worksheet(summary_sheet)
    setup_accounts_worksheet(accounts_sheet)

    return {
        "tweets": tweets_sheet,
        "trades": trades_sheet,
        "pnl": pnl_sheet,
        "agent_summary": agent_summary_sheet,
        "accounts": accounts_sheet,
    }


def setup_accounts_worksheet(sheet):
    """Setup the accounts worksheet headers"""
    headers = ["Twitter Handle"]
    update_worksheet_headers(sheet, headers)


def update_worksheet_headers(sheet, headers):
    """Update worksheet headers if they don't match"""
    values = sheet.get_all_values()
    if not values or values[0] != headers:
        if values:
            logger.info(f"Clearing sheet {sheet.title} to add correct headers")
            sheet.clear()
        sheet.append_row(headers)
        logger.info(f"Added headers to {sheet.title} sheet")


def setup_tweets_worksheet(sheet):
    """Setup the tweets worksheet headers"""
    headers = [
        "Tweet ID",
        "AI Agent",  # New column
        "Text",
        "Created At",
        "Timestamp",
        "Ticker",
        "Ticker Status",
        "Current Price USD",
        "Tweet Time Price USD",
        "Volume 24h",
        "Liquidity",
        "Price Change 24h %",
        "DEX",
        "Network",
        "Trading Pair",
        "Contract Address",
        "Last Updated",
    ]
    update_worksheet_headers(sheet, headers)


def setup_trades_worksheet(sheet):
    """Setup the trades worksheet headers"""
    headers = [
        "Trade ID",
        "AI Agent",
        "Timestamp",
        "Ticker",
        "Contract Address",
        "Network",
        "Entry Price",
        "Position Size",
        "Direction",
        "Stop Loss",
        "Take Profit",
        "Tweet ID Reference",
        "Status",
        "Exit Price",
        "Exit Timestamp",
        "PNL Amount",
        "PNL Percentage",
        "ATH Price",
        "ATH Timestamp",
        "Market Cap",
        "Notes",
    ]
    update_worksheet_headers(sheet, headers)


def setup_pnl_worksheet(sheet):
    """Setup the PNL worksheet with sections for each AI agent"""
    headers = [
        "AI Agent",
        "Ticker",
        "Contract Address",
        "Entry Time",
        "Entry Price",
        "Current Price",
        "ATH Price",
        "ATH Time",
        "Stop Loss",
        "Price Change %",
        "From ATH %",
        "To Stop Loss %",
        "Invested Amount ($)",
        "Current Value ($)",
        "PNL ($)",
    ]
    update_worksheet_headers(sheet, headers)


def setup_agent_summary_worksheet(sheet):
    """Setup the agent summary worksheet headers"""
    headers = [
        "Agent Name",
        "Total Tweets",
        "Single Ticker Tweets",
        "Qualified Tweets",
        "Total PNL ($)",
        "Closed Trades PNL ($)",
        "Open Trades PNL ($)",
        "Total Trades",
        "Closed Trades",
        "Open Trades",
        "Overall Win Rate (%)",
        "Closed Win Rate (%)",
        "Open Win Rate (%)",
        "Best Trade",
        "Worst Trade",
        "Last Updated",
    ]
    update_worksheet_headers(sheet, headers)


def setup_summary_worksheet(sheet):
    """Setup the summary worksheet headers"""
    headers = ["Metric", "Value"]
    update_worksheet_headers(sheet, headers)


def get_twitter_accounts(sheet):
    """Get list of Twitter handles from Accounts sheet"""
    try:
        # Get all values from the Accounts sheet
        values = sheet.get_all_values()

        # Skip header row and filter out empty values
        accounts = [row[0].strip() for row in values[1:] if row and row[0].strip()]

        # Remove @ symbol if present
        accounts = [acct.lstrip("@") for acct in accounts]

        return accounts
    except Exception as e:
        logger.error(f"Error getting Twitter accounts from sheet: {str(e)}")
        return []


def save_tweet(sheet, tweet, ticker, ticker_status, price_data, ai_agent):
    try:
        sheet_rate_limiter.wait_if_needed()

        price_data = price_data or {}

        row = [
            str(tweet.id),
            ai_agent,
            tweet.text,
            str(tweet.created_at),
            str(datetime.now()),
            ticker if ticker else "N/A",
            ticker_status,
            "N/A",  # Current Price USD
            price_data.get("price", "N/A"),
            price_data.get("volume_24h", "N/A"),
            price_data.get("liquidity", "N/A"),
            price_data.get("percent_change_24h", "N/A"),
            price_data.get("dex", "N/A"),
            price_data.get("network", "N/A"),
            price_data.get("pair_name", "N/A"),
            price_data.get("contract_address", "N/A"),
            price_data.get("last_updated", "N/A"),
        ]

        sheet.append_row(row)
        logger.info(f"Tweet saved to Google Sheets: {tweet.id}")

    except Exception as e:
        logger.error(f"Error saving to Google Sheets: {str(e)}")


def save_trade(sheet, trade_data, pnl_sheet):
    """Save trade information to the Trades worksheet and update PNL"""
    try:
        sheet_rate_limiter.wait_if_needed()

        if "timestamp" in trade_data:
            trade_data["timestamp"] = trade_data["timestamp"].strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        # Format ATH timestamp if exists
        if "ath_timestamp" in trade_data and trade_data["ath_timestamp"]:
            trade_data["ath_timestamp"] = trade_data["ath_timestamp"].strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        # Calculate stop loss if ATH price is available
        stop_loss = None
        if "ath_price" in trade_data and trade_data["ath_price"]:
            stop_loss = float(trade_data["ath_price"]) * config.STOP_LOSS_PERCENTAGE

        # Format market cap for display
        market_cap_display = (
            f"${trade_data['market_cap']:,.2f}"
            if "market_cap" in trade_data and trade_data["market_cap"]
            else "N/A"
        )

        row = [
            trade_data.get("trade_id", ""),
            trade_data.get("ai_agent", ""),
            trade_data.get("timestamp", ""),
            trade_data.get("ticker", ""),
            trade_data.get("contract_address", ""),
            trade_data.get("network", ""),
            str(trade_data.get("entry_price", "")),
            str(trade_data.get("position_size", "")),
            trade_data.get("direction", ""),
            f"${stop_loss:.8f}" if stop_loss else "",
            str(trade_data.get("take_profit", "")),
            str(trade_data.get("tweet_id", "")),
            trade_data.get("status", "Open"),
            str(trade_data.get("exit_price", "")),
            str(trade_data.get("exit_timestamp", "")),
            str(trade_data.get("pnl_amount", "")),
            str(trade_data.get("pnl_percentage", "")),
            f"${trade_data.get('ath_price', '')}",
            str(trade_data.get("ath_timestamp", "")),
            market_cap_display,
            trade_data.get("notes", ""),
        ]

        sheet.append_row(row)
        logger.info(f"Trade saved to Google Sheets: {trade_data.get('trade_id')}")
    except Exception as e:
        logger.error(f"Error saving trade to Google Sheets: {str(e)}")


def update_trades_worksheet(trades_sheet, trades_to_update):
    """Update ATH and stop loss values in trades worksheet in batches"""
    try:
        # Get all values from trades sheet
        all_values = trades_sheet.get_all_values()
        headers = all_values[0]

        # Find relevant column indices
        try:
            ticker_idx = headers.index("Ticker")
            contract_idx = headers.index("Contract Address")
            ath_price_idx = headers.index("ATH Price")
            ath_timestamp_idx = headers.index("ATH Timestamp")
            stop_loss_idx = headers.index("Stop Loss")
            status_idx = headers.index("Status")
        except ValueError as e:
            logger.error(f"Required column not found in trades sheet: {e}")
            return

        # Create batch updates
        batch_updates = []

        # Find and prepare updates for matching trades
        for i, row in enumerate(
            all_values[1:], start=2
        ):  # Start from 2 to account for header row
            if row[status_idx] == "Open":  # Only update open trades
                for trade in trades_to_update:
                    if (
                        row[ticker_idx] == trade["ticker"]
                        and row[contract_idx] == trade["contract_address"]
                    ):

                        # Format values
                        ath_price_str = f"${trade['ath_price']:.8f}"
                        stop_loss_str = f"${trade['stop_loss']:.8f}"
                        ath_timestamp_str = trade["ath_timestamp"].strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )

                        # Add updates to batch
                        batch_updates.extend(
                            [
                                {
                                    "range": f"{chr(65 + ath_price_idx)}{i}",
                                    "values": [[ath_price_str]],
                                },
                                {
                                    "range": f"{chr(65 + ath_timestamp_idx)}{i}",
                                    "values": [[ath_timestamp_str]],
                                },
                                {
                                    "range": f"{chr(65 + stop_loss_idx)}{i}",
                                    "values": [[stop_loss_str]],
                                },
                            ]
                        )

        # Process updates in batches
        if batch_updates:
            BATCH_SIZE = 10  # Number of cell updates per batch
            for i in range(0, len(batch_updates), BATCH_SIZE):
                batch = batch_updates[i : i + BATCH_SIZE]

                # Wait for rate limiting if needed
                sheet_rate_limiter.wait_if_needed()

                # Perform batch update
                trades_sheet.batch_update(batch)

                logger.info(f"Updated batch of {len(batch)} cells in trades worksheet")

            logger.info(
                f"Completed updating {len(batch_updates)} cells for {len(trades_to_update)} trades"
            )

    except Exception as e:
        logger.error(f"Error updating trades worksheet: {str(e)}")
        logger.exception("Full traceback:")
        raise


def update_trade_exit(trades_sheet, exit_data):
    """Update trade exit information in trades worksheet"""
    try:
        # Get all values from trades sheet
        all_values = trades_sheet.get_all_values()
        headers = all_values[0]

        # Find relevant column indices
        try:
            ticker_idx = headers.index("Ticker")
            contract_idx = headers.index("Contract Address")
            status_idx = headers.index("Status")
            exit_price_idx = headers.index("Exit Price")
            exit_timestamp_idx = headers.index("Exit Timestamp")
            pnl_amount_idx = headers.index("PNL Amount")
            pnl_percentage_idx = headers.index("PNL Percentage")
            notes_idx = headers.index("Notes")
        except ValueError as e:
            logger.error(f"Required column not found in trades sheet: {e}")
            return

        # Find the row to update
        row_to_update = None
        for i, row in enumerate(
            all_values[1:], start=2
        ):  # Start from 2 to account for header row
            if (
                row[ticker_idx] == exit_data["ticker"]
                and row[contract_idx] == exit_data["contract_address"]
                and row[status_idx] == "Open"
            ):
                row_to_update = i
                break

        if row_to_update:
            # Prepare updates
            updates = [
                {
                    "range": f"{chr(65 + status_idx)}{row_to_update}",
                    "values": [["Closed"]],
                },
                {
                    "range": f"{chr(65 + exit_price_idx)}{row_to_update}",
                    "values": [[f"${exit_data['exit_price']:.8f}"]],
                },
                {
                    "range": f"{chr(65 + exit_timestamp_idx)}{row_to_update}",
                    "values": [
                        [exit_data["exit_timestamp"].strftime("%Y-%m-%d %H:%M:%S")]
                    ],
                },
                {
                    "range": f"{chr(65 + pnl_amount_idx)}{row_to_update}",
                    "values": [[f"${exit_data['pnl_amount']:.2f}"]],
                },
                {
                    "range": f"{chr(65 + pnl_percentage_idx)}{row_to_update}",
                    "values": [[f"{exit_data['pnl_percentage']:.2f}%"]],
                },
                {
                    "range": f"{chr(65 + notes_idx)}{row_to_update}",
                    "values": [[f"Closed due to {exit_data['exit_reason']}"]],
                },
            ]

            # Wait for rate limiting
            sheet_rate_limiter.wait_if_needed()

            # Perform batch update
            trades_sheet.batch_update(updates)
            logger.info(f"Trade exit updated in sheets for {exit_data['ticker']}")
            return True

        else:
            logger.warning(f"No matching open trade found for {exit_data['ticker']}")
            return False

    except Exception as e:
        logger.error(f"Error updating trade exit in sheets: {str(e)}")
        logger.exception("Full traceback:")
        return False


def update_pnl_sheet(sheet, stats):
    """Update PNL worksheet with current statistics and closed trades"""
    try:
        sheet_rate_limiter.wait_if_needed()

        # Clear and reset headers
        sheet.clear()
        headers = [
            "AI Agent",
            "Ticker",
            "Contract Address",
            "Entry Time",
            "Entry Price",
            "Current/Exit Price",
            "ATH Price",
            "ATH Time",
            "Stop Loss",
            "Price Change %",
            "From ATH %",
            "To Stop Loss %",
            "Invested Amount ($)",
            "Current Value ($)",
            "PNL ($)",
            "Status",
        ]
        sheet.append_row(headers)

        # Group trades by AI agent
        agent_trades = {}

        # Process each trade only once
        processed_trades = set()

        for stat in stats:
            if stat.get("type") != "trade":
                continue

            # Create unique trade identifier
            trade_id = f"{stat['ticker']}_{stat['contract_address']}"
            if trade_id in processed_trades:
                continue
            processed_trades.add(trade_id)

            agent = stat["ai_agent"]
            if agent not in agent_trades:
                agent_trades[agent] = {
                    "open": [],
                    "closed": [],
                    "totals": {
                        "invested_amount": 0,
                        "current_value": 0,
                        "pnl_dollars": 0,
                    },
                }

            # Determine if trade is closed
            is_closed = stat.get("status") == "Closed"
            trade_list = "closed" if is_closed else "open"

            # Add trade to appropriate list
            agent_trades[agent][trade_list].append(stat)

            # Update agent totals
            invested = float(
                str(stat["invested_amount"]).replace("$", "").replace(",", "")
            )
            current = float(
                str(stat["current_value"]).replace("$", "").replace(",", "")
            )
            pnl = float(str(stat["pnl_dollars"]).replace("$", "").replace(",", ""))

            agent_trades[agent]["totals"]["invested_amount"] += invested
            agent_trades[agent]["totals"]["current_value"] += current
            agent_trades[agent]["totals"]["pnl_dollars"] += pnl

        # Prepare all rows for single batch update
        all_rows = []

        for agent in sorted(agent_trades.keys()):
            # Add open trades section
            all_rows.append(
                [f"=== {agent} Active Trades ==="] + [""] * (len(headers) - 1)
            )

            # Sort and add open trades
            open_trades = sorted(
                agent_trades[agent]["open"], key=lambda x: x["entry_time"], reverse=True
            )
            for trade in open_trades:
                all_rows.append(format_trade_row(trade, "Open"))

            # Spacing
            all_rows.append([""] * len(headers))

            # Add closed trades section
            all_rows.append(
                [f"=== {agent} Closed Trades ==="] + [""] * (len(headers) - 1)
            )

            # Sort and add closed trades
            closed_trades = sorted(
                agent_trades[agent]["closed"],
                key=lambda x: x.get("exit_timestamp", x["entry_time"]),
                reverse=True,
            )
            for trade in closed_trades:
                all_rows.append(format_trade_row(trade, "Closed"))

            # Add agent totals
            all_rows.append([""] * len(headers))
            totals = agent_trades[agent]["totals"]
            all_rows.append(
                [
                    f"{agent} Totals",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    f"${totals['invested_amount']:.2f}",
                    f"${totals['current_value']:.2f}",
                    f"${totals['pnl_dollars']:.2f}",
                    "",
                ]
            )
            all_rows.append([""] * len(headers))

        # Calculate and add portfolio totals
        portfolio_totals = {
            "invested": sum(
                agent["totals"]["invested_amount"] for agent in agent_trades.values()
            ),
            "current": sum(
                agent["totals"]["current_value"] for agent in agent_trades.values()
            ),
            "pnl": sum(
                agent["totals"]["pnl_dollars"] for agent in agent_trades.values()
            ),
        }

        all_rows.append(
            [
                "Portfolio Totals",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                f"${portfolio_totals['invested']:.2f}",
                f"${portfolio_totals['current']:.2f}",
                f"${portfolio_totals['pnl']:.2f}",
                "",
            ]
        )

        # Single batch update to sheet
        sheet_rate_limiter.wait_if_needed()
        sheet.append_rows(all_rows)

        logger.info(
            f"PNL sheet updated successfully with {len(processed_trades)} trades"
        )

    except Exception as e:
        logger.error(f"Error updating PNL sheet: {str(e)}")
        logger.exception("Full traceback:")
        raise


def format_trade_row(trade, status):
    """Helper function to format trade row for PNL sheet"""
    try:
        entry_price = float(str(trade["entry_price"]).replace("$", "").replace(",", ""))

        # Handle current/exit price based on status
        if status == "Closed":
            current_price = float(
                str(trade.get("exit_price", trade["current_price"]))
                .replace("$", "")
                .replace(",", "")
            )
            price_display = f"${current_price:.8f} (Exit)"
        else:
            current_price = float(
                str(trade["current_price"]).replace("$", "").replace(",", "")
            )
            price_display = f"${current_price:.8f}"

        ath_price = float(
            str(trade.get("ath_price", current_price)).replace("$", "").replace(",", "")
        )
        stop_loss = ath_price * config.STOP_LOSS_PERCENTAGE

        # Calculate percentages
        price_change = float(
            str(trade["price_change"]).replace("%", "").replace(",", "")
        )
        from_ath = ((current_price - ath_price) / ath_price * 100) if ath_price else 0
        to_stop_loss = (current_price - stop_loss) / current_price * 100

        # Handle invested amount and values
        invested_amount = float(
            str(trade["invested_amount"]).replace("$", "").replace(",", "")
        )
        current_value = float(
            str(trade["current_value"]).replace("$", "").replace(",", "")
        )
        pnl_dollars = float(str(trade["pnl_dollars"]).replace("$", "").replace(",", ""))

        return [
            trade["ai_agent"],
            trade["ticker"],
            trade.get("contract_address", "N/A"),
            trade["entry_time"],
            f"${entry_price:.8f}",
            price_display,
            f"${ath_price:.8f}",
            trade.get("ath_timestamp", "N/A"),
            f"${stop_loss:.8f}",
            f"{price_change:.2f}%" + (" (Final)" if status == "Closed" else ""),
            f"{from_ath:.2f}%",
            f"{to_stop_loss:.2f}%",
            f"${invested_amount:.2f}",
            f"${current_value:.2f}",
            f"${pnl_dollars:.2f}",
            status,
        ]

    except Exception as e:
        logger.error(f"Error formatting trade row: {str(e)}")
        raise


def update_summary_sheet(sheet, agent_stats, pnl_sheet):
    """Update the summary sheet with overall statistics"""
    try:
        sheet_rate_limiter.wait_if_needed()

        # Get PNL data
        pnl_values = pnl_sheet.get_all_values()
        if len(pnl_values) <= 1:
            logger.warning("PNL sheet is empty or contains only headers")
            return

        # Initialize counters
        total_accounts = len(agent_stats)  # Count unique agents
        total_invested = 0
        current_balance = 0
        total_trades = 0
        closed_trades = 0
        open_trades = 0
        winning_trades = 0
        closed_winning_trades = 0
        open_winning_trades = 0
        largest_gain = float("-inf")
        largest_loss = float("inf")
        largest_gain_info = "N/A"
        largest_loss_info = "N/A"
        best_agent = None
        worst_agent = None
        best_pnl = float("-inf")
        worst_pnl = float("inf")
        total_tweets = 0
        single_ticker_tweets = 0
        qualified_tweets = 0

        # Get column indices from PNL sheet headers
        pnl_headers = pnl_values[0]
        try:
            pnl_agent_idx = pnl_headers.index("AI Agent")
            pnl_ticker_idx = pnl_headers.index("Ticker")
            pnl_price_change_idx = pnl_headers.index("Price Change %")
            pnl_status_idx = pnl_headers.index("Status")
            pnl_invested_idx = pnl_headers.index("Invested Amount ($)")
            pnl_current_value_idx = pnl_headers.index("Current Value ($)")
            pnl_amount_idx = pnl_headers.index("PNL ($)")
        except ValueError as e:
            logger.error(f"Required column not found in PNL sheet: {e}")
            return

        # Process agent stats for tweet counts
        for agent, stats in agent_stats.items():
            total_tweets += stats.get("total_tweets", 0)
            single_ticker_tweets += stats.get("single_ticker_tweets", 0)
            qualified_tweets += stats.get("qualified_tweets", 0)

        # Process PNL sheet for trade statistics
        for row in pnl_values[1:]:  # Skip header
            if not row or len(row) <= max(pnl_amount_idx, pnl_status_idx):
                continue

            # Skip section headers and totals
            if "===" in row[pnl_agent_idx] or "Totals" in row[pnl_agent_idx]:
                continue

            try:
                agent = row[pnl_agent_idx]
                ticker = row[pnl_ticker_idx]
                status = row[pnl_status_idx]

                # Process amounts
                invested_str = row[pnl_invested_idx].strip("$").replace(",", "")
                current_str = row[pnl_current_value_idx].strip("$").replace(",", "")
                pnl_str = row[pnl_amount_idx].strip("$").replace(",", "")
                price_change_str = (
                    row[pnl_price_change_idx]
                    .split("(")[0]
                    .strip()
                    .rstrip("%")
                    .replace(",", "")
                )

                if invested_str and current_str:
                    invested_amount = float(invested_str)
                    current_value = float(current_str)
                    total_invested += invested_amount
                    current_balance += current_value

                if pnl_str and price_change_str:
                    pnl = float(pnl_str)
                    price_change = float(price_change_str)

                    # Track trades
                    total_trades += 1
                    if status == "Closed":
                        closed_trades += 1
                        if price_change > 0:
                            closed_winning_trades += 1
                    else:
                        open_trades += 1
                        if price_change > 0:
                            open_winning_trades += 1

                    # Track winning trades overall
                    if price_change > 0:
                        winning_trades += 1

                    # Track largest gain/loss
                    if price_change > largest_gain:
                        largest_gain = price_change
                        largest_gain_info = f"{ticker}: {price_change:.1f}% ({agent})"
                    if price_change < largest_loss:
                        largest_loss = price_change
                        largest_loss_info = f"{ticker}: {price_change:.1f}% ({agent})"

                    # Track best/worst agent
                    agent_pnl = float(pnl_str)
                    if agent_pnl > best_pnl:
                        best_pnl = agent_pnl
                        best_agent = agent
                    if agent_pnl < worst_pnl:
                        worst_pnl = agent_pnl
                        worst_agent = agent

            except (ValueError, IndexError) as e:
                logger.warning(f"Error processing row: {e}")
                continue

        # Calculate rates and percentages
        pnl_dollars = current_balance - total_invested
        pnl_percentage = (
            (pnl_dollars / total_invested * 100) if total_invested > 0 else 0
        )
        overall_win_rate = (
            (winning_trades / total_trades * 100) if total_trades > 0 else 0
        )
        closed_win_rate = (
            (closed_winning_trades / closed_trades * 100) if closed_trades > 0 else 0
        )
        open_win_rate = (
            (open_winning_trades / open_trades * 100) if open_trades > 0 else 0
        )

        # Prepare summary rows
        summary_rows = [
            ["Total Accounts Tracked", str(total_accounts)],
            ["Total Tweets Tracked", str(total_tweets)],
            ["Tweets with Single Ticker", str(single_ticker_tweets)],
            ["Tweets that pass all filters", str(qualified_tweets)],
            ["Amount Invested per Tweet", "$100"],
            ["Current Balance", f"${current_balance:,.2f}"],
            ["Total Amount Invested", f"${total_invested:,.2f}"],
            ["PnL $", f"${pnl_dollars:,.2f}"],
            ["PnL %", f"{pnl_percentage:.1f}%"],
            ["Total Trades", str(total_trades)],
            ["Closed Trades", str(closed_trades)],
            ["Open Trades", str(open_trades)],
            ["Overall Win Rate", f"{overall_win_rate:.1f}%"],
            ["Closed Trades Win Rate", f"{closed_win_rate:.1f}%"],
            ["Open Trades Win Rate", f"{open_win_rate:.1f}%"],
            [
                "Highest Win Rate",
                f"{max([overall_win_rate, closed_win_rate, open_win_rate]):.1f}% ({best_agent or 'N/A'})",
            ],
            [
                "Lowest Win Rate",
                f"{min([overall_win_rate, closed_win_rate, open_win_rate]):.1f}% ({worst_agent or 'N/A'})",
            ],
            ["Largest Gainer", largest_gain_info],
            ["Largest Loser", largest_loss_info],
            [
                "Best Performing Agent",
                f"{best_agent or 'N/A'}"
                + (f" (${best_pnl:,.2f})" if best_agent else ""),
            ],
            [
                "Worst Performing Agent",
                f"{worst_agent or 'N/A'}"
                + (f" (${worst_pnl:,.2f})" if worst_agent else ""),
            ],
            ["Last Updated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        ]

        # Clear existing data and update
        sheet.clear()
        sheet.append_row(["Metric", "Value"])
        sheet.append_rows(summary_rows)

        logger.info("Summary sheet updated successfully")

    except Exception as e:
        logger.error(f"Error updating summary sheet: {str(e)}")
        logger.exception("Full traceback:")
        raise


def update_agent_summary(sheet, stats):
    """Update agent summary worksheet with detailed stats including closed trades"""
    try:
        sheet_rate_limiter.wait_if_needed()

        # Define headers
        headers = [
            "Agent Name",
            "Total Tweets",
            "Single Ticker Tweets",
            "Qualified Tweets",
            "Total PNL ($)",
            "Closed Trades PNL ($)",
            "Open Trades PNL ($)",
            "Total Trades",
            "Closed Trades",
            "Open Trades",
            "Overall Win Rate (%)",
            "Closed Win Rate (%)",
            "Open Win Rate (%)",
            "Best Trade",
            "Worst Trade",
            "Last Updated",
        ]

        # Clear existing data
        sheet.clear()

        # Add headers only once
        sheet.append_row(headers)

        agent_stats = {}

        # Initialize stats for each agent
        for agent in config.TWITTER_USERS:
            agent_stats[agent] = {
                "total_tweets": 0,
                "single_ticker_tweets": 0,
                "qualified_tweets": 0,
                "cumulative_pnl": 0.0,
                "winning_trades": 0,
                "total_trades": 0,
                "closed_trades": 0,
                "closed_winning_trades": 0,
                "open_trades": 0,
                "open_winning_trades": 0,
                "best_trade_pnl": 0.0,
                "worst_trade_pnl": 0.0,
                "best_trade_ticker": "",
                "worst_trade_ticker": "",
                "avg_trade_duration": timedelta(0),
                "total_closed_pnl": 0.0,
                "total_open_pnl": 0.0,
            }

        spreadsheet = sheet.spreadsheet

        # Get PNL sheet data
        pnl_sheet = spreadsheet.worksheet(sheet.title.replace("AgentSummary", "PNL"))
        pnl_values = pnl_sheet.get_all_values()
        pnl_headers = pnl_values[0]

        # Get PNL sheet column indices
        try:
            pnl_agent_idx = pnl_headers.index("AI Agent")
            pnl_ticker_idx = pnl_headers.index("Ticker")
            pnl_contract_idx = pnl_headers.index("Contract Address")
            pnl_entry_time_idx = pnl_headers.index("Entry Time")
            pnl_amount_idx = pnl_headers.index("PNL ($)")
            pnl_price_change_idx = pnl_headers.index("Price Change %")
            pnl_status_idx = pnl_headers.index("Status")
            pnl_invested_idx = pnl_headers.index("Invested Amount ($)")
            pnl_current_value_idx = pnl_headers.index("Current Value ($)")
        except ValueError as e:
            logger.error(f"Required column not found in PNL sheet: {e}")
            return

        # Process PNL sheet for trade statistics and qualified tweets
        processed_trades = set()  # To track unique trades

        for row in pnl_values[1:]:  # Skip header
            if not row or len(row) <= max(pnl_amount_idx, pnl_status_idx):
                continue

            # Skip section headers and totals
            if "===" in row[pnl_agent_idx] or "Totals" in row[pnl_agent_idx]:
                continue

            agent = row[pnl_agent_idx]
            if agent not in agent_stats:
                continue

            # Create unique trade identifier
            trade_id = f"{agent}_{row[pnl_ticker_idx]}_{row[pnl_contract_idx]}"

            # Only process each unique trade once
            if trade_id not in processed_trades:
                processed_trades.add(trade_id)
                agent_stats[agent][
                    "qualified_tweets"
                ] += 1  # Each unique trade represents a qualified tweet

            try:
                # Process PNL and trade data
                pnl_str = row[pnl_amount_idx].strip("$").replace(",", "")
                price_change_str = (
                    row[pnl_price_change_idx]
                    .split("(")[0]
                    .strip()
                    .rstrip("%")
                    .replace(",", "")
                )
                status = row[pnl_status_idx]
                is_closed = status == "Closed"

                if pnl_str and price_change_str:
                    pnl = float(pnl_str)
                    try:
                        price_change = float(price_change_str)
                    except ValueError:
                        price_change_str = "".join(
                            c for c in price_change_str if c in "0123456789.-"
                        )
                        price_change = float(price_change_str)

                    # Update trade counts
                    agent_stats[agent]["total_trades"] += 1

                    if is_closed:
                        agent_stats[agent]["closed_trades"] += 1
                        agent_stats[agent]["total_closed_pnl"] += pnl
                        if price_change > 0:
                            agent_stats[agent]["closed_winning_trades"] += 1
                    else:
                        agent_stats[agent]["open_trades"] += 1
                        agent_stats[agent]["total_open_pnl"] += pnl
                        if price_change > 0:
                            agent_stats[agent]["open_winning_trades"] += 1

                    # Track best and worst trades
                    if pnl > agent_stats[agent]["best_trade_pnl"]:
                        agent_stats[agent]["best_trade_pnl"] = pnl
                        agent_stats[agent]["best_trade_ticker"] = row[pnl_ticker_idx]
                    if pnl < agent_stats[agent]["worst_trade_pnl"]:
                        agent_stats[agent]["worst_trade_pnl"] = pnl
                        agent_stats[agent]["worst_trade_ticker"] = row[pnl_ticker_idx]

                    agent_stats[agent]["cumulative_pnl"] += pnl

            except (ValueError, IndexError) as e:
                logger.warning(f"Error processing row for {agent}: {e}")
                continue

        # Process tweet statistics (only for total and single ticker tweets)
        tweets_sheet = spreadsheet.worksheet(
            sheet.title.replace("AgentSummary", "Tweets")
        )
        tweet_values = tweets_sheet.get_all_values()
        tweet_headers = tweet_values[0]

        # Get tweet sheet column indices
        ai_agent_idx = tweet_headers.index("AI Agent")
        ticker_status_idx = tweet_headers.index("Ticker Status")

        for row in tweet_values[1:]:
            if len(row) <= max(ai_agent_idx, ticker_status_idx):
                continue

            agent = row[ai_agent_idx]
            if agent not in agent_stats:
                continue

            agent_stats[agent]["total_tweets"] += 1
            if row[ticker_status_idx] == "Single ticker":
                agent_stats[agent]["single_ticker_tweets"] += 1

        # Prepare rows for updating with expanded statistics
        rows_to_update = []
        for agent, stats in agent_stats.items():
            # Calculate win rates
            closed_win_rate = (
                (stats["closed_winning_trades"] / stats["closed_trades"] * 100)
                if stats["closed_trades"] > 0
                else 0
            )
            open_win_rate = (
                (stats["open_winning_trades"] / stats["open_trades"] * 100)
                if stats["open_trades"] > 0
                else 0
            )
            overall_win_rate = (
                (
                    (stats["closed_winning_trades"] + stats["open_winning_trades"])
                    / stats["total_trades"]
                    * 100
                )
                if stats["total_trades"] > 0
                else 0
            )

            row = [
                agent,
                stats["total_tweets"],
                stats["single_ticker_tweets"],
                stats["qualified_tweets"],  # This now represents actual trades taken
                f"${stats['cumulative_pnl']:,.2f}",
                f"${stats['total_closed_pnl']:,.2f}",
                f"${stats['total_open_pnl']:,.2f}",
                stats["total_trades"],
                stats["closed_trades"],
                stats["open_trades"],
                f"{overall_win_rate:.1f}%",
                f"{closed_win_rate:.1f}%",
                f"{open_win_rate:.1f}%",
                f"${stats['best_trade_pnl']:,.2f} ({stats['best_trade_ticker']})",
                f"${stats['worst_trade_pnl']:,.2f} ({stats['worst_trade_ticker']})",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ]
            rows_to_update.append(row)

        # Update sheet with all rows
        if rows_to_update:
            sheet.append_rows(rows_to_update)
            logger.info("Agent summary updated successfully")

        # Update summary sheet
        summary_sheet = sheet.spreadsheet.worksheet(
            sheet.title.replace("AgentSummary", "Summary")
        )
        update_summary_sheet(summary_sheet, agent_stats, pnl_sheet)

    except Exception as e:
        logger.error(f"Error updating agent summary: {str(e)}")
        logger.exception("Full traceback:")
        raise


def get_latest_tweet_id_by_agent(sheet, ai_agent: str) -> str:
    """Get the ID of the latest processed tweet for a specific AI agent"""
    try:
        values = sheet.get_all_values()
        if len(values) <= 1:  # Only headers or empty
            return None

        headers = values[0]
        tweet_id_index = 0  # First column is Tweet ID
        ai_agent_index = headers.index("AI Agent")

        # Filter rows for specific AI agent and get tweet IDs
        tweet_ids = [
            row[tweet_id_index]
            for row in values[1:]
            if row[ai_agent_index] == ai_agent and row[tweet_id_index]
        ]

        if tweet_ids:
            return max(tweet_ids)

    except Exception as e:
        logger.error(f"Error getting latest tweet ID for {ai_agent}: {str(e)}")
    return None


def is_tweet_processed(sheet, tweet_id: str, ai_agent: str) -> bool:
    """Check if a specific tweet from an AI agent has already been processed"""
    try:
        values = sheet.get_all_values()
        if len(values) <= 1:  # Only headers or empty
            return False

        headers = values[0]
        tweet_id_index = 0  # First column is Tweet ID
        ai_agent_index = headers.index("AI Agent")

        for row in values[1:]:
            if row[tweet_id_index] == str(tweet_id) and row[ai_agent_index] == ai_agent:
                return True

        return False

    except Exception as e:
        logger.error(f"Error checking processed tweet: {str(e)}")
        return False


def get_sheet_access():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(
        config.SHEETS_CREDENTIALS, scope
    )
    client = gspread.authorize(credentials)

    # Your spreadsheet ID
    spreadsheet = client.open_by_key("15IiBIGnmoLFCY8LWsU_gyjze6m5Na4qh-esgmCmIb8A")

    # Share with your email
    email = "yhp2378@gmail.com"  # Replace with your email
    spreadsheet.share(email, perm_type="user", role="writer")

    print(f"Access granted! Open the spreadsheet at:")
    print(f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}")


def setup_new_sheet():
    # Setup credentials
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(
        config.SHEETS_CREDENTIALS, scope
    )

    # Authorize and create new spreadsheet
    gc = gspread.authorize(credentials)
    sh = gc.create(config.SPREADSHEET_NAME)

    # Get the first sheet
    worksheet = sh.get_worksheet(0)

    # Add headers
    headers = ["Tweet ID", "Text", "Created At", "Timestamp"]
    worksheet.append_row(headers)

    print(f"Created new spreadsheet: {sh.url}")
    print("Please share this spreadsheet with your Google account email")


if __name__ == "__main__":
    import sys

    def setup_sheets(historical=False):
        # Setup credentials
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(
            config.SHEETS_CREDENTIALS, scope
        )

        # Authorize and create new spreadsheet
        gc = gspread.authorize(credentials)
        spreadsheet_name = (
            config.HISTORICAL_SPREADSHEET_NAME
            if historical
            else config.SPREADSHEET_NAME
        )
        sh = gc.create(spreadsheet_name)

        # Initialize worksheets with proper setup
        sheets = setup_google_sheets(historical=historical)

        print(f"Created new {'historical ' if historical else ''}spreadsheet: {sh.url}")
        print("Please share this spreadsheet with your Google account email")

        # Get spreadsheet ID from URL
        spreadsheet_id = sh.id
        return spreadsheet_id

    def grant_access(spreadsheet_id):
        # Reauthorize with credentials
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(
            config.SHEETS_CREDENTIALS, scope
        )
        client = gspread.authorize(credentials)

        # Open and share the spreadsheet
        spreadsheet = client.open_by_key(spreadsheet_id)
        email = "yhp2378@gmail.com"  # Replace with your email
        spreadsheet.share(email, perm_type="user", role="writer")

        print(f"\nAccess granted! Open the spreadsheet at:")
        print(f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}")

    def main():
        print("\nGoogle Sheets Setup Utility")
        print("--------------------------")
        print("1. Setup new main sheet")
        print("2. Setup new historical sheet")
        print("3. Grant access to existing main sheet")
        print("4. Grant access to existing historical sheet")
        print("5. Exit")

        choice = input("\nEnter your choice (1-5): ")

        try:
            if choice == "1":
                print("\nSetting up new main sheet...")
                spreadsheet_id = setup_sheets(historical=False)
                print("\nNow granting access to the new sheet...")
                grant_access(spreadsheet_id)

            elif choice == "2":
                print("\nSetting up new historical sheet...")
                spreadsheet_id = setup_sheets(historical=True)
                print("\nNow granting access to the new sheet...")
                grant_access(spreadsheet_id)

            elif choice == "3":
                print("\nEnter the spreadsheet ID for the main sheet:")
                spreadsheet_id = input("Spreadsheet ID: ")
                grant_access(spreadsheet_id)

            elif choice == "4":
                print("\nEnter the spreadsheet ID for the historical sheet:")
                spreadsheet_id = input("Spreadsheet ID: ")
                grant_access(spreadsheet_id)

            elif choice == "5":
                print("\nExiting...")
                sys.exit(0)

            else:
                print("\nInvalid choice!")
                sys.exit(1)

        except Exception as e:
            print(f"\nAn error occurred: {str(e)}")
            sys.exit(1)

    main()
