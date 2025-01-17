import logging
import requests
from typing import Dict, Optional
from apexbt.config.config import SIGNAL_API_BASE_URL

logger = logging.getLogger(__name__)


class SignalAPI:
    def __init__(self, base_url: str = SIGNAL_API_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def send_signal(
        self,
        token: str,
        contract: str,
        entry_price: float,
        signal_from: str,
        chain: str,
        tx_type: str = "buy",
    ) -> Optional[Dict]:
        """
        Send a trading signal to the signal bot API

        Args:
            token (str): Token symbol
            contract (str): Contract address
            entry_price (float): Entry price
            signal_from (str): Signal source
            chain (str): Blockchain network
            tx_type (str): Transaction type (default: "buy")

        Returns:
            Optional[Dict]: API response data if successful, None if failed
        """
        try:
            payload = {
                "token": token,
                "contract": contract,
                "entry_price": entry_price,
                "signal_from": signal_from,
                "chain": chain.lower(),
                "tx_type": tx_type,
            }

            response = self.session.post(f"{self.base_url}/signal", json=payload)

            if response.status_code == 200:
                logger.info(f"Successfully sent signal for {token}")
                return response.json()
            else:
                logger.error(
                    f"Failed to send signal. Status code: {response.status_code}. Response: {response.text}"
                )
                return None

        except Exception as e:
            logger.error(f"Error sending signal: {str(e)}")
            return None

    def __del__(self):
        """Cleanup session on deletion"""
        self.session.close()
