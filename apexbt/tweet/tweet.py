# tweet.py
import tweepy
import logging
import re
from datetime import datetime, timezone
from dataclasses import dataclass
from apexbt.config import config
from typing import Tuple, List, Optional
import time

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class MockTweet:
    """Mock Tweet class to simulate Twitter API response"""
    id: int
    text: str
    created_at: datetime

class TwitterManager:
    def __init__(self):
        self.api_key = config.API_KEY
        self.api_secret = config.API_SECRET
        self.access_token = config.ACCESS_TOKEN
        self.access_token_secret = config.ACCESS_TOKEN_SECRET
        self.bearer_token = config.BEARER_TOKEN

        self.client = self._setup_client()

    def _setup_client(self) -> tweepy.Client:
        """Initialize Twitter API client"""
        return tweepy.Client(
            bearer_token=self.bearer_token,
            consumer_key=self.api_key,
            consumer_secret=self.api_secret,
            access_token=self.access_token,
            access_token_secret=self.access_token_secret,
        )

    def verify_credentials(self) -> bool:
        """Verify Twitter API credentials"""
        try:
            me = self.client.get_me()
            logger.info(f"Successfully authenticated as: {me.data.username}")
            return True
        except Exception as e:
            logger.error(f"Authentication failed: {str(e)}")
            return False

    def get_user_id(self, username: str) -> Optional[int]:
        """Get user ID from username"""
        try:
            user = self.client.get_user(username=username)
            if user.data:
                logger.info(f"Username: @{username}")
                logger.info(f"User ID: {user.data.id}")
                return user.data.id
            logger.warning(f"User @{username} not found")
            return None
        except Exception as e:
            logger.error(f"Error getting user ID: {str(e)}")
            return None

    @staticmethod
    def extract_ticker(tweet_text: str) -> Tuple[Optional[str], str]:
        """Extract ticker from tweet text, ignoring dollar amounts"""
        dollar_matches = re.finditer(r"\$([A-Za-z0-9]+)", tweet_text, re.IGNORECASE)

        tickers = []
        for match in dollar_matches:
            if not match.group(1)[0].isdigit():
                tickers.append(match.group(1))

        if len(tickers) == 0:
            return None, "No ticker"
        elif len(tickers) > 1:
            return None, "Multiple tickers"
        else:
            return tickers[0].upper(), "Single ticker"

    def fetch_historical_tweets(self, username: str, start_date: datetime) -> List[MockTweet]:
        """Fetch historical tweets from a specific user since start_date"""
        historical_tweets = []
        user_id = self.get_user_id(username)

        if not user_id:
            logger.error(f"Could not find user ID for {username}")
            return []

        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)

        pagination_token = None
        retry_count = 0
        max_retries = 3
        base_delay = 60  # Base delay of 1 minute

        while True:
            try:
                tweets = self.client.get_users_tweets(
                    id=user_id,
                    tweet_fields=['created_at'],
                    max_results=100,
                    pagination_token=pagination_token,
                    start_time=start_date.isoformat()
                )

                if not tweets.data:
                    break

                for tweet in tweets.data:
                    created_at = tweet.created_at
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)

                    mock_tweet = MockTweet(
                        id=tweet.id,
                        text=tweet.text,
                        created_at=created_at
                    )
                    historical_tweets.append(mock_tweet)

                if not tweets.meta.get('next_token'):
                    break

                pagination_token = tweets.meta['next_token']
                time.sleep(2)  # Add small delay between requests

            except tweepy.TooManyRequests:
                retry_count += 1
                if retry_count > max_retries:
                    logger.error("Max retries exceeded for rate limit")
                    break

                # Exponential backoff
                delay = base_delay * (2 ** (retry_count - 1))
                logger.info(f"Rate limit hit. Waiting {delay} seconds...")
                time.sleep(delay)
                continue

            except Exception as e:
                logger.error(f"Error fetching historical tweets: {str(e)}")
                break

        return historical_tweets

    def stream_user_tweets(self, username: str, callback, delay: int = 60):
        """Stream new tweets from a user with a callback function"""
        user_id = self.get_user_id(username)
        if not user_id:
            return

        latest_tweet_id = None

        while True:
            try:
                tweets = self.client.get_users_tweets(
                    id=user_id,
                    tweet_fields=["created_at"],
                    since_id=latest_tweet_id,
                    max_results=10,
                )

                if tweets.data:
                    latest_tweet_id = tweets.data[0].id
                    for tweet in tweets.data:
                        mock_tweet = MockTweet(
                            id=tweet.id,
                            text=tweet.text,
                            created_at=tweet.created_at
                        )
                        callback(mock_tweet)

                time.sleep(delay)

            except Exception as e:
                logger.error(f"Error streaming tweets: {str(e)}")
                time.sleep(delay)
