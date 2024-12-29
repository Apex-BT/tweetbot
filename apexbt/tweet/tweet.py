# apexbt/apexbt/tweet/tweet.py
import tweepy
import logging
import re
from datetime import datetime, timezone
from dataclasses import dataclass
from apexbt.config import config
from typing import Tuple, List, Optional
import time
from apexbt.database.database import get_db_connection

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class MockTweet:
    """Mock Tweet class to simulate Twitter API response"""
    id: int
    text: str
    created_at: datetime
    author: str = "Unknown"

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

    def get_latest_tweet_id_by_agent(self, username: str) -> Optional[str]:
        """Get the latest processed tweet ID for a specific AI agent from database"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT tweet_id FROM tweets
                    WHERE ai_agent = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (username,))
                result = cursor.fetchone()
                return result['tweet_id'] if result else None
        except Exception as e:
            logger.error(f"Error getting latest tweet ID for {username}: {str(e)}")
            return None

    def fetch_historical_tweets(self, username: str, start_date: datetime) -> List[MockTweet]:
        """Fetch historical tweets (excluding replies) from a specific user since start_date"""
        historical_tweets = []
        user_id = self.get_user_id(username)

        if not user_id:
            logger.error(f"Could not find user ID for {username}")
            return []

        latest_tweet_id = self.get_latest_tweet_id_by_agent(username)
        logger.info(f"Latest processed tweet ID for {username}: {latest_tweet_id}")

        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)

        start_time = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        pagination_token = None
        retry_count = 0
        max_retries = 5
        batch_count = 0
        total_requests = 0

        while True:
            try:
                base_delay = 5
                batch_delay = min(base_delay + (batch_count * 2), 30)
                logger.info(f"Waiting {batch_delay} seconds before next request...")
                time.sleep(batch_delay)

                # Add exclude parameter to filter out replies
                tweets = self.client.get_users_tweets(
                    id=user_id,
                    tweet_fields=['created_at', 'referenced_tweets'],  # Add referenced_tweets field
                    max_results=100,
                    pagination_token=pagination_token,
                    since_id=latest_tweet_id,
                    start_time=start_time,
                    end_time=end_time,
                    exclude=['replies']  # Exclude replies
                )

                total_requests += 1
                logger.info(f"Made {total_requests} requests for @{username}")

                if not tweets.data:
                    logger.info(f"No more tweets found for @{username}")
                    break

                new_tweets = 0
                for tweet in tweets.data:
                    # Skip if it's a reply or retweet
                    if hasattr(tweet, 'referenced_tweets') and tweet.referenced_tweets:
                        continue

                    if latest_tweet_id and str(tweet.id) <= latest_tweet_id:
                        continue

                    created_at = tweet.created_at
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)

                    if created_at >= start_date and created_at <= datetime.now(timezone.utc):
                        mock_tweet = MockTweet(
                            id=tweet.id,
                            text=tweet.text,
                            created_at=created_at,
                            author=username
                        )
                        historical_tweets.append(mock_tweet)
                        new_tweets += 1

                batch_count += 1
                logger.info(f"Batch {batch_count}: Fetched {new_tweets} new original tweets from @{username}")

                if new_tweets == 0:
                    logger.info(f"No new tweets in this batch for @{username}")
                    break

                if not tweets.meta.get('next_token'):
                    logger.info(f"No more pages available for @{username}")
                    break

                pagination_token = tweets.meta['next_token']

                # Reset retry count on successful request
                retry_count = 0

            except tweepy.errors.TooManyRequests as e:
                logger.warning(f"Rate limit exceeded for @{username}")
                retry_count += 1
                if retry_count > max_retries:
                    logger.error(f"Max retries ({max_retries}) reached for @{username}")
                    break
                exponential_backoff(retry_count)
                continue

            except Exception as e:
                logger.error(f"Error fetching tweets for @{username}: {str(e)}")
                retry_count += 1
                if retry_count > max_retries:
                    logger.error(f"Max retries ({max_retries}) reached due to errors")
                    break
                time.sleep(60)
                continue

        logger.info(f"Completed fetching tweets for @{username}. Total tweets: {len(historical_tweets)}")
        return historical_tweets

    def monitor_multiple_users(self, usernames: List[str], callback, delay: int = 60):
        """Monitor tweets from multiple users"""
        user_ids = {}
        latest_tweet_ids = {}

        # Get user IDs for all usernames
        for username in usernames:
            user_id = self.get_user_id(username)
            if user_id:
                user_ids[username] = user_id
                latest_tweet_ids[username] = self.get_latest_tweet_id_by_agent(username)
            else:
                logger.error(f"Could not find user ID for {username}")

        while True:
                try:
                    for username, user_id in user_ids.items():
                        try:
                            tweets = self.client.get_users_tweets(
                                id=user_id,
                                tweet_fields=["created_at", "referenced_tweets"],
                                since_id=latest_tweet_ids[username],
                                max_results=10,
                                exclude=['replies']  # Exclude replies
                            )

                            if tweets.data:
                                latest_tweet_ids[username] = tweets.data[0].id
                                for tweet in tweets.data:
                                    # Skip if it's a reply or retweet
                                    if hasattr(tweet, 'referenced_tweets') and tweet.referenced_tweets:
                                        continue

                                    mock_tweet = MockTweet(
                                        id=tweet.id,
                                        text=tweet.text,
                                        created_at=tweet.created_at,
                                        author=username
                                    )
                                    callback(mock_tweet)

                            time.sleep(2)  # Small delay between users

                        except Exception as e:
                            logger.error(f"Error fetching tweets for {username}: {str(e)}")
                            continue

                    time.sleep(delay)

                except Exception as e:
                    logger.error(f"Error in monitor loop: {str(e)}")
                    time.sleep(delay)

def exponential_backoff(retry_count):
    """Implement exponential backoff for rate limiting"""
    wait_time = min(60 * (2 ** retry_count), 900)  # Max 15 minutes
    logger.info(f"Rate limit hit. Waiting {wait_time} seconds...")
    time.sleep(wait_time)
