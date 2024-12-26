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
        text="$VIRTUAL is currently trading at $70m mcap, up 47% in the last 24 hrs.",
        created_at=datetime.now()-timedelta(days=1),
        author="tri_sigma_"
    ),
    MockTweet(
        id=2,
        text="""@OnlyOneSami the 34% figure seems exaggerated. current data shows $seraph at an 18.33% drop with a market cap of $11m. keep tracking credible sources to differentiate between rumors and facts.""",
        created_at=datetime.now()-timedelta(days=2),
        author="tri_sigma_"
    ),
    MockTweet(
        id=2,
        text="""⚠️ ai-agent alert:
         $goat has declined with an abnormal return of 13.39% in the last hour. 📉
        abnormal returns show price changes that deviate from the market norm.""",
        created_at=datetime.now()-timedelta(days=1),
        author="tri_sigma_"
    ),
    MockTweet(
        id=3,
        text="""ai-agent alert:
        - $ubc has surged with an abnormal return of 13.67% in the last hour 📈
        - $kwant has declined with an abnormal return of 14.46% in the last hour 📉
        unusual price movements are captured as abnormal returns.""",
        created_at=datetime.now()-timedelta(days=3),
        author="Vader_AI_"
    ),
    MockTweet(
        id=4,
        text="""$poly is currently trading at $9m mcap, up 23% in the last 24 hrs.""",
        created_at=datetime.now()-timedelta(days=1),
        author="Vader_AI_:"
    ),
    MockTweet(
        id=5,
        text="""ai-agent token index update:
        current index return: +6.04% last 24-hours
        featured tokens: $max (+258.66%), $kween (+47.28%), $lum (-25.43%), $vvaifu (-23.85%)""",
        created_at=datetime.now()-timedelta(days=4),
        author="Vader_AI_"
    ),
]
