import apexbt.config.config as config
import logging
from requests import Session
import requests
from datetime import timedelta, datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_crypto_price(ticker, timestamp=None):
    """
    Get cryptocurrency price data including historical prices
    timestamp: Optional timestamp to get historical price
    Returns current price, price at tweet time, and historical data
    """
    try:
        current_price_data = get_current_price(ticker)
        if not current_price_data:
            return None

        tweet_time_price = None
        if timestamp and current_price_data:
            tweet_time_price = get_historical_price(
                ticker,
                timestamp,
                contract_address=current_price_data.get("contract_address"),
                network_id=current_price_data.get("network_id")
            )

        current_price = current_price_data.get("price")
        contract_address = current_price_data.get("contract_address")
        network_id = current_price_data.get("network_id")

        # Optional historical lookups
        now = datetime.utcnow()

        # Get historical prices at different lookback periods
        price_7d = get_historical_price(ticker, now - timedelta(days=7), contract_address=contract_address, network_id=network_id)
        price_14d = get_historical_price(ticker, now - timedelta(days=14), contract_address=contract_address, network_id=network_id)
        price_30d = get_historical_price(ticker, now - timedelta(days=30), contract_address=contract_address, network_id=network_id)

        def calc_percent_change(historical_price, current_price):
            if historical_price and historical_price != 0:
                return ((current_price - historical_price) / historical_price) * 100
            return None

        percent_change_7d = calc_percent_change(price_7d, current_price)
        percent_change_14d = calc_percent_change(price_14d, current_price)
        percent_change_30d = calc_percent_change(price_30d, current_price)

        return {
            "current_price": current_price_data.get("price"),
            "tweet_time_price": tweet_time_price,
            "volume_24h": current_price_data.get("volume_24h"),
            "liquidity": current_price_data.get("liquidity"),
            "percent_change_24h": current_price_data.get("percent_change_24h"),
            "percent_change_7d": percent_change_7d,
            "percent_change_14d": percent_change_14d,
            "percent_change_30d": percent_change_30d,
            "dex": current_price_data.get("dex"),
            "network": current_price_data.get("network"),
            "pair_name": current_price_data.get("pair_name"),
            "last_updated": current_price_data.get("last_updated"),
            "contract_address": current_price_data.get("contract_address"),
        }
    except Exception as e:
        logger.error(f"Error getting price data for {ticker}: {str(e)}")
        return None


def get_current_price(ticker):
    """Get current price from DEX API across all networks"""
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
    logger.info(f"Response data: {data}")

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


def get_historical_price(ticker, timestamp, contract_address=None, network_id=None, network_slug=None):
    try:
        url = "https://pro-api.coinmarketcap.com/v4/dex/pairs/ohlcv/historical"
        headers = {
            "Accept": "application/json",
            "X-CMC_PRO_API_KEY": config.COINMARKETCAP_API_KEY,
        }

        if not (contract_address and (network_id or network_slug)):
            raise ValueError("You must provide a contract_address and either network_id or network_slug.")

        time_start = timestamp - timedelta(minutes=60)
        time_end = timestamp + timedelta(minutes=60)

        parameters = {
            "contract_address": contract_address,
            "time_start": time_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "time_end": time_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "time_period": "15m",
            "interval": "15m",
        }

        # Include network_id or network_slug
        if network_id:
            parameters["network_id"] = network_id
        elif network_slug:
            parameters["network_slug"] = network_slug

        response = requests.get(url, headers=headers, params=parameters)
        logger.info(f"Request parameters: {parameters}")
        logger.info(f"Response status code: {response.status_code}")
        logger.info(f"Response text: {response.text}")

        if response.status_code == 200:
            data = response.json()
            pairs = data.get("data", [])

            if pairs:  # Ensure we have at least one pair
                pair_data = pairs[0]  # Take the first pair
                quotes = pair_data.get("quotes", [])
                if quotes:
                    # quotes is a list of candle data
                    # Each candle is a dict with "quote" key and time keys
                    # To find the closest quote to a certain timestamp:
                    target_ts = timestamp.timestamp()

                    # Convert time_open/time_close to timestamps if needed
                    for q in quotes:
                        # If there's a time field we need to convert, do so here
                        time_open_str = q.get("time_open")
                        if time_open_str:
                            # Convert ISO8601 to timestamp
                            from datetime import datetime
                            candle_time = datetime.fromisoformat(time_open_str.replace("Z", "+00:00")).timestamp()
                            q["timestamp_unix"] = candle_time

                    # Find the closest candle by timestamp
                    closest_quote = min(quotes, key=lambda x: abs(target_ts - x.get("timestamp_unix", 0)))

                    # Each candle's "quote" field is a list of quote dictionaries; pick the first one
                    candle_quote = closest_quote["quote"][0] if closest_quote.get("quote") else {}

                    # Now you can get "close" price if it exists
                    close_price = candle_quote.get("close")
                    return close_price

            logger.error("No quotes found.")
            return None


        logger.error(f"No valid historical price found for token {ticker}")
        return None

    except ValueError as ve:
        logger.error(f"Parameter validation error: {str(ve)}")
        return None
    except Exception as e:
        logger.error(f"Error getting historical price: {str(e)}")
        return None
