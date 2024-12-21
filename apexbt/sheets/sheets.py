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
    """Setup Google Sheets connection"""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]

    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        config.CREDENTIALS_FILE, scope
    )

    client = gspread.authorize(credentials)

    # Open spreadsheet by name
    sheet = client.open(config.SPREADSHEET_NAME).sheet1

    # Updated headers to include all price data fields
    headers = [
        "Tweet ID",
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
        "Price Change 7d %",
        "Price Change 14d %",
        "Price Change 30d %",
        "DEX",
        "Network",
        "Trading Pair",
        "Contract Address",
        "Last Updated",
    ]

    # Check if headers exist
    values = sheet.get_all_values()
    if not values or values[0] != headers:
        if values:
            logger.info("Clearing sheet to add correct headers")
            sheet.clear()
        sheet.append_row(headers)
        logger.info("Added headers to sheet")

    return sheet


def save_tweet_to_sheets(sheet, tweet, ticker, ticker_status, price_data):
    try:
        row = [
            str(tweet.id),
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
            str(price_data["percent_change_7d"]) if price_data else "N/A",
            str(price_data["percent_change_14d"]) if price_data else "N/A",
            str(price_data["percent_change_30d"]) if price_data else "N/A",
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
