import tweepy
import config
import logging
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from sheets_config import SPREADSHEET_NAME, CREDENTIALS_FILE
import re
from requests import Session
from requests.exceptions import RequestException

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Twitter API credentials from config.py
API_KEY = config.API_KEY
API_SECRET = config.API_SECRET
ACCESS_TOKEN = config.ACCESS_TOKEN
ACCESS_TOKEN_SECRET = config.ACCESS_TOKEN_SECRET
BEARER_TOKEN = config.BEARER_TOKEN

def extract_ticker(tweet_text):
    """
    Extract ticker from tweet text, ignoring dollar amounts
    Returns: (ticker, status)
    """
    # Find all $ instances
    dollar_matches = re.finditer(r'\$([A-Za-z0-9]+)', tweet_text, re.IGNORECASE)

    # Filter out dollar amounts, only keep potential tickers
    tickers = []
    for match in dollar_matches:
        # If it starts with a number, it's likely a price, not a ticker
        if not match.group(1)[0].isdigit():
            tickers.append(match.group(1))

    if len(tickers) == 0:
        return None, "No ticker"
    elif len(tickers) > 1:
        return None, "Multiple tickers"
    else:
        # Return single ticker in uppercase and status
        return tickers[0].upper(), "Single ticker"

def get_crypto_price(ticker):
    """
    Get cryptocurrency price from CoinMarketCap DEX API using spot-pairs endpoint
    Returns price and additional market data for the highest volume pair
    """
    try:
        url = 'https://pro-api.coinmarketcap.com/v4/dex/spot-pairs/latest'

        headers = {
            'Accept': 'application/json',
            'X-CMC_PRO_API_KEY': config.COINMARKETCAP_API_KEY,
        }

        # Using only Ethereum network (1) as it worked in curl
        parameters = {
            'base_asset_symbol': ticker,
            'network_id': '1',  # Only Ethereum
            'limit': '1'
        }

        logger.info(f"Requesting price for {ticker} with parameters: {parameters}")

        session = Session()
        session.headers.update(headers)

        response = session.get(url, params=parameters)
        logger.info(f"Response status code: {response.status_code}")

        data = response.json()
        logger.info(f"Response data: {data}")

        if response.status_code == 200 and data.get('data'):
            pair = data['data'][0]  # Get first pair
            quote = pair['quote'][0]  # Get quote data

            return {
                'price': quote.get('price'),
                'volume_24h': quote.get('volume_24h'),
                'liquidity': quote.get('liquidity'),
                'percent_change_24h': quote.get('percent_change_price_24h'),
                'dex': pair.get('dex_slug'),
                'network': pair.get('network_slug'),
                'pair_name': pair.get('name'),
                'last_updated': quote.get('last_updated')
            }

        logger.warning(f"No valid price data found for {ticker}. Response: {data}")
        return None

    except RequestException as e:
        logger.error(f"Network error fetching DEX price for {ticker}: {str(e)}")
        return None
    except KeyError as e:
        logger.error(f"Data parsing error for {ticker}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching DEX price for {ticker}: {str(e)}")
        return None

def get_user_id(username):
    """Get user ID from username using Twitter API"""
    try:
        # Initialize client with your bearer token
        client = tweepy.Client(bearer_token=config.BEARER_TOKEN)

        # Get user information
        user = client.get_user(username=username)

        if user.data:
            print(f"Username: @{username}")
            print(f"User ID: {user.data.id}")
            return user.data.id
        else:
            print(f"User @{username} not found")
            return None

    except Exception as e:
        print(f"Error: {str(e)}")
        return None

def poll_user_tweets(username, delay=60):
    """Poll for new tweets every minute"""
    client = tweepy.Client(
        bearer_token=config.BEARER_TOKEN,
        consumer_key=config.API_KEY,
        consumer_secret=config.API_SECRET,
        access_token=config.ACCESS_TOKEN,
        access_token_secret=config.ACCESS_TOKEN_SECRET
    )

    # Setup Google Sheets
    sheet = setup_google_sheets()

    latest_tweet_id = None

    while True:
        try:
            # Get user's tweets
            tweets = client.get_users_tweets(
                id=get_user_id(username),
                tweet_fields=['created_at'],
                since_id=latest_tweet_id,
                max_results=10
            )

            if tweets.data:
                # Update latest_tweet_id
                latest_tweet_id = tweets.data[0].id

                # Process tweets
                for tweet in tweets.data:
                    logger.info(f"New tweet: {tweet.text}")
                    save_tweet_to_sheets(sheet, tweet)

            time.sleep(delay)  # Wait before next poll

        except gspread.exceptions.APIError as e:
            if 'QUOTA_EXCEEDED' in str(e):
                logger.error("Google Sheets API quota exceeded. Waiting...")
                time.sleep(100)  # Wait longer if quota is exceeded
            else:
                logger.error(f"Google Sheets API error: {str(e)}")
                time.sleep(delay)
        except Exception as e:
            logger.error(f"Error polling tweets: {str(e)}")
            time.sleep(delay)

def setup_google_sheets():
    """Setup Google Sheets connection"""
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']

    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        CREDENTIALS_FILE, scope)

    client = gspread.authorize(credentials)

    # Open spreadsheet by name
    sheet = client.open(SPREADSHEET_NAME).sheet1

    # Updated headers to include all price data fields
    headers = [
        'Tweet ID',
        'Text',
        'Created At',
        'Timestamp',
        'Ticker',
        'Ticker Status',
        'Price USD',
        'Volume 24h',
        'Liquidity',
        'Price Change 24h %',
        'DEX',
        'Network',
        'Trading Pair',
        'Last Updated'
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

def save_tweet_to_sheets(sheet, tweet):
    """Save tweet to Google Sheets with separate columns for price data"""
    try:
        # Extract ticker from tweet
        ticker, ticker_status = extract_ticker(tweet.text)

        # Get price data if single ticker
        price_data = None
        if ticker_status == "Single ticker":
            price_data = get_crypto_price(ticker)

        row = [
            str(tweet.id),
            tweet.text,
            str(tweet.created_at),
            str(datetime.now()),
            ticker if ticker else "N/A",
            ticker_status,
            str(price_data['price']) if price_data else "N/A",
            str(price_data['volume_24h']) if price_data else "N/A",
            str(price_data['liquidity']) if price_data else "N/A",
            str(price_data['percent_change_24h']) if price_data else "N/A",
            str(price_data['dex']) if price_data else "N/A",
            str(price_data['network']) if price_data else "N/A",
            str(price_data['pair_name']) if price_data else "N/A",
            str(price_data['last_updated']) if price_data else "N/A"
        ]

        sheet.append_row(row)
        logger.info(f"Tweet saved to Google Sheets: {tweet.id}")

    except Exception as e:
        logger.error(f"Error saving to Google Sheets: {str(e)}")

def verify_credentials():
    client = tweepy.Client(
        bearer_token=BEARER_TOKEN,
        consumer_key=API_KEY,
        consumer_secret=API_SECRET,
        access_token=ACCESS_TOKEN,
        access_token_secret=ACCESS_TOKEN_SECRET
    )

    try:
        me = client.get_me()
        print(f"Successfully authenticated as: {me.data.username}")
        return True
    except Exception as e:
        print(f"Authentication failed: {str(e)}")
        return False

if __name__ == "__main__":
    if verify_credentials():
        username = "Vader_AI_"
        logger.info(f"Starting to poll tweets for @{username}")
        poll_user_tweets(username)
