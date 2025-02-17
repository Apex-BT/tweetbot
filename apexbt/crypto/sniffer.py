import logging
import requests
from typing import Optional
from config.config import config

logger = logging.getLogger(__name__)

class SolSnifferAPI:
    BASE_URL = "https://solsniffer.com/api/v2"

    def __init__(self):
        self.headers = {
            'accept': 'application/json',
            'X-API-KEY': config.SOL_SNIFFER_API_KEY,
            'Content-Type': 'application/json'
        }

    def get_token_data(self, address: str) -> Optional[dict]:
        """
        Get token data from SolSniffer API for a single token address
        Returns None if request fails

        Args:
            address (str): The token address to query

        Returns:
            Optional[dict]: Token data or None if request fails
        """
        try:
            # Validate input
            logger.info(f"Validating address: {address}")
            if not isinstance(address, str):
                logger.error(f"Invalid address type: {type(address)}")
                return None

            url = f"{self.BASE_URL}/token/{address}"
            logger.info(f"Making request to: {url}")

            response = requests.get(
                url,
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error fetching token data from SolSniffer: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching token data from SolSniffer: {e}")
            return None
