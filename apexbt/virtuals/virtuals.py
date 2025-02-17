import logging
import asyncio
from typing import Callable, Optional, Dict, Any, List
from apexbt.crypto.virtualsSDK import VirtualsSDK

logger = logging.getLogger(__name__)


class VirtualsManager:
    def __init__(self, callback: Callable):
        self.callback = callback
        self.sdk_client = VirtualsSDK()
        self.running = False
        self.check_interval = 60  # Check every x seconds

    async def monitor(self):
        """Monitor for new virtual tokens"""
        logger.info("Starting Virtuals monitoring...")
        self.running = True

        while self.running:
            try:
                await self.process_new_tokens()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in Virtuals monitoring loop: {str(e)}")
                await asyncio.sleep(
                    self.check_interval
                )  # Still sleep on error to prevent tight loop

    def stop(self):
        """Stop the monitoring process"""
        logger.info("Stopping Virtuals monitoring...")
        self.running = False

    def _create_token_info(self, token: Dict[str, Any]) -> Dict[str, Any]:
        """Create token info structure for callback"""
        return {
            "id": token["id"],
            "name": token["name"],
            "symbol": token["symbol"],
            "text": (
                f"New {token['type'].title()} Virtual Token: {token['name']} (${token['symbol']})\n"
                f"Holders: {token['holder_count']}\n"
                f"Market Cap: ${token['market_cap']:,.2f}\n"
                f"Status: {token['status']}"
            ),
            "author": "virtuals",
            "token_address": token["token_address"],
            "network": "base",
            "type": token["type"],
            "market_cap": token["market_cap"],
            "holder_count": token["holder_count"],
            "lp_address": token["lp_address"],
            "description": token["description"],
            "socials": token["socials"],
            "image_url": token["image_url"],
            "created_at": token["created_at"],
            "raw_data": token,
        }

    async def process_new_tokens(self):
        """Process new virtual tokens"""
        try:
            # Get both sentient and prototype listings
            sentient_result = self.sdk_client.get_sentient_listing()

            # Process new tokens from both listings
            for token_list in [
                sentient_result.get("tokens", []),
            ]:
                for token in token_list:
                    token_info = self._create_token_info(token)

                    # Log new token discovery
                    logger.info(
                        f"New {token_info['type']} token found: "
                        f"{token_info['name']} ({token_info['symbol']})"
                    )

                    # Process through callback
                    await self.callback(token_info)

        except Exception as e:
            logger.error(f"Error processing virtual tokens: {str(e)}")
            logger.exception(e)
