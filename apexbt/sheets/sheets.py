# sheets.py

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import apexbt.config.config as config
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
            self.requests = [t for t in self.requests if (now - t) < timedelta(minutes=1)]
            self.last_cleanup = now

        # Check if we're at the limit
        if len(self.requests) >= self.max_requests:
            oldest_allowed = now - timedelta(minutes=1)
            self.requests = [t for t in self.requests if t > oldest_allowed]

            if len(self.requests) >= self.max_requests:
                sleep_time = (self.requests[0] + timedelta(minutes=1) - now).total_seconds()
                if sleep_time > 0:
                    logger.info(f"Rate limit reached, waiting {sleep_time:.1f} seconds...")
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
    spreadsheet_name = config.HISTORICAL_SPREADSHEET_NAME if historical else config.SPREADSHEET_NAME
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

    # Setup all worksheets with headers
    setup_tweets_worksheet(tweets_sheet)
    setup_trades_worksheet(trades_sheet)
    setup_pnl_worksheet(pnl_sheet)

    return {
        "tweets": tweets_sheet,
        "trades": trades_sheet,
        "pnl": pnl_sheet
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
        "Notes"
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
        "Price Change %",
        "Invested Amount ($)",
        "Current Value ($)",
        "PNL ($)"
    ]
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
            price_data.get("last_updated", "N/A")
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
            trade_data["timestamp"] = trade_data["timestamp"].strftime("%Y-%m-%d %H:%M:%S")

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
            str(trade_data.get("stop_loss", "")),
            str(trade_data.get("take_profit", "")),
            str(trade_data.get("tweet_id", "")),
            trade_data.get("status", "Open"),
            str(trade_data.get("exit_price", "")),
            str(trade_data.get("exit_timestamp", "")),
            str(trade_data.get("pnl_amount", "")),
            str(trade_data.get("pnl_percentage", "")),
            trade_data.get("notes", "")
        ]

        sheet.append_row(row)
        logger.info(f"Trade saved to Google Sheets: {trade_data.get('trade_id')}")
    except Exception as e:
        logger.error(f"Error saving trade to Google Sheets: {str(e)}")

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
    """Update PNL worksheet with current statistics"""
    try:
        # Rate limit check
        sheet_rate_limiter.wait_if_needed()

        # Clear existing data but keep headers
        sheet.clear()
        sheet.append_row([
            "AI Agent",
            "Ticker",
            "Contract Address",
            "Entry Time",
            "Entry Price",
            "Current Price",
            "Price Change %",
            "Invested Amount ($)",
            "Current Value ($)",
            "PNL ($)"
        ])

        # Group trades by AI agent and calculate totals
        agent_trades = {}
        portfolio_total = {
            'invested_amount': 0,
            'current_value': 0,
            'pnl_dollars': 0
        }

        # Process stats and build rows
        rows_to_append = []

        for stat in stats:
            if stat['type'] == 'trade':
                agent = stat['ai_agent']
                if agent not in agent_trades:
                    agent_trades[agent] = {
                        'trades': [],
                        'invested_amount': 0,
                        'current_value': 0,
                        'pnl_dollars': 0
                    }

                agent_trades[agent]['trades'].append(stat)
                agent_trades[agent]['invested_amount'] += stat['invested_amount']
                agent_trades[agent]['current_value'] += stat['current_value']
                agent_trades[agent]['pnl_dollars'] += stat['pnl_dollars']

                # Add to portfolio totals
                portfolio_total['invested_amount'] += stat['invested_amount']
                portfolio_total['current_value'] += stat['current_value']
                portfolio_total['pnl_dollars'] += stat['pnl_dollars']

        # Write trades grouped by agent with totals
        for agent, data in agent_trades.items():
            # Write individual trades
            for trade in data['trades']:
                row = [
                    trade['ai_agent'],
                    trade['ticker'],
                    trade.get('contract_address', 'N/A'),
                    trade['entry_time'],
                    f"${trade['entry_price']:.8f}",
                    f"${trade['current_price']:.8f}",
                    trade['price_change'],
                    f"${trade['invested_amount']:.2f}",
                    f"${trade['current_value']:.2f}",
                    f"${trade['pnl_dollars']:.2f}"
                ]
                rows_to_append.append(row)

            # Write agent totals
            rows_to_append.append([])  # Empty row
            rows_to_append.append([
                f"{agent} Totals",
                "", "", "", "", "", "",
                f"${data['invested_amount']:.2f}",
                f"${data['current_value']:.2f}",
                f"${data['pnl_dollars']:.2f}"
            ])
            rows_to_append.append([])  # Empty row

        # Write portfolio totals
        rows_to_append.append([
            "Portfolio Totals",
            "", "", "", "", "", "",
            f"${portfolio_total['invested_amount']:.2f}",
            f"${portfolio_total['current_value']:.2f}",
            f"${portfolio_total['pnl_dollars']:.2f}"
        ])

        # Batch append rows with rate limiting
        batch_size = 20
        for i in range(0, len(rows_to_append), batch_size):
            batch = rows_to_append[i:i + batch_size]
            sheet_rate_limiter.wait_if_needed()
            sheet.append_rows(batch)

        logger.info("PNL data updated in Google Sheets")

    except Exception as e:
        logger.error(f"Error updating PNL sheet: {str(e)}")

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
            if (row[tweet_id_index] == str(tweet_id) and
                row[ai_agent_index] == ai_agent):
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
        spreadsheet_name = config.HISTORICAL_SPREADSHEET_NAME if historical else config.SPREADSHEET_NAME
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
