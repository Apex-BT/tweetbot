# sheets.py

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import apexbt.config.config as config
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def setup_google_sheets():
    """Setup Google Sheets connection with multiple worksheets"""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]

    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        config.CREDENTIALS_FILE, scope
    )

    client = gspread.authorize(credentials)
    spreadsheet = client.open(config.SPREADSHEET_NAME)

    # Setup Tweets worksheet
    try:
        tweets_sheet = spreadsheet.worksheet("Tweets")
    except gspread.exceptions.WorksheetNotFound:
        try:
            sheet1 = spreadsheet.sheet1
            sheet1.update_title("Tweets")
            tweets_sheet = sheet1
        except:
            tweets_sheet = spreadsheet.add_worksheet("Tweets", 1000, 20)

    # Setup Trades worksheet
    try:
        trades_sheet = spreadsheet.worksheet("Trades")
    except gspread.exceptions.WorksheetNotFound:
        trades_sheet = spreadsheet.add_worksheet("Trades", 1000, 20)

    # Setup PNL worksheet
    try:
        pnl_sheet = spreadsheet.worksheet("PNL")
    except gspread.exceptions.WorksheetNotFound:
        pnl_sheet = spreadsheet.add_worksheet("PNL", 1000, 15)

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
        "AI Agent",  # New column
        "Timestamp",
        "Ticker",
        "Entry Price",
        "Position Size",
        "Direction",  # Long/Short
        "Stop Loss",
        "Take Profit",
        "Tweet ID Reference",
        "Status",  # Open/Closed
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
        row = [
            str(tweet.id),
            ai_agent,  # Add AI agent
            tweet.text,
            str(tweet.created_at),
            str(datetime.now()),
            ticker if ticker else "N/A",
            ticker_status,
            str(price_data["current_price"]) if price_data else "N/A",
            str(price_data["tweet_time_price"]) if price_data else "N/A",
            str(price_data["volume_24h"]) if price_data else "N/A",
            str(price_data["liquidity"]) if price_data else "N/A",
            str(price_data["percent_change_24h"]) if price_data else "N/A",
            str(price_data["dex"]) if price_data else "N/A",
            str(price_data["network"]) if price_data else "N/A",
            str(price_data["pair_name"]) if price_data else "N/A",
            str(price_data["contract_address"]) if price_data else "N/A",
            str(price_data["last_updated"]) if price_data else "N/A",
        ]

        sheet.append_row(row)
        logger.info(f"Tweet saved to Google Sheets: {tweet.id}")

    except Exception as e:
        logger.error(f"Error saving to Google Sheets: {str(e)}")

def save_trade(sheet, trade_data, pnl_sheet):
    """Save trade information to the Trades worksheet and update PNL"""
    try:
        if "timestamp" in trade_data:
            trade_data["timestamp"] = trade_data["timestamp"].strftime("%Y-%m-%d %H:%M:%S")

        row = [
            trade_data.get("trade_id", ""),
            trade_data.get("ai_agent", ""),
            trade_data.get("timestamp", ""),
            trade_data.get("ticker", ""),
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
