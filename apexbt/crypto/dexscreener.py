import logging
import requests
import traceback


class DexScreener:
    """Client for interacting with DexScreener API"""

    def __init__(self):
        # Set up logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def get_token_by_ticker(self, ticker):
        """
        Get token market data from DexScreener API for most liquid pair with market cap check

        Args:
            ticker (str): Token symbol/ticker to search for

        Returns:
            dict: Market data including price, volume, liquidity etc. or None if error/no data
        """
        try:
            url = f"https://api.dexscreener.com/latest/dex/search?q={ticker}"
            response = requests.get(url)

            if response.status_code == 200:
                data = response.json()
                pairs = data.get("pairs", [])

                self.logger.info(f"Number of pairs found: {len(pairs)}")

                if not pairs:
                    self.logger.warning(f"No pairs found for {ticker} on DexScreener")
                    return None

                # Filter pairs to ensure base token symbol matches ticker
                matching_pairs = [
                    pair
                    for pair in pairs
                    if pair.get("baseToken", {}).get("symbol", "").upper()
                    == ticker.upper()
                ]

                self.logger.info(f"Number of matching pairs: {len(matching_pairs)}")

                if not matching_pairs:
                    self.logger.warning(
                        f"No pairs found with matching ticker {ticker} on DexScreener"
                    )
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
                    "liquidity": float(
                        best_pair.get("liquidity", {}).get("usd", 0) or 0
                    ),
                    "percent_change_24h": float(
                        best_pair.get("priceChange", {}).get("h24", 0) or 0
                    ),
                    "dex": best_pair.get("dexId"),
                    "network": best_pair.get("chainId"),
                    "pair_name": f"{best_pair.get('baseToken', {}).get('symbol')}/{best_pair.get('quoteToken', {}).get('symbol')}",
                    "last_updated": best_pair.get("pairCreatedAt"),
                    "pair_address": best_pair.get("pairAddress"),
                    "contract_address": best_pair.get("baseToken", {}).get("address"),
                    "market_cap": market_cap,
                }

            else:
                self.logger.error(
                    f"DexScreener API error ({response.status_code}): {response.text}"
                )
                return None

        except Exception as e:
            self.logger.error(
                f"Error getting DexScreener market data for {ticker}: {str(e)}"
            )
            self.logger.error(f"Exception traceback: {traceback.format_exc()}")
            return None

    def get_token_by_address(self, contract_address, chain_id):
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
            response = requests.get(url)

            if response.status_code == 200:
                pairs = response.json()  # API returns array with single pair object

                if not pairs or len(pairs) == 0:
                    self.logger.warning(
                        f"No pairs found for contract {contract_address} on chain {chain_id}"
                    )
                    return None

                # Get the first (and usually only) pair
                best_pair = pairs[0]

                # Use the market cap provided by the API
                market_cap = float(best_pair.get("marketCap", 0) or 0)
                price_usd = float(best_pair.get("priceUsd", 0) or 0)

                return {
                    "current_price": price_usd,
                    "volume_24h": float(best_pair.get("volume", {}).get("h24", 0) or 0),
                    "liquidity": float(
                        best_pair.get("liquidity", {}).get("usd", 0) or 0
                    ),
                    "percent_change_24h": float(
                        best_pair.get("priceChange", {}).get("h24", 0) or 0
                    ),
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
                self.logger.error(
                    f"DexScreener API error ({response.status_code}): {response.text}"
                )
                return None

        except Exception as e:
            self.logger.error(
                f"Error getting DexScreener data for {contract_address} on {chain_id}: {str(e)}"
            )
            self.logger.error(f"Exception traceback: {traceback.format_exc()}")
            return None
