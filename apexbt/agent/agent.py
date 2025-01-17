import logging
import time
from dataclasses import dataclass
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate
from google.api_core import retry
from apexbt.config.config import GOOGLE_API_KEY
from threading import Lock

logger = logging.getLogger(__name__)


@dataclass
class SentimentAnalysis:
    is_positive: bool
    confidence: float
    reasoning: str


class RateLimiter:
    def __init__(self, requests_per_minute):
        self.requests_per_minute = requests_per_minute
        self.available_requests = requests_per_minute
        self.last_update = time.time()
        self.lock = Lock()

    def acquire(self):
        with self.lock:
            now = time.time()
            time_passed = now - self.last_update

            # Replenish available requests based on time passed
            self.available_requests = min(
                self.available_requests
                + (time_passed * (self.requests_per_minute / 60)),
                self.requests_per_minute,
            )

            if self.available_requests < 1:
                # Calculate sleep time needed to get 1 request
                sleep_time = (1 - self.available_requests) * (
                    60 / self.requests_per_minute
                )
                time.sleep(sleep_time)
                self.available_requests = 1

            self.available_requests -= 1
            self.last_update = now


class TradeAgent:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            google_api_key=GOOGLE_API_KEY,
            temperature=0,
            max_output_tokens=150,
        )

        # Initialize rate limiter for 15 requests per minute
        self.request_rate_limiter = RateLimiter(requests_per_minute=15)

        self.system_prompt = """You are a cryptocurrency tweet analyzer.
        Your only task is to determine if a tweet expresses positive or negative sentiment about a specific token.

        Return your analysis in exactly this format:
        SENTIMENT|CONFIDENCE|REASONING

        Where:
        - SENTIMENT must be exactly POSITIVE or NEGATIVE
        - CONFIDENCE must be a number between 0.0 and 1.0
        - REASONING should be a brief explanation

        Example response:
        POSITIVE|0.85|Tweet shows enthusiasm about token's potential and growth"""

        self.prompt_template = """Tweet: {tweet_text}
        Token: {token}

        Is this tweet positive or negative regarding this specific token?
        Only mark as NEGATIVE if there's clear negative sentiment."""

    @retry.Retry()
    def analyze_sentiment(self, tweet_text: str, token: str) -> SentimentAnalysis:
        try:
            # Acquire rate limit token before making the API call
            self.rate_limiter.acquire()

            prompt = ChatPromptTemplate.from_messages(
                [("system", self.system_prompt), ("human", self.prompt_template)]
            )

            chain = prompt | self.llm

            response = chain.invoke({"tweet_text": tweet_text, "token": token})

            try:
                sentiment, confidence, reasoning = response.content.strip().split("|")
                confidence = float(confidence)

                analysis = SentimentAnalysis(
                    is_positive=(sentiment.strip().upper() == "POSITIVE"),
                    confidence=min(max(confidence, 0.0), 1.0),  # Clamp between 0 and 1
                    reasoning=reasoning.strip(),
                )

                logger.info(
                    f"Sentiment analysis for {token}:\n"
                    f"Sentiment: {'POSITIVE' if analysis.is_positive else 'NEGATIVE'}\n"
                    f"Confidence: {analysis.confidence}\n"
                    f"Reasoning: {analysis.reasoning}"
                )

                return analysis

            except Exception as parse_error:
                logger.error(f"Error parsing model response: {str(parse_error)}")
                logger.error(f"Raw response: {response.content}")
                return SentimentAnalysis(
                    is_positive=True,  # Default to positive if parsing fails
                    confidence=0.0,
                    reasoning=f"Error parsing response: {response.content}",
                )

        except Exception as e:
            logger.error(f"Error in sentiment analysis: {str(e)}")
            return SentimentAnalysis(
                is_positive=True,  # Default to positive
                confidence=0.0,
                reasoning=f"Error in analysis: {str(e)}",
            )

    def should_take_trade(self, tweet_text: str, token: str) -> bool:
        """
        Only reject trade if we're confident the sentiment is negative.
        """
        analysis = self.analyze_sentiment(tweet_text, token)

        # Reject only if we're confident (>0.7) that sentiment is negative
        should_reject = not analysis.is_positive and analysis.confidence > 0.7

        if should_reject:
            logger.info(
                f"Trade rejected due to negative sentiment: {analysis.reasoning}"
            )
            return False

        return True  # Accept all other cases
