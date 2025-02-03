from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class ValidationCriteria:
    min_market_cap: float = 10000    # Minimum market cap in USD
    max_market_cap: float = 1000000  # Maximum market cap in USD
    min_liquidity: float = 5000      # Minimum liquidity in USD
    min_volume_24h: float = 1000     # Minimum 24h volume in USD

class TokenValidator:
    def __init__(self, criteria: ValidationCriteria = None):
        self.criteria = criteria or ValidationCriteria()

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

        return True, "Token passed all validation criteria"
