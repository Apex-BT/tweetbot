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
            response = requests.get(
                f"{self.BASE_URL}/token/{address}",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching token data from SolSniffer: {e}")
            return None
