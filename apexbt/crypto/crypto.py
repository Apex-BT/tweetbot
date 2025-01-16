import apexbt.config.config as config
import logging
from requests import Session
import requests
from datetime import timedelta, datetime, timezone
import time

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, calls_per_minute=25):  # CMC Free tier allows 30 calls/minute
        self.calls_per_minute = calls_per_minute
        self.calls = []

    def wait_if_needed(self):
        """Wait if we've exceeded our rate limit"""
        now = time.time()

        # Remove calls older than 1 minute
        self.calls = [call_time for call_time in self.calls if call_time > now - 60]

        if len(self.calls) >= self.calls_per_minute:
            # Wait until oldest call is 1 minute old
            sleep_time = self.calls[0] - (now - 60)
            if sleep_time > 0:
                logger.info(f"Rate limit reached. Waiting {sleep_time:.1f} seconds...")
                time.sleep(sleep_time)

            # Clean up old calls again
            self.calls = [
                call_time for call_time in self.calls if call_time > time.time() - 60
            ]

        # Add current call
        self.calls.append(now)


rate_limiter = RateLimiter()


def get_crypto_price_dexscreener(ticker):
    """
    Get cryptocurrency price data from DexScreener API with market cap filter

    Args:
        ticker: Cryptocurrency ticker symbol

    Returns: Dictionary containing price data or None if not found
    """
    try:
        url = f"https://api.dexscreener.com/latest/dex/search?q={ticker}"
        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()
            pairs = data.get('pairs', [])

            if not pairs:
                logger.warning(f"No pairs found for {ticker} on DexScreener")
                return None

            # Filter pairs to ensure base token symbol matches ticker
            matching_pairs = [
                pair for pair in pairs
                if pair.get('baseToken', {}).get('symbol', '').upper() == ticker.upper()
            ]

            if not matching_pairs:
                logger.warning(f"No pairs found with matching ticker {ticker} on DexScreener")
                return None

            # Filter for market cap <= 250M
            filtered_pairs = []
            for pair in matching_pairs:
                # Get market cap in USD
                price_usd = float(pair.get('priceUsd', 0) or 0)
                total_supply = float(pair.get('baseToken', {}).get('totalSupply', 0) or 0)

                # Calculate market cap
                market_cap = price_usd * total_supply

                # Only include pairs with market cap <= 250M
                if market_cap <= 250000000:  # 250 million
                    filtered_pairs.append(pair)
                    logger.info(f"Found {ticker} with market cap: ${market_cap:,.2f}")
                else:
                    logger.info(f"Skipping {ticker} - market cap too high: ${market_cap:,.2f}")

            if not filtered_pairs:
                logger.warning(f"No pairs found for {ticker} with market cap <= 250M")
                return None

            # Sort filtered pairs by both liquidity and volume
            sorted_pairs = sorted(
                filtered_pairs,
                key=lambda x: (
                    float(x.get('volume', {}).get('h24', 0) or 0),  # Prioritize volume
                    float(x.get('liquidity', {}).get('usd', 0) or 0)  # Then liquidity
                ),
                reverse=True
            )

            # Get the pair with highest liquidity and volume
            best_pair = sorted_pairs[0]

            return {
                "current_price": float(best_pair.get('priceUsd', 0) or 0),
                "volume_24h": float(best_pair.get('volume', {}).get('h24', 0) or 0),
                "liquidity": float(best_pair.get('liquidity', {}).get('usd', 0) or 0),
                "percent_change_24h": float(best_pair.get('priceChange', {}).get('h24', 0) or 0),
                "dex": best_pair.get('dexId'),
                "network": best_pair.get('chainId'),
                "pair_name": f"{best_pair.get('baseToken', {}).get('symbol')}/{best_pair.get('quoteToken', {}).get('symbol')}",
                "last_updated": best_pair.get('pairCreatedAt'),
                "pair_address": best_pair.get('pairAddress'),
                "contract_address": best_pair.get('baseToken', {}).get('address'),
                "market_cap": price_usd * total_supply
            }

        else:
            logger.error(
                f"DexScreener API error ({response.status_code}): {response.text}"
            )
            return None

    except Exception as e:
        logger.error(
            f"Error getting DexScreener price for {ticker}: {str(e)}"
        )
        return None


def get_crypto_price(ticker, timestamp=None, include_historical=False):
    """
    Get cryptocurrency price data including historical prices

    Args:
        ticker: Cryptocurrency ticker symbol
        timestamp: Optional timestamp to get historical price
        include_historical: Boolean flag to determine if historical prices should be fetched

    Returns: Dictionary containing price data
    """
    try:
        current_price_data = get_current_price(ticker)
        if not current_price_data:
            return None

        result = {
            "current_price": current_price_data.get("price"),
            "volume_24h": current_price_data.get("volume_24h"),
            "liquidity": current_price_data.get("liquidity"),
            "percent_change_24h": current_price_data.get("percent_change_24h"),
            "dex": current_price_data.get("dex"),
            "network": current_price_data.get("network"),
            "pair_name": current_price_data.get("pair_name"),
            "last_updated": current_price_data.get("last_updated"),
            "contract_address": current_price_data.get("contract_address"),
        }

        # Get tweet time price if timestamp is provided
        if timestamp and current_price_data:
            tweet_time_price = get_historical_price(
                ticker,
                timestamp,
                contract_address=current_price_data.get("contract_address"),
                network_id=current_price_data.get("network_id"),
            )
            if tweet_time_price is None:
                logger.error(
                    f"Could not get historical price for {ticker} at {timestamp}"
                )
                return None
            result["tweet_time_price"] = tweet_time_price

        # Only get historical prices if include_historical flag is True
        if include_historical:
            now = datetime.utcnow()
            contract_address = current_price_data.get("contract_address")
            network_id = current_price_data.get("network_id")
            current_price = current_price_data.get("price")

            # Get historical prices at different lookback periods
            price_7d = get_historical_price(
                ticker,
                now - timedelta(days=7),
                contract_address=contract_address,
                network_id=network_id,
            )
            price_14d = get_historical_price(
                ticker,
                now - timedelta(days=14),
                contract_address=contract_address,
                network_id=network_id,
            )
            price_30d = get_historical_price(
                ticker,
                now - timedelta(days=30),
                contract_address=contract_address,
                network_id=network_id,
            )

            def calc_percent_change(historical_price, current_price):
                if historical_price and historical_price != 0:
                    return ((current_price - historical_price) / historical_price) * 100
                return None

            result.update(
                {
                    "percent_change_7d": calc_percent_change(price_7d, current_price),
                    "percent_change_14d": calc_percent_change(price_14d, current_price),
                    "percent_change_30d": calc_percent_change(price_30d, current_price),
                }
            )

        return result

    except Exception as e:
        logger.error(f"Error getting price data for {ticker}: {str(e)}")
        return None


def get_current_price(ticker):
    """Get current price with fallback to CoinMarketCap standard API"""
    # Try CoinMarketCap DEX API first
    cmc_dex_data = get_coinmarketcap_dex_price(ticker)
    if cmc_dex_data:
        return cmc_dex_data

    # Fallback to CoinMarketCap standard API
    logger.info(f"Falling back to CoinMarketCap standard API for {ticker}")
    cmc_standard_data = get_coinmarketcap_standard_price(ticker)
    if cmc_standard_data:
        return cmc_standard_data

    logger.warning(f"No valid price data found for {ticker} from either API")
    return None


def get_coinmarketcap_dex_price(ticker):
    """Get current price from DEX API across all networks"""
    rate_limiter.wait_if_needed()

    url = "https://pro-api.coinmarketcap.com/v4/dex/spot-pairs/latest"

    headers = {
        "Accept": "application/json",
        "X-CMC_PRO_API_KEY": config.COINMARKETCAP_API_KEY,
    }

    parameters = {
        "base_asset_symbol": ticker,
        "limit": "5",
        "network_id": "199",
    }

    session = Session()
    session.headers.update(headers)

    response = session.get(url, params=parameters)
    data = response.json()

    if response.status_code == 200 and data.get("data"):
        pairs = sorted(
            data["data"],
            key=lambda x: float(x["quote"][0]["liquidity"] or 0),
            reverse=True,
        )

        if pairs:
            pair = pairs[0]
            quote = pair["quote"][0]

            return {
                "price": quote.get("price"),
                "volume_24h": quote.get("volume_24h"),
                "liquidity": quote.get("liquidity"),
                "percent_change_24h": quote.get("percent_change_price_24h"),
                "dex": pair.get("dex_slug"),
                "network": pair.get("network_slug"),
                "network_id": pair.get("network_id"),
                "pair_name": pair.get("name"),
                "last_updated": quote.get("last_updated"),
                "contract_address": pair.get("contract_address"),
            }

    logger.warning(f"No valid price data found for {ticker}")
    return None


def get_coinmarketcap_standard_price(ticker):
    """Get current price from CoinMarketCap standard API"""
    try:
        # First get token info
        rate_limiter.wait_if_needed()
        info_url = "https://pro-api.coinmarketcap.com/v2/cryptocurrency/info"

        headers = {
            "Accept": "application/json",
            "X-CMC_PRO_API_KEY": config.COINMARKETCAP_API_KEY,
        }

        info_params = {"symbol": ticker}

        session = Session()
        session.headers.update(headers)

        info_response = session.get(info_url, params=info_params)
        info_data = info_response.json()

        # Log info response
        logger.info(f"Info API Response for {ticker}: {info_response.status_code}")
        logger.info(f"Info API Data: {info_data}")

        # Initialize variables
        token_id = None
        platform_name = None
        contract_address = None

        if info_data.get("data"):
            data_items = info_data["data"].get(ticker, [])
            if isinstance(data_items, list):
                # Filter for tokens on Arbitrum or Solana platforms
                filtered_tokens = []
                for token in data_items:
                    # Check contract_address array for Arbitrum or Solana
                    contract_addresses = token.get("contract_address", [])
                    for addr in contract_addresses:
                        if addr.get("platform", {}).get("name") in [
                            "Arbitrum",
                            "Solana",
                        ]:
                            filtered_tokens.append(token)
                            platform_name = addr["platform"]["name"]
                            contract_address = addr["contract_address"]
                            break

                    # Also check platform field as backup
                    if token.get("platform", {}).get("name") in ["Arbitrum", "Solana"]:
                        filtered_tokens.append(token)
                        platform_name = token["platform"]["name"]
                        contract_address = token["platform"]["token_address"]

                if filtered_tokens:
                    token = filtered_tokens[0]  # Take first matching token
                    token_id = token.get("id")

        if not token_id:
            logger.warning(
                f"Could not find token ID for {ticker} on Arbitrum or Solana"
            )
            return None

        # Get current price data
        rate_limiter.wait_if_needed()
        price_url = "https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/latest"

        price_params = {"symbol": ticker, "convert": "USD"}

        response = session.get(price_url, params=price_params)
        data = response.json()

        # Log price response
        logger.info(f"Price API Response for {ticker}: {response.status_code}")
        logger.info(f"Price API Data: {data}")

        if response.status_code == 200 and data.get("data"):
            ticker_data = None
            if ticker in data["data"]:
                # Handle dictionary with list value
                ticker_list = data["data"][ticker]
                if isinstance(ticker_list, list) and ticker_list:
                    ticker_data = ticker_list[0]
            elif isinstance(data["data"], list):
                # Handle list response
                ticker_data = next(
                    (item for item in data["data"] if item.get("symbol") == ticker),
                    None,
                )
            else:
                # Handle dictionary response
                ticker_data = data["data"].get(ticker)

            if not ticker_data:
                logger.warning(f"No price data found for token {ticker}")
                return None

            # Check if we have quote data
            if "quote" not in ticker_data or "USD" not in ticker_data["quote"]:
                logger.warning(f"No USD quote found for {ticker}")
                return None

            quote = ticker_data["quote"]["USD"]

            return {
                "price": quote.get("price"),
                "volume_24h": quote.get("volume_24h"),
                "liquidity": None,  # Not available in standard API
                "percent_change_24h": quote.get("percent_change_24h"),
                "dex": None,  # Not applicable for standard API
                "network": platform_name.lower() if platform_name else None,
                "network_id": "199" if platform_name == "Solana" else None,
                "pair_name": ticker_data.get("name"),
                "last_updated": quote.get("last_updated"),
                "contract_address": contract_address,
                "cmc_id": token_id,
            }

        elif response.status_code == 400:
            logger.warning(
                f"Invalid request for {ticker}: {data.get('status', {}).get('error_message')}"
            )
            return None
        else:
            logger.error(
                f"CMC API error ({response.status_code}): {data.get('status', {}).get('error_message')}"
            )
            return None

    except Exception as e:
        logger.error(
            f"Error getting CoinMarketCap standard price for {ticker}: {str(e)}"
        )
        return None


def get_historical_price(
    ticker, timestamp, contract_address=None, network_id=None, network_slug=None
):
    """Get historical price with fallback to CoinMarketCap standard API"""
    # Try CoinMarketCap DEX API first
    cmc_dex_historical = get_coinmarketcap_dex_historical_price(
        ticker, timestamp, contract_address, network_id, network_slug
    )
    if cmc_dex_historical is not None:
        return cmc_dex_historical

    # Fallback to CoinMarketCap standard API
    logger.info(
        f"Falling back to CoinMarketCap standard API for historical price of {ticker}"
    )
    return get_coinmarketcap_standard_historical_price(ticker, timestamp)


def get_coinmarketcap_dex_historical_price(
    ticker, timestamp, contract_address=None, network_id=None, network_slug=None
):
    """Get historical price from CoinMarketCap DEX API"""
    try:
        rate_limiter.wait_if_needed()
        # Validate timestamp and ensure it's timezone-aware
        if not isinstance(timestamp, datetime):
            logger.error(f"Invalid timestamp format for {ticker}: {timestamp}")
            return None

        # Convert to UTC if timestamp has no timezone
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        # Compare with UTC now
        if timestamp < datetime.now(timezone.utc) - timedelta(days=30):
            logger.warning(
                f"Historical price request for {ticker} is older than 30 days"
            )

        if not (contract_address and (network_id or network_slug)):
            logger.error("Missing contract_address or network information for DEX API")
            return None

        # Define the URL for historical data
        url = "https://pro-api.coinmarketcap.com/v4/dex/pairs/ohlcv/historical"
        headers = {
            "Accept": "application/json",
            "X-CMC_PRO_API_KEY": config.COINMARKETCAP_API_KEY,
        }

        time_start = timestamp - timedelta(minutes=60)
        time_end = timestamp + timedelta(minutes=60)

        parameters = {
            "contract_address": contract_address,
            "time_start": time_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "time_end": time_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "time_period": "15m",
            "interval": "15m",
        }

        if network_id:
            parameters["network_id"] = network_id
        elif network_slug:
            parameters["network_slug"] = network_slug

        response = requests.get(url, headers=headers, params=parameters)

        if response.status_code == 200:
            data = response.json()
            pairs = data.get("data", [])

            if pairs:
                pair_data = pairs[0]
                quotes = pair_data.get("quotes", [])
                if quotes:
                    target_ts = timestamp.timestamp()

                    for q in quotes:
                        time_open_str = q.get("time_open")
                        if time_open_str:
                            candle_time = datetime.fromisoformat(
                                time_open_str.replace("Z", "+00:00")
                            ).timestamp()
                            q["timestamp_unix"] = candle_time

                    closest_quote = min(
                        quotes,
                        key=lambda x: abs(target_ts - x.get("timestamp_unix", 0)),
                    )
                    candle_quote = (
                        closest_quote["quote"][0] if closest_quote.get("quote") else {}
                    )
                    return candle_quote.get("close")

        return None

    except Exception as e:
        logger.error(f"Error getting CMC DEX historical price: {str(e)}")
        return None


def get_coinmarketcap_standard_historical_price(ticker, timestamp):
    """Get historical price from CoinMarketCap standard API"""
    try:
        # First get token info to get ID
        rate_limiter.wait_if_needed()
        platform_url = "https://pro-api.coinmarketcap.com/v2/cryptocurrency/info"
        headers = {
            "Accept": "application/json",
            "X-CMC_PRO_API_KEY": config.COINMARKETCAP_API_KEY,
        }

        platform_params = {"symbol": ticker}
        platform_response = requests.get(
            platform_url, headers=headers, params=platform_params
        )

        # Log token info API response
        logger.info(
            f"Token Info API Response for {ticker}: Status={platform_response.status_code}"
        )
        logger.debug(f"Token Info API Raw Response: {platform_response.text}")

        if platform_response.status_code != 200:
            logger.error(f"Failed to get token info for {ticker}")
            return None

        platform_data = platform_response.json()

        # Get token ID
        token_id = None
        platform_name = None
        contract_address = None

        if platform_data.get("data"):
            data_items = platform_data["data"].get(ticker, [])
            if isinstance(data_items, list):
                # Filter for tokens on Arbitrum or Solana platforms
                filtered_tokens = []
                for token in data_items:
                    # Check contract_address array for Arbitrum or Solana
                    contract_addresses = token.get("contract_address", [])
                    for addr in contract_addresses:
                        if addr.get("platform", {}).get("name") in [
                            "Arbitrum",
                            "Solana",
                        ]:
                            filtered_tokens.append(token)
                            platform_name = addr["platform"]["name"]
                            contract_address = addr["contract_address"]
                            break

                    # Also check platform field as backup
                    if token.get("platform", {}).get("name") in ["Arbitrum", "Solana"]:
                        filtered_tokens.append(token)
                        platform_name = token["platform"]["name"]
                        contract_address = token["platform"]["token_address"]

                if filtered_tokens:
                    token = filtered_tokens[0]  # Take first matching token
                    token_id = token.get("id")

        if not token_id:
            logger.warning(
                f"Could not find token ID for {ticker} on Arbitrum or Solana"
            )
            return None

        # Convert timestamp to UTC if needed
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        # Create time window around the target timestamp
        time_start = timestamp - timedelta(minutes=30)  # Start 30 minutes before
        time_end = timestamp + timedelta(minutes=30)  # End 30 minutes after

        # Format timestamps for CMC API
        time_start_str = time_start.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        time_end_str = time_end.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        # Get historical quotes using the correct endpoint and parameters
        rate_limiter.wait_if_needed()
        quotes_url = (
            "https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/historical"
        )

        parameters = {
            "id": token_id,
            "time_start": time_start_str,
            "time_end": time_end_str,
            "count": 60,  # Get enough data points for the time window
            "interval": "5m",  # Use 5-minute intervals
            "convert": "USD",
        }

        logger.debug(f"Historical price request parameters: {parameters}")

        response = requests.get(quotes_url, headers=headers, params=parameters)

        # Log response for debugging
        logger.info(
            f"Historical Price API Response for {ticker}: {response.status_code}"
        )
        if response.status_code != 200:
            logger.info(f"Historical Price API Data: {response.text}")

        if response.status_code == 200:
            data = response.json()

            # Log price response
            logger.info(
                f"Historical Price API Response for {ticker}: {response.status_code}"
            )
            logger.info(f"Historical Price API Data: {data}")

            if not data.get("data"):
                logger.warning(f"No historical data found for {ticker}")
                return None

            quotes = data["data"].get("quotes", [])
            if not quotes:
                logger.warning(f"No quotes found for {ticker}")
                return None

            # Get the closest quote to our target timestamp
            target_ts = timestamp.timestamp()
            try:
                closest_quote = min(
                    quotes,
                    key=lambda x: abs(
                        datetime.fromisoformat(
                            x.get("timestamp", "").replace("Z", "+00:00")
                        ).timestamp()
                        - target_ts
                    ),
                )

                if "quote" in closest_quote and "USD" in closest_quote["quote"]:
                    price = closest_quote["quote"]["USD"].get("price")
                    if price is not None:
                        return float(price)
            except (ValueError, KeyError) as e:
                logger.error(f"Error processing quote data: {str(e)}")
                return None

            logger.warning(f"No price found in quote data for {ticker}")
            return None

        elif response.status_code == 429:
            logger.error("CoinMarketCap API rate limit exceeded")
            return None
        else:
            logger.error(f"CoinMarketCap API error: {response.status_code}")
            if response.text:
                logger.error(f"Response: {response.text}")
            return None

    except Exception as e:
        logger.error(
            f"Error getting CMC standard historical price for {ticker}: {str(e)}"
        )
        return None
