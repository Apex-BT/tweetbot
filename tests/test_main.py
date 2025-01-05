from datetime import datetime
from dataclasses import dataclass
from apexbt.sheets.sheets import save_tweet_to_sheets, setup_google_sheets
from apexbt.crypto.crypto import get_crypto_price
from apexbt.main import extract_ticker


@dataclass
class MockTweet:
    """Mock Tweet class to simulate Twitter API response"""

    id: int
    text: str
    created_at: datetime


def process_test_tweets():
    """Process a list of sample tweets and write to Google Sheet"""
    # Setup test tweets
    sample_tweets = [
        MockTweet(
            id=1,
            text="$WBTC is currently trading at $70m mcap, up 47% in the last 24 hrs.",
            created_at=datetime.now(),
        ),
        MockTweet(
            id=2,
            text="""⚠️ ai-agent alert:
             $goat has declined with an abnormal return of 13.39% in the last hour. 📉

            abnormal returns show price changes that deviate from the market norm.""",
            created_at=datetime.now(),
        ),
        MockTweet(
            id=3,
            text="""ai-agent alert:
            - $ubc has surged with an abnormal return of 13.67% in the last hour 📈
            - $kwant has declined with an abnormal return of 14.46% in the last hour 📉

            unusual price movements are captured as abnormal returns.""",
            created_at=datetime.now(),
        ),
        MockTweet(
            id=4,
            text="""$poly is currently trading at $9m mcap, up 23% in the last 24 hrs.
""",
            created_at=datetime.now(),
        ),
        MockTweet(
            id=5,
            text="""ai-agent token index update:
            current index return: +6.04% last 24-hours
            featured tokens: $max (+258.66%), $kween (+47.28%), $lum (-25.43%), $vvaifu (-23.85%)""",
            created_at=datetime.now(),
        ),
    ]

    # Setup Google Sheets
    sheet = setup_google_sheets()

    # Process each tweet
    for tweet in sample_tweets:
        ticker, ticker_status = extract_ticker(tweet.text)

        price_data = None
        if ticker_status == "Single ticker":
            price_data = get_crypto_price(ticker, tweet.created_at)
        save_tweet_to_sheets(sheet, tweet, ticker, ticker_status, price_data)
        print(f"Processed tweet {tweet.id}: {tweet.text}")


if __name__ == "__main__":
    print("Starting test tweet processing...")
    process_test_tweets()
    print("Finished processing test tweets. Check Google Sheet for results.")
