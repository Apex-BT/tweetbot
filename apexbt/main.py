import tweepy
import logging
import time
import gspread
import re
from apexbt.config import config
from apexbt.sheets import sheets
from apexbt.crypto import crypto

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
    dollar_matches = re.finditer(r"\$([A-Za-z0-9]+)", tweet_text, re.IGNORECASE)

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
        access_token_secret=config.ACCESS_TOKEN_SECRET,
    )

    # Setup Google Sheets
    sheet = sheets.setup_google_sheets()

    latest_tweet_id = None

    while True:
        try:
            # Get user's tweets
            tweets = client.get_users_tweets(
                id=get_user_id(username),
                tweet_fields=["created_at"],
                since_id=latest_tweet_id,
                max_results=10,
            )

            if tweets.data:
                # Update latest_tweet_id
                latest_tweet_id = tweets.data[0].id

                # Process tweets
                for tweet in tweets.data:
                    logger.info(f"New tweet: {tweet.text}")

                    ticker, ticker_status = extract_ticker(tweet.text)

                    price_data = None
                    if ticker_status == "Single ticker":
                        price_data = crypto.get_crypto_price(ticker, tweet.created_at)

                    sheets.save_tweet_to_sheets(
                        sheet, tweet, ticker, ticker_status, price_data
                    )

            time.sleep(delay)  # Wait before next poll

        except gspread.exceptions.APIError as e:
            if "QUOTA_EXCEEDED" in str(e):
                logger.error("Google Sheets API quota exceeded. Waiting...")
                time.sleep(100)  # Wait longer if quota is exceeded
            else:
                logger.error(f"Google Sheets API error: {str(e)}")
                time.sleep(delay)
        except Exception as e:
            logger.error(f"Error polling tweets: {str(e)}")
            time.sleep(delay)


def verify_credentials():
    client = tweepy.Client(
        bearer_token=BEARER_TOKEN,
        consumer_key=API_KEY,
        consumer_secret=API_SECRET,
        access_token=ACCESS_TOKEN,
        access_token_secret=ACCESS_TOKEN_SECRET,
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
