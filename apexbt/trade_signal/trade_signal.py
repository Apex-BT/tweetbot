import logging
import requests
from typing import Dict, Optional, List
from apexbt.config.config import config

logger = logging.getLogger(__name__)


class SignalAPI:
    _instance = None
    _is_authenticated = False
    _auth_token = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, base_url: str = config.SIGNAL_API_BASE_URL):
        if not hasattr(self, "initialized"):
            self.base_url = base_url.rstrip("/")
            self.session = requests.Session()
            self.initialized = True

    @classmethod
    def initialize(
        cls, username: str, password: str, base_url: str = config.SIGNAL_API_BASE_URL
    ) -> bool:
        """
        Initialize the API with authentication

        Args:
            username (str): Username for authentication
            password (str): Password for authentication
            base_url (str): Base URL for the API

        Returns:
            bool: True if initialization successful, False otherwise
        """
        if cls._is_authenticated:
            return True

        instance = cls(base_url)
        return instance._authenticate(username, password)

    def _authenticate(self, username: str, password: str) -> bool:
        """
        Authenticate with the API and get bearer token
        """
        try:
            # Use form data instead of JSON
            payload = {"username": username, "password": password}
            # Remove the Content-Type header for multipart/form-data
            headers = self.session.headers.copy()
            headers.pop("Content-Type", None)

            response = self.session.post(
                f"{self.base_url}/token",
                data=payload,  # Use data instead of json
                headers=headers,
            )

            if response.status_code == 200:
                response_data = response.json()
                SignalAPI._auth_token = response_data.get("access_token")
                # Update header with proper token format
                self.session.headers.update(
                    {"Authorization": f"Bearer {SignalAPI._auth_token}"}
                )
                SignalAPI._is_authenticated = True
                logger.info("Successfully authenticated")
                return True
            else:
                logger.error(
                    f"Authentication failed. Status code: {response.status_code}"
                )
                logger.error(f"Response content: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return False

    def send_signal(
        self,
        token: str,
        contract: str,
        entry_price: float,
        chain: str,
        tx_type: str,
        signal_from: Optional[str] = None,
        market_cap: Optional[str] = None,
        channel: Optional[str] = "trade_signals",
        user_ids: Optional[List[str]] = None,
        price: Optional[float] = None,
        trigger_type: Optional[str] = None,
        sniffscore: Optional[float] = None,
        holder_count: Optional[int] = None,
    ) -> Optional[Dict]:
        """
        Send a trading signal to the signal bot API

        Args:
            token (str): Token symbol
            contract (str): Contract address
            entry_price (float): Entry price for the trade
            signal_from (Optional[str]): Signal source
            chain (str): Blockchain network
            tx_type (str): Transaction type
            market_cap (Optional[str]): Market capitalization
            channel (Optional[str]): Channel to send signal to (default: "trade_signals")
            user_ids (Optional[List[str]]): List of user IDs
            price (Optional[float]): Current price
            trigger_type (Optional[str]): Type of trigger
            sniffscore (Optional[float]): Sniff score
            holder_count (Optional[int]): Number of holders

        Returns:
            Optional[Dict]: API response data if successful, None if failed
        """
        if not SignalAPI._is_authenticated:
            logger.error("Not authenticated. Call initialize() first")
            return None

        try:
            # Create the base payload
            payload = {
                "token": token,
                "contract": contract,
                "entry_price": entry_price,
                "chain": chain.lower(),
                "tx_type": tx_type,
                "channel": channel,
            }

            # Add optional fields if they exist
            if signal_from is not None:
                payload["signal_from"] = signal_from
            if market_cap is not None:
                payload["market_cap"] = str(market_cap)
            if user_ids is not None:
                payload["user_ids"] = user_ids
            if price is not None:
                payload["price"] = price
            if trigger_type is not None:
                payload["trigger_type"] = trigger_type
            if sniffscore is not None:
                payload["sniffscore"] = sniffscore
            if holder_count is not None:
                payload["holder_count"] = holder_count

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
        if hasattr(self, "session"):
            self.session.close()
