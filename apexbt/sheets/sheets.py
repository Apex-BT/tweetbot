# sheets.py

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import apexbt.config.config as config
import logging
import time
from datetime import datetime, timedelta
from config.config import TWITTER_USERS

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

    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        config.CREDENTIALS_FILE, scope
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

    # Setup all worksheets with headers
    setup_tweets_worksheet(tweets_sheet)
    setup_trades_worksheet(trades_sheet)
    setup_pnl_worksheet(pnl_sheet)
    setup_agent_summary_worksheet(agent_summary_sheet)
    setup_summary_worksheet(summary_sheet)

    return {
        "tweets": tweets_sheet,
        "trades": trades_sheet,
        "pnl": pnl_sheet,
        "agent_summary": agent_summary_sheet,
    }


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
        "Cumulative PNL ($)",
        "Win Rate (%)",
        "Last Updated",
    ]
    update_worksheet_headers(sheet, headers)


def setup_summary_worksheet(sheet):
    """Setup the summary worksheet headers"""
    headers = ["Metric", "Value"]
    update_worksheet_headers(sheet, headers)


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
            stop_loss = float(trade_data["ath_price"]) * 0.75  # 25% below ATH

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


def get_sheet_access():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        config.CREDENTIALS_FILE, scope
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
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        config.CREDENTIALS_FILE, scope
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


def update_pnl_sheet(sheet, stats):
    """Update PNL worksheet with current statistics using batch processing"""
    try:
        sheet_rate_limiter.wait_if_needed()

        # Define column indices for better clarity
        AGENT_COL = 0
        TICKER_COL = 1
        CONTRACT_COL = 2
        ENTRY_TIME_COL = 3
        ENTRY_PRICE_COL = 4
        CURRENT_PRICE_COL = 5
        ATH_PRICE_COL = 6
        ATH_TIME_COL = 7
        STOP_LOSS_COL = 8
        PRICE_CHANGE_COL = 9
        FROM_ATH_COL = 10
        TO_STOP_LOSS_COL = 11
        INVESTED_COL = 12
        CURRENT_VALUE_COL = 13
        PNL_COL = 14

        # Clear and reset headers
        sheet.clear()
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
        sheet.append_row(headers)

        # Group trades by AI agent and sort agents alphabetically
        agent_trades = {}
        for stat in stats:
            if stat["type"] == "trade":
                agent = stat["ai_agent"]
                if agent not in agent_trades:
                    agent_trades[agent] = []
                agent_trades[agent].append(stat)

        all_rows = []

        # Process each agent's trades in order
        for agent in sorted(agent_trades.keys()):
            # Sort trades by entry time
            agent_trades[agent].sort(key=lambda x: x["entry_time"])

            # Add individual trades
            for trade in agent_trades[agent]:
                try:
                    entry_price = float(
                        str(trade["entry_price"]).replace("$", "").replace(",", "")
                    )
                    current_price = float(
                        str(trade["current_price"]).replace("$", "").replace(",", "")
                    )
                    ath_price = float(
                        str(trade.get("ath_price", current_price))
                        .replace("$", "")
                        .replace(",", "")
                    )
                    stop_loss = ath_price * 0.75  # 25% below ATH
                    price_change = float(
                        str(trade["price_change"]).replace("%", "").replace(",", "")
                    )
                    from_ath = (
                        ((current_price - ath_price) / ath_price * 100)
                        if ath_price
                        else 0
                    )
                    to_stop_loss = (current_price - stop_loss) / current_price * 100
                    invested_amount = float(
                        str(trade["invested_amount"]).replace("$", "").replace(",", "")
                    )
                    current_value = float(
                        str(trade["current_value"]).replace("$", "").replace(",", "")
                    )
                    pnl_dollars = float(
                        str(trade["pnl_dollars"]).replace("$", "").replace(",", "")
                    )

                    trade_row = [""] * len(headers)
                    trade_row[AGENT_COL] = agent  # Include agent name in each trade row
                    trade_row[TICKER_COL] = trade["ticker"]
                    trade_row[CONTRACT_COL] = trade.get("contract_address", "N/A")
                    trade_row[ENTRY_TIME_COL] = trade["entry_time"]
                    trade_row[ENTRY_PRICE_COL] = f"${entry_price:.8f}"
                    trade_row[CURRENT_PRICE_COL] = f"${current_price:.8f}"
                    trade_row[ATH_PRICE_COL] = f"${ath_price:.8f}"
                    trade_row[ATH_TIME_COL] = trade.get("ath_timestamp", "N/A")
                    trade_row[STOP_LOSS_COL] = f"${stop_loss:.8f}"
                    trade_row[PRICE_CHANGE_COL] = f"{price_change:.2f}%"
                    trade_row[FROM_ATH_COL] = f"{from_ath:.2f}%"
                    trade_row[TO_STOP_LOSS_COL] = f"{to_stop_loss:.2f}%"
                    trade_row[INVESTED_COL] = f"${invested_amount:.2f}"
                    trade_row[CURRENT_VALUE_COL] = f"${current_value:.2f}"
                    trade_row[PNL_COL] = f"${pnl_dollars:.2f}"

                    all_rows.append(trade_row)

                except (ValueError, TypeError) as e:
                    logger.warning(
                        f"Error converting values for trade: {trade}. Error: {e}"
                    )
                    continue

            # Calculate agent totals
            agent_trades_list = agent_trades[agent]
            total_invested = sum(
                float(str(t["invested_amount"]).replace("$", "").replace(",", ""))
                for t in agent_trades_list
            )
            total_current = sum(
                float(str(t["current_value"]).replace("$", "").replace(",", ""))
                for t in agent_trades_list
            )
            total_pnl = sum(
                float(str(t["pnl_dollars"]).replace("$", "").replace(",", ""))
                for t in agent_trades_list
            )

            # Add totals row
            totals_row = [""] * len(headers)
            totals_row[AGENT_COL] = f"{agent} Totals"
            totals_row[INVESTED_COL] = f"${total_invested:.2f}"
            totals_row[CURRENT_VALUE_COL] = f"${total_current:.2f}"
            totals_row[PNL_COL] = f"${total_pnl:.2f}"
            all_rows.append(totals_row)

            # Add empty row for separation
            all_rows.append([""] * len(headers))

        # Calculate and add portfolio totals
        portfolio_invested = sum(
            sum(
                float(str(t["invested_amount"]).replace("$", "").replace(",", ""))
                for t in trades
            )
            for trades in agent_trades.values()
        )
        portfolio_current = sum(
            sum(
                float(str(t["current_value"]).replace("$", "").replace(",", ""))
                for t in trades
            )
            for trades in agent_trades.values()
        )
        portfolio_pnl = sum(
            sum(
                float(str(t["pnl_dollars"]).replace("$", "").replace(",", ""))
                for t in trades
            )
            for trades in agent_trades.values()
        )

        # Add portfolio totals row
        portfolio_row = [""] * len(headers)
        portfolio_row[AGENT_COL] = "Portfolio Totals"
        portfolio_row[INVESTED_COL] = f"${portfolio_invested:.2f}"
        portfolio_row[CURRENT_VALUE_COL] = f"${portfolio_current:.2f}"
        portfolio_row[PNL_COL] = f"${portfolio_pnl:.2f}"
        all_rows.append(portfolio_row)

        # Process rows in batches
        batch_size = 20
        for i in range(0, len(all_rows), batch_size):
            batch = all_rows[i : i + batch_size]
            sheet_rate_limiter.wait_if_needed()
            sheet.append_rows(batch)

        logger.info("PNL sheet updated successfully")

    except Exception as e:
        logger.error(f"Error updating PNL sheet: {str(e)}")
        logger.exception("Full traceback:")
        raise


def update_summary_sheet(sheet, agent_stats, pnl_sheet):
    """Update the summary sheet with overall statistics"""
    try:
        sheet_rate_limiter.wait_if_needed()

        # Clear existing data but keep headers
        sheet.clear()
        setup_summary_worksheet(sheet)

        # Get PNL data
        pnl_values = pnl_sheet.get_all_values()
        if len(pnl_values) <= 1:  # Only headers or empty
            logger.warning("PNL sheet is empty or contains only headers")
            return

        pnl_headers = pnl_values[0]

        # Find column indices
        try:
            invested_amount_idx = pnl_headers.index("Invested Amount ($)")
            current_value_idx = pnl_headers.index("Current Value ($)")
            pnl_amount_idx = pnl_headers.index("PNL ($)")
            price_change_idx = pnl_headers.index("Price Change %")
            agent_idx = pnl_headers.index("AI Agent")
            ticker_idx = pnl_headers.index("Ticker")
        except ValueError as e:
            logger.error(f"Required column not found in PNL sheet: {e}")
            return

        # Initialize tracking variables
        total_invested = 0
        total_current_value = 0
        total_pnl = 0
        agent_totals = {}
        largest_gain = float("-inf")
        largest_loss = float("inf")
        largest_gain_ticker = "N/A"
        largest_loss_ticker = "N/A"
        largest_gain_agent = "N/A"
        largest_loss_agent = "N/A"

        # Process PNL data
        current_agent = None
        winning_trades = {}
        total_trades = {}

        for row in pnl_values[1:]:
            if not row or len(row) <= pnl_amount_idx:
                continue

            # Handle Portfolio Totals row
            if any("Portfolio Totals" in str(cell) for cell in row):
                # Find the non-empty cells from the end of the row
                non_empty_values = [val for val in row[-3:] if val.strip()]
                if len(non_empty_values) >= 3:
                    try:
                        total_invested = float(
                            non_empty_values[0].strip("$").replace(",", "")
                        )
                        total_current_value = float(
                            non_empty_values[1].strip("$").replace(",", "")
                        )
                        total_pnl = float(
                            non_empty_values[2].strip("$").replace(",", "")
                        )
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Error processing portfolio totals: {e}")
                continue

            # Handle Agent Totals rows
            if "Totals" in str(row[agent_idx]):
                agent_name = row[agent_idx].replace("Totals", "").strip()
                if agent_name:
                    # Find the non-empty cells from the end of the row
                    non_empty_values = [val for val in row[-3:] if val.strip()]
                    if len(non_empty_values) >= 3:
                        try:
                            invested = float(
                                non_empty_values[0].strip("$").replace(",", "")
                            )
                            current_val = float(
                                non_empty_values[1].strip("$").replace(",", "")
                            )
                            pnl = float(non_empty_values[2].strip("$").replace(",", ""))
                            agent_totals[agent_name] = {
                                "invested": invested,
                                "current_value": current_val,
                                "pnl": pnl,
                            }
                        except (ValueError, IndexError) as e:
                            logger.warning(
                                f"Error processing agent totals for {agent_name}: {e}"
                            )
                continue

            # Process regular trade rows
            agent = row[agent_idx]
            if agent and not "Totals" in agent:
                current_agent = agent

                if agent not in winning_trades:
                    winning_trades[agent] = 0
                    total_trades[agent] = 0

                try:
                    price_change_str = row[price_change_idx].strip("%").strip()
                    if price_change_str:
                        price_change = float(price_change_str)
                        total_trades[agent] += 1

                        if price_change > 0:
                            winning_trades[agent] += 1

                        if price_change > largest_gain:
                            largest_gain = price_change
                            largest_gain_ticker = row[ticker_idx]
                            largest_gain_agent = agent
                        if price_change < largest_loss:
                            largest_loss = price_change
                            largest_loss_ticker = row[ticker_idx]
                            largest_loss_agent = agent
                except (ValueError, IndexError) as e:
                    continue

        # Calculate win rates
        win_rates = {}
        for agent in total_trades:
            if total_trades[agent] > 0:
                win_rates[agent] = (winning_trades[agent] / total_trades[agent]) * 100
            else:
                win_rates[agent] = 0

        # Get highest and lowest win rates
        highest_win_rate = 0
        lowest_win_rate = 0
        highest_win_rate_agent = "N/A"
        lowest_win_rate_agent = "N/A"

        if win_rates:
            highest_win_rate_agent = max(win_rates.items(), key=lambda x: x[1])[0]
            lowest_win_rate_agent = min(win_rates.items(), key=lambda x: x[1])[0]
            highest_win_rate = win_rates[highest_win_rate_agent]
            lowest_win_rate = win_rates[lowest_win_rate_agent]

        # Calculate total trades and winning trades
        total_trades_count = sum(total_trades.values())
        total_winning_trades = sum(winning_trades.values())
        cumulative_win_rate = (
            (total_winning_trades / total_trades_count * 100)
            if total_trades_count > 0
            else 0
        )

        # Find best and worst performing agents
        best_agent = "N/A"
        worst_agent = "N/A"
        if agent_totals:
            best_agent = max(agent_totals.items(), key=lambda x: x[1]["pnl"])[0]
            worst_agent = min(agent_totals.items(), key=lambda x: x[1]["pnl"])[0]

        # Calculate total tweets from agent_stats
        total_tweets = sum(stats["total_tweets"] for stats in agent_stats.values())
        total_single_ticker = sum(
            stats["single_ticker_tweets"] for stats in agent_stats.values()
        )
        total_qualified = sum(
            stats["qualified_tweets"] for stats in agent_stats.values()
        )

        # Calculate PNL percentage
        pnl_percentage = (total_pnl / total_invested * 100) if total_invested > 0 else 0

        # Prepare summary rows
        summary_rows = [
            ["Total Accounts Tracked", str(len(agent_totals))],
            ["Total Tweets Tracked", str(total_tweets)],
            ["Tweets with Single Ticker", str(total_single_ticker)],
            ["Tweets that pass all filters", str(total_qualified)],
            ["Amount Invested per Tweet", "$100"],
            ["Current Balance", f"${total_current_value:,.2f}"],
            ["Total Amount Invested", f"${total_invested:,.2f}"],
            ["PnL $", f"${total_pnl:,.2f}"],
            ["PnL %", f"{pnl_percentage:.1f}%"],
            ["Cumulative Win Rate", f"{cumulative_win_rate:.1f}%"],
            ["Highest Win Rate", f"{highest_win_rate:.1f}% ({highest_win_rate_agent})"],
            ["Lowest Win Rate", f"{lowest_win_rate:.1f}% ({lowest_win_rate_agent})"],
            [
                "Largest Gainer",
                f"{largest_gain_ticker}: {largest_gain:.1f}% ({largest_gain_agent})",
            ],
            [
                "Largest Loser",
                f"{largest_loss_ticker}: {largest_loss:.1f}% ({largest_loss_agent})",
            ],
            [
                "Best Performing Agent",
                f"{best_agent}"
                + (
                    f" (${agent_totals[best_agent]['pnl']:,.2f})"
                    if best_agent != "N/A"
                    else ""
                ),
            ],
            [
                "Worst Performing Agent",
                f"{worst_agent}"
                + (
                    f" (${agent_totals[worst_agent]['pnl']:,.2f})"
                    if worst_agent != "N/A"
                    else ""
                ),
            ],
            ["Last Updated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        ]

        # Update sheet
        sheet.append_rows(summary_rows)
        logger.info("Summary sheet updated successfully")

    except Exception as e:
        logger.error(f"Error updating summary sheet: {str(e)}")
        logger.exception("Full traceback:")
        raise


def update_agent_summary(sheet, stats):
    """Update agent summary worksheet"""
    try:
        sheet_rate_limiter.wait_if_needed()

        # Clear existing data but keep headers
        sheet.clear()
        setup_agent_summary_worksheet(sheet)

        agent_stats = {}

        # Initialize stats for each agent
        for agent in TWITTER_USERS:
            agent_stats[agent] = {
                "total_tweets": 0,
                "single_ticker_tweets": 0,
                "qualified_tweets": 0,
                "cumulative_pnl": 0.0,
                "winning_trades": 0,
                "total_trades": 0,
            }

        spreadsheet = sheet.spreadsheet

        # First get trades from PNL sheet
        pnl_sheet = spreadsheet.worksheet(sheet.title.replace("AgentSummary", "PNL"))
        pnl_values = pnl_sheet.get_all_values()
        pnl_headers = pnl_values[0]

        # Get PNL sheet column indices
        pnl_agent_idx = pnl_headers.index("AI Agent")
        pnl_contract_idx = pnl_headers.index("Contract Address")
        pnl_amount_idx = pnl_headers.index("PNL ($)")

        # Create agent-specific contract to PNL mapping
        agent_trades = {}
        current_agent = None

        for row in pnl_values[1:]:  # Skip header
            # Skip empty rows or rows without enough columns
            if not row or len(row) <= pnl_amount_idx:
                continue

            # Skip totals rows or empty agent rows
            if not row[pnl_agent_idx] or "Totals" in row[pnl_agent_idx]:
                continue

            agent = row[pnl_agent_idx]
            if agent not in agent_stats:
                continue

            contract = row[pnl_contract_idx]
            if not contract:
                continue

            # Initialize agent's trades set if not exists
            if agent not in agent_trades:
                agent_trades[agent] = set()

            try:
                # Get PNL value
                pnl_str = row[pnl_amount_idx].strip("$").strip()
                if pnl_str:  # Only process if PNL value exists
                    pnl = float(pnl_str)

                    # Add contract to agent's trades
                    agent_trades[agent].add(contract)

                    agent_stats[agent]["total_trades"] += 1
                    agent_stats[agent]["cumulative_pnl"] += pnl
                    if pnl > 0:
                        agent_stats[agent]["winning_trades"] += 1

            except ValueError as e:
                logger.warning(
                    f"Skipping row - Invalid PNL value for {agent}, contract {contract}"
                )
                continue

        # Process tweet statistics
        tweets_sheet = spreadsheet.worksheet(
            sheet.title.replace("AgentSummary", "Tweets")
        )
        values = tweets_sheet.get_all_values()
        headers = values[0]

        # Get tweet sheet column indices
        ai_agent_idx = headers.index("AI Agent")
        ticker_status_idx = headers.index("Ticker Status")
        contract_addr_idx = headers.index("Contract Address")

        for row in values[1:]:  # Skip header
            if len(row) <= contract_addr_idx:
                continue

            agent = row[ai_agent_idx]
            if agent not in agent_stats:
                continue

            agent_stats[agent]["total_tweets"] += 1

            if row[ticker_status_idx] == "Single ticker":
                agent_stats[agent]["single_ticker_tweets"] += 1

                # Check if this tweet's contract is in agent's trades
                contract = row[contract_addr_idx]
                if (
                    contract
                    and contract != "N/A"
                    and agent in agent_trades
                    and contract in agent_trades[agent]
                ):
                    agent_stats[agent]["qualified_tweets"] += 1

        # Prepare rows for updating
        rows_to_update = []
        for agent, stats in agent_stats.items():
            win_rate = (
                (stats["winning_trades"] / stats["total_trades"] * 100)
                if stats["total_trades"] > 0
                else 0
            )

            rows_to_update.append(
                [
                    agent,
                    stats["total_tweets"],
                    stats["single_ticker_tweets"],
                    stats["qualified_tweets"],
                    f"${stats['cumulative_pnl']:.2f}",
                    f"{win_rate:.1f}%",
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ]
            )

        # Update sheet
        if rows_to_update:
            sheet.append_rows(rows_to_update)
            logger.info("Agent summary updated successfully")

        # Update summary sheet
        summary_sheet = sheet.spreadsheet.worksheet(
            sheet.title.replace("AgentSummary", "Summary")
        )
        pnl_sheet = sheet.spreadsheet.worksheet(
            sheet.title.replace("AgentSummary", "PNL")
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


if __name__ == "__main__":
    import sys

    def setup_sheets(historical=False):
        # Setup credentials
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        credentials = ServiceAccountCredentials.from_json_keyfile_name(
            config.CREDENTIALS_FILE, scope
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
        credentials = ServiceAccountCredentials.from_json_keyfile_name(
            config.CREDENTIALS_FILE, scope
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
