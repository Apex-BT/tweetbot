# apexbt/apexbt/tweet/tweet.py
import tweepy
import logging
import asyncio
import re
from datetime import datetime, timezone
from dataclasses import dataclass
from apexbt.config.config import config
from typing import Tuple, List, Optional, Callable, Any
import time
from collections import deque
from apexbt.database.database import Database


class RateLimiter:
    def __init__(self, max_requests, time_window):
        self.max_requests = max_requests
        self.time_window = time_window  # in seconds
        self.requests = deque()
        self.reset_time = None
        self.remaining_requests = None
        self.rate_limit_ceiling = None

    def update_from_headers(self, headers):
        """Update rate limit info from response headers"""
        try:
            self.rate_limit_ceiling = int(headers.get("x-rate-limit-limit", 0))
            self.remaining_requests = int(headers.get("x-rate-limit-remaining", 0))
            self.reset_time = int(headers.get("x-rate-limit-reset", 0))

            logger.info(f"Rate Limit Headers:")
            logger.info(f"  Limit ceiling: {self.rate_limit_ceiling}")
            logger.info(f"  Remaining requests: {self.remaining_requests}")
            logger.info(
                f"  Reset time: {datetime.fromtimestamp(self.reset_time).strftime('%Y-%m-%d %H:%M:%S')}"
            )
        except Exception as e:
            logger.error(f"Error parsing rate limit headers: {str(e)}")

    async def wait_for_reset_async(self):
        """Async wait until the rate limit resets"""
        if self.reset_time:
            now = time.time()
            wait_time = max(0, self.reset_time - now)
            if wait_time > 0:
                logger.info(
                    f"Rate limit reached. Waiting {wait_time:.2f} seconds until reset at "
                    f"{datetime.fromtimestamp(self.reset_time).strftime('%Y-%m-%d %H:%M:%S')}"
                )
                await asyncio.sleep(wait_time)

    def can_make_request(self):
        """Check if we can make a request based on headers"""
        if self.remaining_requests is not None:
            return self.remaining_requests > 0

        now = time.time()
        while self.requests and self.requests[0] < now - self.time_window:
            self.requests.popleft()
        if len(self.requests) < self.max_requests:
            self.requests.append(now)
            return True
        return False


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
    def __init__(self, db: Database):
        self.db = db
        self.api_key = config.TWITTER_API_KEY
        self.api_secret = config.TWITTER_API_SECRET
        self.access_token = config.TWITTER_ACCESS_TOKEN
        self.access_token_secret = config.TWITTER_ACCESS_TOKEN_SECRET
        self.bearer_token = config.TWITTER_BEARER_TOKEN
        self.client = self._setup_client()
        self.running = True

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

    async def monitor(
        self,
        usernames: List[str],
        callback: Callable[[MockTweet], Any],
        delay: int = 60,
    ):
        """Async monitor tweets from multiple users with rate limiting"""
        logger.info(
            f"Starting async tweet monitoring for users: {', '.join(usernames)}"
        )
        user_ids = {}
        latest_tweet_ids = {}
        rate_limiter = RateLimiter(max_requests=900, time_window=15 * 60)

        # Get user IDs for all usernames
        logger.info("Initializing user IDs and latest tweet IDs...")
        for username in usernames:
            user_id = self.get_user_id(username)
            if user_id:
                user_ids[username] = user_id
                latest_tweet_ids[username] = self.db.get_latest_tweet_id_by_agent(
                    username
                )
                logger.info(f"Initialized @{username} - User ID: {user_id}")
            else:
                logger.error(f"Could not find user ID for @{username}")

        monitoring_iteration = 0

        while self.running:
            monitoring_iteration += 1
            logger.info(f"Starting monitoring iteration {monitoring_iteration}")

            try:
                for username, user_id in user_ids.items():
                    if not self.running:
                        break

                    logger.info(f"Checking tweets for @{username}")
                    try:
                        if not rate_limiter.can_make_request():
                            await rate_limiter.wait_for_reset_async()

                        response = self.client.get_users_tweets(
                            id=user_id,
                            tweet_fields=["created_at", "referenced_tweets"],
                            since_id=latest_tweet_ids[username],
                            max_results=10,
                            exclude=["replies"],
                        )

                        if hasattr(response, "headers"):
                            rate_limiter.update_from_headers(response.headers)

                        if response.data:
                            latest_tweet_ids[username] = response.data[0].id

                            for tweet in response.data:
                                if (
                                    hasattr(tweet, "referenced_tweets")
                                    and tweet.referenced_tweets
                                ):
                                    continue

                                mock_tweet = MockTweet(
                                    id=tweet.id,
                                    text=tweet.text,
                                    created_at=tweet.created_at,
                                    author=username,
                                )
                                await callback(mock_tweet)

                        await asyncio.sleep(15)  # Wait between users

                    except tweepy.errors.TooManyRequests as e:
                        logger.warning(f"Rate limit exceeded for @{username}")
                        if hasattr(e, "response") and e.response is not None:
                            rate_limiter.update_from_headers(e.response.headers)
                        await rate_limiter.wait_for_reset_async()
                        continue
                    except Exception as e:
                        logger.error(
                            f"Error processing tweets for @{username}: {str(e)}"
                        )
                        continue

                logger.info(f"Completed iteration {monitoring_iteration}")
                await asyncio.sleep(delay)

            except Exception as e:
                logger.error(f"Critical error in monitoring loop: {str(e)}")
                await asyncio.sleep(delay)

    def fetch_historical_tweets(
        self, username: str, start_date: datetime
    ) -> List[MockTweet]:
        """Fetch historical tweets (excluding replies) from a specific user since start_date"""
        historical_tweets = []
        user_id = self.get_user_id(username)
        rate_limiter = RateLimiter(max_requests=900, time_window=15 * 60)

        if not user_id:
            logger.error(f"Could not find user ID for {username}")
            return []

        latest_tweet_id = self.db.get_latest_tweet_id_by_agent(username)
        logger.info(f"Latest processed tweet ID for {username}: {latest_tweet_id}")

        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)

        start_time = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        pagination_token = None
        batch_count = 0
        total_requests = 0

        while True:
            try:
                # Check rate limits before making request
                if not rate_limiter.can_make_request():
                    logger.info("Rate limit check failed, waiting for reset...")
                    rate_limiter.wait_for_reset()

                base_delay = 5
                batch_delay = min(base_delay + (batch_count * 2), 30)
                logger.info(f"Waiting {batch_delay} seconds before next request...")
                time.sleep(batch_delay)

                tweets = self.client.get_users_tweets(
                    id=user_id,
                    tweet_fields=["created_at", "referenced_tweets"],
                    max_results=100,
                    pagination_token=pagination_token,
                    since_id=latest_tweet_id,
                    start_time=start_time,
                    end_time=end_time,
                    exclude=["replies"],
                )

                # Update rate limit info from response headers
                if hasattr(tweets, "headers"):
                    logger.info("Updating rate limit info")
                    rate_limiter.update_from_headers(tweets.headers)

                total_requests += 1
                logger.info(f"Made {total_requests} requests for @{username}")

                if not tweets.data:
                    logger.info(f"No more tweets found for @{username}")
                    break

                new_tweets = 0
                for tweet in tweets.data:
                    if hasattr(tweet, "referenced_tweets") and tweet.referenced_tweets:
                        continue

                    if latest_tweet_id and str(tweet.id) <= latest_tweet_id:
                        continue

                    created_at = tweet.created_at
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)

                    if created_at >= start_date and created_at <= datetime.now(
                        timezone.utc
                    ):
                        mock_tweet = MockTweet(
                            id=tweet.id,
                            text=tweet.text,
                            created_at=created_at,
                            author=username,
                        )
                        historical_tweets.append(mock_tweet)
                        new_tweets += 1

                batch_count += 1
                logger.info(
                    f"Batch {batch_count}: Fetched {new_tweets} new original tweets from @{username}"
                )

                if new_tweets == 0:
                    logger.info(f"No new tweets in this batch for @{username}")
                    break

                if not tweets.meta.get("next_token"):
                    logger.info(f"No more pages available for @{username}")
                    break

                pagination_token = tweets.meta["next_token"]

            except tweepy.errors.TooManyRequests as e:
                logger.warning(f"Rate limit exceeded for @{username}")
                if hasattr(e, "response") and e.response is not None:
                    logger.info("Updating rate limit info from error response")
                    rate_limiter.update_from_headers(e.response.headers)
                rate_limiter.wait_for_reset()
                continue

            except Exception as e:
                logger.error(f"Error fetching tweets for @{username}: {str(e)}")
                time.sleep(60)  # Basic error backoff
                continue

        logger.info(
            f"Completed fetching tweets for @{username}. Total tweets: {len(historical_tweets)}"
        )
        return historical_tweets
