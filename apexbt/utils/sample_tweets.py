from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class MockTweet:
    """Mock Tweet class to simulate Twitter API response"""

    id: int
    text: str
    created_at: datetime
    author: str = "Unknown"


sample_tweets = [
    MockTweet(
        id=1,
        text="$TNSR is currently trading at $70m mcap, up 47% in the last 24 hrs.",
        created_at=datetime.now() - timedelta(days=1),
        author="aixbt_agent",
    ),
    MockTweet(
        id=2,
        text="$ai16z is currently trading at $70m mcap, up 47% in the last 24 hrs.",
        created_at=datetime.now() - timedelta(days=2),
        author="aixbt_agent",
    ),
    MockTweet(
        id=3,
        text="$LEXICON is currently trading at $70m mcap, up 47% in the last 24 hrs.",
        created_at=datetime.now() - timedelta(days=3),
        author="aixbt_agent",
    ),
    MockTweet(
        id=4,
        text="$PENDLE is currently trading at $70m mcap, up 47% in the last 24 hrs.",
        created_at=datetime.now() - timedelta(days=4),
        author="tri_sigma_",
    ),
    MockTweet(
        id=5,
        text="$XAI is currently trading at $70m mcap, up 47% in the last 24 hrs.",
        created_at=datetime.now() - timedelta(days=5),
        author="tri_sigma_",
    ),
]
