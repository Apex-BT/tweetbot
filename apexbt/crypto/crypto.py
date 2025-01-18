import logging
import requests
import traceback
from config.config import MARKET_CAP_FILTER

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_crypto_price_dexscreener(ticker):
    """
    Get cryptocurrency price data from DexScreener API for most liquid pair with market cap check
    """
    try:
        url = f"https://api.dexscreener.com/latest/dex/search?q={ticker}"
        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()

            pairs = data.get("pairs", [])

            logger.info(f"Number of pairs found: {len(pairs)}")

            if not pairs:
                logger.warning(f"No pairs found for {ticker} on DexScreener")
                return None

            # Filter pairs to ensure base token symbol matches ticker
            matching_pairs = [
                pair
                for pair in pairs
                if pair.get("baseToken", {}).get("symbol", "").upper() == ticker.upper()
            ]

            logger.info(f"Number of matching pairs: {len(matching_pairs)}")

            if not matching_pairs:
                logger.warning(
                    f"No pairs found with matching ticker {ticker} on DexScreener"
                )
                return None

            # Sort pairs by liquidity and volume first
            sorted_pairs = sorted(
                matching_pairs,
                key=lambda x: (
                    float(x.get("volume", {}).get("h24", 0) or 0),
                    float(
                        x.get("liquidity", {}).get("usd", 0) or 0
                    ),
                ),
                reverse=True,
            )

            # Get the most liquid pair
            best_pair = sorted_pairs[0]

            # Use the market cap provided by the API
            market_cap = float(best_pair.get("marketCap", 0) or 0)
            price_usd = float(best_pair.get("priceUsd", 0) or 0)

            # Check if market cap is <= MARKET_CAP_FILTER
            if market_cap >= MARKET_CAP_FILTER:
                logger.warning(
                    f"Most liquid pair for {ticker} has market cap (${market_cap:,.2f}) > ${MARKET_CAP_FILTER} - skipping"
                )
                return None

            return {
                "current_price": price_usd,
                "volume_24h": float(best_pair.get("volume", {}).get("h24", 0) or 0),
                "liquidity": float(best_pair.get("liquidity", {}).get("usd", 0) or 0),
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
            logger.error(
                f"DexScreener API error ({response.status_code}): {response.text}"
            )
            return None

    except Exception as e:
        logger.error(f"Error getting DexScreener price for {ticker}: {str(e)}")
        logger.error(f"Exception traceback: {traceback.format_exc()}")
        return None
