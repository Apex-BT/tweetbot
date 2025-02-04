import asyncio
import websockets
import json
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

class PumpFunManager:
    def __init__(self, callback: Callable):
        self.uri = "wss://pumpportal.fun/api/data"
        self.callback = callback
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False

    async def connect(self):
        """Establish websocket connection and subscribe to new tokens"""
        try:
            self.websocket = await websockets.connect(self.uri)

            # Subscribe to new token events
            payload = {
                "method": "subscribeNewToken",
            }
            await self.websocket.send(json.dumps(payload))
            logger.info("Successfully subscribed to PumpFun new token events")

            return True
        except Exception as e:
            logger.error(f"Failed to connect to PumpFun: {str(e)}")
            return False

    async def process_message(self, message: str):
        """Process incoming websocket messages"""
        try:
            data = json.loads(message)
            symbol = data.get('symbol', '')

            token_info = {
                "id": data.get("signature", ""),  # Use signature as ID
                "text": f"New token detected: {data.get('symbol', '')} - {data.get('name', '')}",
                "author": "pump.fun",
                "created_at": "",  # Add timestamp if available in future
                "token_symbol": symbol,
                "token_address": data.get("mint"),  # Use mint address as token address
                "network": "solana",  # PumpFun is Solana-specific
                "market_cap_sol": data.get("marketCapSol"),
                "initial_buy": data.get("initialBuy"),
                "sol_amount": data.get("solAmount"),
                "token_uri": data.get("uri"),
                "pool": data.get("pool")
            }

            await asyncio.sleep(10)

            await self.callback(token_info)

        except Exception as e:
            logger.error(f"Error processing PumpFun message: {str(e)}")

    async def monitor(self):
        """Main monitoring loop"""
        self.running = True

        while self.running:
            try:
                if not self.websocket:
                    success = await self.connect()
                    if not success:
                        await asyncio.sleep(5)
                        continue

                async for message in self.websocket:
                    await self.process_message(message)

            except websockets.exceptions.ConnectionClosed:
                logger.warning("PumpFun connection closed, attempting to reconnect...")
                self.websocket = None
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Error in PumpFun monitor: {str(e)}")
                await asyncio.sleep(5)

    def stop(self):
        """Stop the monitoring"""
        self.running = False
        if self.websocket:
            asyncio.create_task(self.websocket.close())
