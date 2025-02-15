from dataclasses import dataclass
import logging
from apexbt.crypto.sniffer import SolSnifferAPI



logger = logging.getLogger(__name__)

from enum import Enum

class TokenSource(Enum):
    TWITTER = "twitter"
    PUMPFUN = "pumpfun"
    VIRTUALS = "virtuals"

@dataclass
class ValidationCriteria:
    min_market_cap: float
    max_market_cap: float
    min_liquidity: float
    min_volume_24h: float
    source: TokenSource

    @classmethod
    def twitter_default(cls) -> 'ValidationCriteria':
        """Default criteria for Twitter-sourced tokens"""
        return cls(
            min_market_cap=1_000_000,     # $1M minimum
            max_market_cap=250_000_000,   # $250M maximum
            min_liquidity=100_000,        # $100K minimum liquidity
            min_volume_24h=50_000,        # $50K minimum 24h volume
            source=TokenSource.TWITTER
        )

    @classmethod
    def pumpfun_default(cls) -> 'ValidationCriteria':
        """Default criteria for PumpFun tokens (new Solana launches)"""
        return cls(
            min_market_cap=0,           # No minimum since it's new
            max_market_cap=10_000_000,  # $10M maximum to focus on new launches
            min_liquidity=0,        # $5K minimum initial liquidity
            min_volume_24h=1_000,       # $1K minimum initial volume
            source=TokenSource.PUMPFUN
        )

    @classmethod
    def virtuals_default(cls) -> 'ValidationCriteria':
        """Default criteria for Virtuals tokens"""
        return cls(
            min_market_cap=0,           # No minimum since it might be new
            max_market_cap=1_000_000_000,  # $1B maximum
            min_liquidity=10_000,       # $10K minimum liquidity
            min_volume_24h=5_000,       # $5K minimum 24h volume
            source=TokenSource.VIRTUALS
        )

class TokenValidator:
    def __init__(self, criteria: ValidationCriteria = None):
        self.criteria = criteria or ValidationCriteria()
        self.sol_sniffer = SolSnifferAPI()

    def validate_token(self, dex_data: dict) -> tuple[bool, str]:
        """
        Validates a token based on market cap range, liquidity, and 24h volume
        Returns: (is_valid: bool, reason: str)
        """
        if not dex_data:
            return False, "No token data available"

        # Check market cap range
        market_cap = float(dex_data.get("market_cap", 0))
        if market_cap < self.criteria.min_market_cap:
            return False, f"Market cap too low: ${market_cap:,.2f} (min: ${self.criteria.min_market_cap:,.2f})"
        if market_cap > self.criteria.max_market_cap:
            return False, f"Market cap too high: ${market_cap:,.2f} (max: ${self.criteria.max_market_cap:,.2f})"

        # Check liquidity
        liquidity = float(dex_data.get("liquidity", 0))
        if liquidity < self.criteria.min_liquidity:
            return False, f"Liquidity too low: ${liquidity:,.2f} (min: ${self.criteria.min_liquidity:,.2f})"

        # Check 24h volume
        volume_24h = float(dex_data.get("volume_24h", 0))
        if volume_24h < self.criteria.min_volume_24h:
            return False, f"24h volume too low: ${volume_24h:,.2f} (min: ${self.criteria.min_volume_24h:,.2f})"


        # For PumpFun tokens, validate with SolSniffer first
        if self.criteria.source == TokenSource.PUMPFUN:
            token_address = dex_data.get("address")
            if not token_address:
                return False, "No token address provided"

            sniffer_data = self.sol_sniffer.get_token_data([token_address])
            if not sniffer_data or "data" not in sniffer_data:
                return False, "Failed to fetch token data from SolSniffer"

            # Get the token data for this specific address
            token_info = next((t for t in sniffer_data["data"]
                             if t["address"] == token_address), None)
            if not token_info:
                return False, "Token not found in SolSniffer response"

            score = token_info["tokenData"].get("score", 0)
            if score < 80:
                return False, f"Token score too low: {score} (minimum: 80)"


        return True, "Token passed all validation criteria"
