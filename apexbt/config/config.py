import os
import json
import boto3
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from botocore.exceptions import ClientError

@dataclass
class BaseConfig:
    """Base configuration with default values"""
    SPREADSHEET_NAME: str = "ApeXBT"
    HISTORICAL_SPREADSHEET_NAME: str = "ApexBT Historical Data"
    HISTORICAL_DATABASE_PATH: str = "apexbt_historical.db"
    TWITTER_USERS: List[str] = field(default_factory=lambda: ["aixbt_agent", "Vader_AI_"])
    STOP_LOSS_PERCENTAGE: float = 0.001
    TRADE_UPDATE_INTERVAL_SECONDS: int = 60
    MARKET_CAP_FILTER: int = 10000000000000

class Config(BaseConfig):
    """Configuration class that loads secrets from AWS Secrets Manager"""

    def __init__(self):
        super().__init__()
        self._load_secrets()
        self.validate_config()

    def _get_secret(self, secret_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve a secret from AWS Secrets Manager"""
        region_name = os.getenv('AWS_REGION', 'us-east-1')

        try:
            session = boto3.Session(profile_name='apexbt')
            client = session.client(
                service_name='secretsmanager',
                region_name=region_name
            )

            response = client.get_secret_value(SecretId=secret_name)
            if 'SecretString' in response:
                return json.loads(response['SecretString'])
        except ClientError as e:
            print(f"Error retrieving secret {secret_name}: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error retrieving secret {secret_name}: {e}")
            return None

    def _load_secrets(self) -> None:
        """Load all secrets from AWS Secrets Manager"""

        # Load Database URL
        if db_secret := self._get_secret('DATABASE_CREDENTIALS'):
            self.DATABASE_URL = db_secret.get('DATABASE_URL')
        else:
            print("Warning: Failed to load DATABASE_URL")

        # Load CODEX API Key
        if codex_secret := self._get_secret('CODEX_API_KEY'):
            self.CODEX_API_KEY = codex_secret.get('CODEX_API_KEY')
        else:
            print("Warning: Failed to load CODEX_API_KEY")

        # Load Twitter API Credentials
        if twitter_secret := self._get_secret('TWITTER_API_CREDENTIALS'):
            self.TWITTER_API_KEY = twitter_secret.get('TWITTER_API_KEY')
            self.TWITTER_API_SECRET = twitter_secret.get('TWITTER_API_SECRET')
            self.TWITTER_ACCESS_TOKEN = twitter_secret.get('TWITTER_ACCESS_TOKEN')
            self.TWITTER_ACCESS_TOKEN_SECRET = twitter_secret.get('TWITTER_ACCESS_TOKEN_SECRET')
            self.TWITTER_BEARER_TOKEN = twitter_secret.get('TWITTER_BEARER_TOKEN')
        else:
            print("Warning: Failed to load TWITTER_API_CREDENTIALS")

        # Load Google API Key
        if google_secret := self._get_secret('GOOGLE_API_KEY'):
            self.GOOGLE_API_KEY = google_secret.get('GOOGLE_API_KEY')
        else:
            print("Warning: Failed to load GOOGLE_API_KEY")

        # Load Google Sheets credentials
        if sheets_credentials := self._get_secret('GOOGLE_SHEETS_CREDENTIALS'):
            self.SHEETS_CREDENTIALS = sheets_credentials
        else:
            print("Warning: Failed to load GOOGLE_SHEETS_CREDENTIALS")

        # Load Signal API Credentials
        if signal_secret := self._get_secret('SIGNAL_API_CREDENTIALS'):
            self.SIGNAL_API_BASE_URL = signal_secret.get('SIGNAL_API_BASE_URL')
            self.SIGNAL_API_USERNAME = signal_secret.get('SIGNAL_API_USERNAME')
            self.SIGNAL_API_PASSWORD = signal_secret.get('SIGNAL_API_PASSWORD')
        else:
            print("Warning: Failed to load SIGNAL_API_CREDENTIALS")

        # Load SOL Sniffer API Key
        if sol_sniffer_secret := self._get_secret('SOL_SNIFFER_API_KEY'):
            self.SOL_SNIFFER_API_KEY = sol_sniffer_secret.get('SOL_SNIFFER_API_KEY')
        else:
            print("Warning: Failed to load SOL_SNIFFER_API_KEY")

    def validate_config(self) -> None:
        """Validate that all required configurations are present"""
        required_attrs = [
            'CODEX_API_KEY',
            'TWITTER_API_KEY',
            'TWITTER_API_SECRET',
            'TWITTER_ACCESS_TOKEN',
            'TWITTER_ACCESS_TOKEN_SECRET',
            'TWITTER_BEARER_TOKEN',
            'GOOGLE_API_KEY',
            'SIGNAL_API_BASE_URL',
            'SIGNAL_API_USERNAME',
            'SIGNAL_API_PASSWORD',
            'SHEETS_CREDENTIALS',
            'DATABASE_URL',
            'SOL_SNIFFER_API_KEY'
        ]

        missing_attrs = [
            attr for attr in required_attrs
            if not hasattr(self, attr) or getattr(self, attr) is None
        ]

        if missing_attrs:
            raise ValueError(f"Missing required configurations: {', '.join(missing_attrs)}")

# Create singleton instance
config = Config()
