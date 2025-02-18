import time
import requests
from typing import List, Dict, Optional
import logging
from enum import Enum
from apexbt.config.config import config


class Network(Enum):
    ETHEREUM = 1
    ARBITRUM = 42161
    BASE = 8453
    SOLANA = 1399811149


logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, requests_per_second: int):
        self.requests_per_second = requests_per_second
        self.requests_timestamps = []

    def wait_if_needed(self):
        current_time = time.time()
        self.requests_timestamps = [
            ts for ts in self.requests_timestamps if current_time - ts < 1
        ]

        if len(self.requests_timestamps) >= self.requests_per_second:
            sleep_time = 1 - (current_time - self.requests_timestamps[0])
            if sleep_time > 0:
                time.sleep(sleep_time)

        self.requests_timestamps.append(current_time)


class Codex:
    base_url = "https://graph.codex.io/graphql"
    rate_limiter = RateLimiter(requests_per_second=5)
    session = requests.Session()
    session.headers.update(
        {"Authorization": config.CODEX_API_KEY, "Content-Type": "application/json"}
    )
    SUPPORTED_NETWORKS = {
        # "ethereum": Network.ETHEREUM.value,
        # "arbitrum": Network.ARBITRUM.value,
        "base": Network.BASE.value,
        "solana": Network.SOLANA.value,
    }

    @staticmethod
    def get_token_info(
        contract_address: str, network: str = "ethereum"
    ) -> Optional[Dict]:
        """Get token information using GraphQL"""
        try:
            network_id = Codex.SUPPORTED_NETWORKS.get(network.lower())
            if not network_id:
                logger.error(f"Unsupported network: {network}")
                return None
            Codex.rate_limiter.wait_if_needed()

            query = """
            query GetTokenInfo($address: String!, $networkId: Int!) {
                token(input: { address: $address, networkId: $networkId }) {
                    id
                    address
                    cmcId
                    decimals
                    name
                    symbol
                    totalSupply
                    info {
                        circulatingSupply
                        imageThumbUrl
                    }
                    explorerData {
                        blueCheckmark
                        description
                        tokenType
                    }
                }
            }
            """

            variables = {"address": contract_address, "networkId": network_id}

            response = Codex.session.post(
                Codex.base_url, json={"query": query, "variables": variables}
            )

            if response.status_code == 200:
                data = response.json()
                if "errors" in data:
                    logger.error(f"GraphQL errors: {data['errors']}")
                    return None
                return data.get("data", {}).get("token")
            else:
                logger.error(
                    f"Codex API error ({response.status_code}): {response.text}"
                )
                return None

        except Exception as e:
            logger.error(f"Error getting token info: {str(e)}")
            return None

    @staticmethod
    def get_token_pairs(
        contract_address: str, network: str = "ethereum", limit: int = 100
    ) -> Optional[List[Dict]]:
        """Get pairs for a token using GraphQL and sort by liquidity"""
        try:
            network_id = Codex.SUPPORTED_NETWORKS.get(network.lower())
            if not network_id:
                logger.error(f"Unsupported network: {network}")
                return None
            Codex.rate_limiter.wait_if_needed()

            query = """
            query GetTokenPairs($tokenAddress: String!, $networkId: Int!) {
                listPairsWithMetadataForToken(tokenAddress: $tokenAddress, networkId: $networkId) {
                    results {
                        pair {
                            address
                        }
                        backingToken {
                            address
                        }
                        volume
                        liquidity
                    }
                }
            }
            """

            variables = {"tokenAddress": contract_address, "networkId": network_id}

            response = Codex.session.post(
                Codex.base_url, json={"query": query, "variables": variables}
            )

            if response.status_code == 200:
                data = response.json()
                if "errors" in data:
                    logger.error(f"GraphQL errors: {data['errors']}")
                    return None

                # Get results from the correct path in the response
                pairs = (
                    data.get("data", {})
                    .get("listPairsWithMetadataForToken", {})
                    .get("results", [])
                )

                # Sort pairs by liquidity in descending order
                sorted_pairs = sorted(
                    pairs,
                    key=lambda x: float(x.get("liquidity", "0") or "0"),
                    reverse=True,
                )

                return sorted_pairs
            else:
                logger.error(
                    f"Codex API error ({response.status_code}): {response.text}"
                )
                return None

        except Exception as e:
            logger.error(f"Error getting token pairs: {str(e)}")
            return None

    @staticmethod
    def get_crypto_price(
        contract_address: str, network: str = "ethereum"
    ) -> Optional[Dict]:
        """
        Get cryptocurrency price data using GraphQL
        """
        try:
            if not contract_address:
                logger.error("Contract address is required for Codex API")
                return None

            network_id = Codex.SUPPORTED_NETWORKS.get(network.lower())
            if not network_id:
                logger.error(f"Unsupported network: {network}")
                return None

            query = """
            query GetTokenPrices($inputs: [GetPriceInput!]!) {
                getTokenPrices(inputs: $inputs) {
                    address
                    networkId
                    priceUsd
                    confidence
                    poolAddress
                }
            }
            """

            variables = {
                "inputs": [{"address": contract_address, "networkId": network_id}]
            }

            Codex.rate_limiter.wait_if_needed()
            response = Codex.session.post(
                Codex.base_url, json={"query": query, "variables": variables}
            )

            if response.status_code == 200:
                data = response.json()
                if "errors" in data:
                    logger.error(f"GraphQL errors: {data['errors']}")
                    return None

                prices = data.get("data", {}).get("getTokenPrices", [])
                if not prices:
                    logger.warning(f"No price data returned for {contract_address}")
                    return None

                price_data = prices[0]

                return {
                    "price": float(price_data.get("priceUsd", 0) or 0),
                    "confidence": price_data.get("confidence"),
                    "pool_address": price_data.get("poolAddress"),
                    "network": network_id,
                    "contract_address": contract_address,
                }
            else:
                logger.error(
                    f"Codex API error ({response.status_code}): {response.text}"
                )
                return None

        except Exception as e:
            logger.error(f"Error getting Codex price for {contract_address}: {str(e)}")
            return None

    @staticmethod
    def get_crypto_prices(token_inputs: List[Dict[str, str]]) -> Optional[List[Dict]]:
        """
        Get cryptocurrency prices for multiple tokens using GraphQL

        Args:
            token_inputs: List of dicts with contract_address and network
            e.g. [{"contract_address": "0x123...", "network": "ethereum"}, ...]
        """
        try:
            if not token_inputs:
                logger.error("No token inputs provided")
                return None

            logger.info(f"Getting prices for {len(token_inputs)} tokens")
            logger.info(f"Token inputs: {token_inputs}")

            # Convert inputs to proper format
            query_inputs = []
            for token in token_inputs:
                network_id = Codex.SUPPORTED_NETWORKS.get(token["network"].lower())
                if network_id:
                    query_inputs.append(
                        {"address": token["contract_address"], "networkId": network_id}
                    )

            if not query_inputs:
                logger.error("No valid token inputs after network validation")
                return None

            # Split inputs into batches of 25
            BATCH_SIZE = 25
            all_results = []

            for i in range(0, len(query_inputs), BATCH_SIZE):
                batch = query_inputs[i : i + BATCH_SIZE]

                query = """
                query GetTokenPrices($inputs: [GetPriceInput!]!) {
                    getTokenPrices(inputs: $inputs) {
                        address
                        networkId
                        priceUsd
                        confidence
                        poolAddress
                    }
                }
                """

                variables = {"inputs": batch}

                Codex.rate_limiter.wait_if_needed()
                response = Codex.session.post(
                    Codex.base_url, json={"query": query, "variables": variables}
                )

                if response.status_code == 200:
                    data = response.json()
                    if "errors" in data:
                        logger.error(f"GraphQL errors: {data['errors']}")
                        continue

                    prices = data.get("data", {}).get("getTokenPrices", [])

                    batch_results = [
                        {
                            "price": float(price.get("priceUsd", 0) or 0),
                            "confidence": price.get("confidence"),
                            "pool_address": price.get("poolAddress"),
                            "network": next(
                                t["network"]
                                for t in token_inputs
                                if t["contract_address"].lower()
                                == price["address"].lower()
                            ),
                            "contract_address": price["address"],
                        }
                        for price in prices
                    ]

                    all_results.extend(batch_results)
                else:
                    logger.error(
                        f"Codex API error ({response.status_code}): {response.text}"
                    )
                    continue

            return all_results if all_results else None

        except Exception as e:
            logger.error(f"Error getting Codex prices: {str(e)}")
            return None

    @staticmethod
    def get_historical_prices(
        contract_address: str, timestamps: List[int], network: str = "ethereum"
    ) -> List[Dict]:
        """Get historical prices using GraphQL"""
        try:
            network_id = Codex.SUPPORTED_NETWORKS.get(network.lower())
            if not network_id:
                logger.error(f"Unsupported network: {network}")
                return None

            query = """
            query GetHistoricalPrices($inputs: [GetPriceInput!]!) {
                getTokenPrices(inputs: $inputs) {
                    priceUsd
                    timestamp
                    confidence
                    poolAddress
                }
            }
            """

            variables = {
                "inputs": [
                    {
                        "address": contract_address,
                        "networkId": network_id,
                        "timestamp": ts,
                    }
                    for ts in timestamps
                ]
            }

            Codex.rate_limiter.wait_if_needed()
            response = Codex.session.post(
                Codex.base_url, json={"query": query, "variables": variables}
            )

            if response.status_code == 200:
                data = response.json()
                if "errors" in data:
                    logger.error(f"GraphQL errors: {data['errors']}")
                    return None

                prices = data.get("data", {}).get("getTokenPrices", [])

                if not prices:
                    logger.warning(f"No price data returned for {contract_address}")
                    return None

                return [
                    {
                        "timestamp": price.get("timestamp"),
                        "price": float(price.get("priceUsd", 0) or 0),
                        "confidence": price.get("confidence"),
                        "pool_address": price.get("poolAddress"),
                        "contract_address": contract_address,
                        "network": network,
                    }
                    for price in prices
                ]
            else:
                logger.error(
                    f"Codex API error ({response.status_code}): {response.text}"
                )
                return None

        except Exception as e:
            logger.error(f"Error getting historical prices: {str(e)}")
            return None

    @staticmethod
    def get_token_holders(
        contract_address: str,
        network: str = "ethereum",
        cursor: str = None,
        sort: str = None,
    ) -> Optional[Dict]:
        """
        Get token holders using GraphQL

        Args:
            contract_address: The token contract address
            network: Network name (ethereum, arbitrum, base, solana)
            cursor: Pagination cursor for subsequent requests
            sort: Sort direction for holders list

        Returns:
            Dictionary containing:
            - holders: List of wallet balances
            - total_count: Total number of unique holders
            - next_cursor: Cursor for pagination
            - status: Holder status
            - top10_holders_percent: Percentage held by top 10 holders
        """
        try:
            network_id = Codex.SUPPORTED_NETWORKS.get(network.lower())
            if not network_id:
                logger.error(f"Unsupported network: {network}")
                return None

            # Construct the token ID in format "address:networkId"
            token_id = f"{contract_address}:{network_id}"

            query = """
            query Holders($input: HoldersInput!) {
                holders(input: $input) {
                    items {
                        walletId
                        tokenId
                        balance
                        shiftedBalance
                    }
                    count
                    cursor
                    status
                    top10HoldersPercent
                }
            }
            """

            # Construct input object according to API spec
            input_vars = {"tokenId": token_id}
            if cursor:
                input_vars["cursor"] = cursor
            if sort:
                input_vars["sort"] = sort

            variables = {"input": input_vars}

            Codex.rate_limiter.wait_if_needed()
            response = Codex.session.post(
                Codex.base_url, json={"query": query, "variables": variables}
            )

            if response.status_code == 200:
                data = response.json()
                if "errors" in data:
                    logger.error(f"GraphQL errors: {data['errors']}")
                    return None

                holders_data = data.get("data", {}).get("holders")
                if not holders_data:
                    logger.warning(f"No holders data returned for {contract_address}")
                    return None

                return {
                    "holders": holders_data.get("items", []),
                    "total_count": holders_data.get("count"),
                    "next_cursor": holders_data.get("cursor"),
                    "status": holders_data.get("status"),
                    "top10_holders_percent": holders_data.get("top10HoldersPercent"),
                    "token_id": token_id,
                }
            else:
                logger.error(
                    f"Codex API error ({response.status_code}): {response.text}"
                )
                return None

        except Exception as e:
            logger.error(
                f"Error getting token holders for {contract_address}: {str(e)}"
            )
            return None
