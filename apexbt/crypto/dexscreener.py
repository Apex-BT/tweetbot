import logging
import requests
import traceback
import time
from threading import Lock


class RateLimiter:
    def __init__(self, max_requests, time_window):
        self.max_requests = max_requests
        self.time_window = time_window  # in seconds
        self.tokens = max_requests
        self.last_update = time.time()
        self.lock = Lock()

    def acquire(self):
        with self.lock:
            now = time.time()
            time_passed = now - self.last_update
            self.tokens = min(
                self.max_requests,
                self.tokens + time_passed * (self.max_requests / self.time_window)
            )
            self.last_update = now

            if self.tokens < 1:
                # Calculate sleep time needed for at least one token
                sleep_time = (1 - self.tokens) * (self.time_window / self.max_requests)
                time.sleep(sleep_time)
                self.tokens = 1

            self.tokens -= 1
            return True


class DexScreener:
    """Client for interacting with DexScreener API"""

    # Class-level rate limiter
    rate_limiter = RateLimiter(max_requests=300, time_window=60)
    logger = logging.getLogger(__name__)

    @staticmethod
    def _make_request(url):
        """
        Make a rate-limited request to the DexScreener API
        """
        DexScreener.rate_limiter.acquire()
        return requests.get(url)

    @staticmethod
    def get_token_by_ticker(ticker):
        """
        Get token market data from DexScreener API for most liquid pair with market cap check

        Args:
            ticker (str): Token symbol/ticker to search for

        Returns:
            dict: Market data including price, volume, liquidity etc. or None if error/no data
        """
        try:
            url = f"https://api.dexscreener.com/latest/dex/search?q={ticker}"
            response = DexScreener._make_request(url)

            if response.status_code == 200:
                data = response.json()
                pairs = data.get("pairs", [])

                DexScreener.logger.info(f"Number of pairs found: {len(pairs)}")

                if not pairs:
                    DexScreener.logger.warning(f"No pairs found for {ticker} on DexScreener")
                    return None

                # Filter pairs to ensure base token symbol matches ticker
                matching_pairs = [
                    pair
                    for pair in pairs
                    if pair.get("baseToken", {}).get("symbol", "").upper() == ticker.upper()
                ]

                DexScreener.logger.info(f"Number of matching pairs: {len(matching_pairs)}")

                if not matching_pairs:
                    DexScreener.logger.warning(f"No pairs found with matching ticker {ticker} on DexScreener")
                    return None

                # Sort pairs by liquidity and volume first
                sorted_pairs = sorted(
                    matching_pairs,
                    key=lambda x: (
                        float(x.get("volume", {}).get("h24", 0) or 0),
                        float(x.get("liquidity", {}).get("usd", 0) or 0),
                    ),
                    reverse=True,
                )

                # Get the most liquid pair
                best_pair = sorted_pairs[0]

                # Use the market cap provided by the API
                market_cap = float(best_pair.get("marketCap", 0) or 0)
                price_usd = float(best_pair.get("priceUsd", 0) or 0)

                return {
                    "current_price": price_usd,
                    "volume_24h": float(best_pair.get("volume", {}).get("h24", 0) or 0),
                    "liquidity": float(best_pair.get("liquidity", {}).get("usd", 0) or 0),
                    "percent_change_24h": float(best_pair.get("priceChange", {}).get("h24", 0) or 0),
                    "dex": best_pair.get("dexId"),
                    "network": best_pair.get("chainId"),
                    "pair_name": f"{best_pair.get('baseToken', {}).get('symbol')}/{best_pair.get('quoteToken', {}).get('symbol')}",
                    "last_updated": best_pair.get("pairCreatedAt"),
                    "pair_address": best_pair.get("pairAddress"),
                    "contract_address": best_pair.get("baseToken", {}).get("address"),
                    "market_cap": market_cap,
                }

            else:
                DexScreener.logger.error(f"DexScreener API error ({response.status_code}): {response.text}")
                return None

        except Exception as e:
            DexScreener.logger.error(f"Error getting DexScreener market data for {ticker}: {str(e)}")
            DexScreener.logger.error(f"Exception traceback: {traceback.format_exc()}")
            return None

    @staticmethod
    def get_token_by_address(contract_address, chain_id):
        """
        Get token market data from DexScreener API using contract address and chain ID

        Args:
            chain_id (str): Chain ID (e.g., 'ethereum', 'bsc', 'solana')
            contract_address (str): Token contract address

        Returns:
            dict: Market data including price, volume, liquidity etc. or None if error/no data
        """
        try:
            url = f"https://api.dexscreener.com/tokens/v1/{chain_id}/{contract_address}"
            response = DexScreener._make_request(url)

            if response.status_code == 200:
                pairs = response.json()  # API returns array with single pair object

                if not pairs or len(pairs) == 0:
                    DexScreener.logger.warning(f"No pairs found for contract {contract_address} on chain {chain_id}")
                    return None

                # Get the first (and usually only) pair
                best_pair = pairs[0]

                # Use the market cap provided by the API
                market_cap = float(best_pair.get("marketCap", 0) or 0)
                price_usd = float(best_pair.get("priceUsd", 0) or 0)

                return {
                    "current_price": price_usd,
                    "volume_24h": float(best_pair.get("volume", {}).get("h24", 0) or 0),
                    "liquidity": float(best_pair.get("liquidity", {}).get("usd", 0) or 0),
                    "percent_change_24h": float(best_pair.get("priceChange", {}).get("h24", 0) or 0),
                    "dex": best_pair.get("dexId"),
                    "network": best_pair.get("chainId"),
                    "pair_name": f"{best_pair.get('baseToken', {}).get('symbol')}/{best_pair.get('quoteToken', {}).get('symbol')}",
                    "last_updated": best_pair.get("pairCreatedAt"),
                    "pair_address": best_pair.get("pairAddress"),
                    "contract_address": best_pair.get("baseToken", {}).get("address"),
                    "market_cap": market_cap,
                    "fdv": float(best_pair.get("fdv", 0) or 0),
                    "token_name": best_pair.get("baseToken", {}).get("name"),
                    "token_symbol": best_pair.get("baseToken", {}).get("symbol"),
                }

            else:
                DexScreener.logger.error(f"DexScreener API error ({response.status_code}): {response.text}")
                return None

        except Exception as e:
            DexScreener.logger.error(f"Error getting DexScreener data for {contract_address} on {chain_id}: {str(e)}")
            DexScreener.logger.error(f"Exception traceback: {traceback.format_exc()}")
            return None
