"""
PriceTracker — background job that periodically updates prices for all active signals.

Runs every N minutes, fetches current prices from DexScreener for all active signals,
calculates PNL, saves snapshots, and updates the signals table.
"""

import logging
import asyncio
import time
from datetime import datetime, timezone
from typing import Optional

from apexbt.crypto.dexscreener import DexScreener
from apexbt.leaderboard.signals import SignalRecorder

logger = logging.getLogger(__name__)


class PriceTracker:
    """
    Background price tracker that updates all active signals with current prices.

    Usage:
        tracker = PriceTracker(interval_minutes=15)
        await tracker.start()  # runs forever in a loop
    """

    def __init__(self, interval_minutes: int = 15, snapshot_interval_minutes: int = 60):
        self.interval_seconds = interval_minutes * 60
        self.snapshot_interval_seconds = snapshot_interval_minutes * 60
        self.recorder = SignalRecorder()
        self.dex = DexScreener()
        self.running = False
        self._last_snapshot_time = 0

    async def start(self):
        """Start the tracking loop. Runs until stopped."""
        self.running = True
        logger.info(
            f"PriceTracker started (update every {self.interval_seconds // 60}m, "
            f"snapshot every {self.snapshot_interval_seconds // 60}m)"
        )

        while self.running:
            try:
                await self.update_all_prices()
            except Exception as e:
                logger.error(f"PriceTracker update cycle error: {e}")

            await asyncio.sleep(self.interval_seconds)

    def stop(self):
        """Signal the tracker to stop after the current cycle."""
        self.running = False
        logger.info("PriceTracker stopping...")

    async def update_all_prices(self):
        """Fetch current prices for all active signals and update the DB."""
        signals = self.recorder.get_active_signals()

        if not signals:
            logger.debug("No active signals to update")
            return

        logger.info(f"Updating prices for {len(signals)} active signals...")

        # Group signals by contract_address + chain to avoid duplicate API calls
        price_cache: dict[str, Optional[float]] = {}
        should_snapshot = self._should_take_snapshot()

        updated = 0
        failed = 0

        for signal in signals:
            try:
                contract = signal.get("contract_address")
                chain = signal.get("chain")
                entry_price = float(signal["entry_price"])
                signal_id = signal["id"]
                ticker = signal["ticker"]
                entry_time = signal["entry_time"]

                if not contract or not chain:
                    logger.debug(f"Signal {signal_id} ({ticker}) missing contract/chain, skipping")
                    failed += 1
                    continue

                # Use cache to avoid hitting DexScreener for the same token
                cache_key = f"{chain}:{contract}"

                if cache_key not in price_cache:
                    current_price = await self._fetch_price(contract, chain, ticker)
                    price_cache[cache_key] = current_price
                    # Small delay to be nice to the DexScreener API
                    await asyncio.sleep(0.3)
                else:
                    current_price = price_cache[cache_key]

                if current_price is None or current_price <= 0:
                    logger.debug(f"Could not fetch price for {ticker} ({contract})")
                    failed += 1
                    continue

                # Calculate PNL percentage
                if entry_price > 0:
                    pnl_percent = ((current_price - entry_price) / entry_price) * 100
                else:
                    pnl_percent = 0.0

                # Update signal in DB
                self.recorder.update_signal_price(signal_id, current_price, pnl_percent)
                updated += 1

                # Save snapshot if it's time
                if should_snapshot and entry_time:
                    hours_since = self._hours_since(entry_time)
                    self.recorder.save_snapshot(
                        signal_id=signal_id,
                        current_price=current_price,
                        pnl_percent=pnl_percent,
                        hours_since_signal=hours_since,
                    )

                # Auto-close signals for dead tokens (price dropped >99%)
                if pnl_percent < -99:
                    logger.info(f"Auto-closing signal {signal_id} ({ticker}) — price dropped {pnl_percent:.1f}%")
                    self.recorder.mark_signal_closed(signal_id, reason="rugged")

            except Exception as e:
                logger.error(f"Error updating signal {signal.get('id')} ({signal.get('ticker')}): {e}")
                failed += 1

        if should_snapshot:
            self._last_snapshot_time = time.time()

        logger.info(
            f"Price update complete: {updated} updated, {failed} failed, "
            f"{len(price_cache)} unique tokens fetched"
        )

    async def _fetch_price(self, contract_address: str, chain: str, ticker: str) -> Optional[float]:
        """
        Fetch the current price for a token from DexScreener.
        Runs the synchronous DexScreener call in a thread to avoid blocking.
        """
        try:
            dex_data = await asyncio.to_thread(
                self.dex.get_token_by_address, contract_address, chain
            )

            if dex_data and dex_data.get("current_price"):
                return float(dex_data["current_price"])

            # Fallback: try by ticker
            dex_data = await asyncio.to_thread(
                self.dex.get_token_by_ticker, ticker
            )

            if dex_data and dex_data.get("current_price"):
                return float(dex_data["current_price"])

            return None

        except Exception as e:
            logger.error(f"DexScreener fetch error for {ticker} ({contract_address}): {e}")
            return None

    def _should_take_snapshot(self) -> bool:
        """Check if enough time has passed since the last snapshot."""
        return (time.time() - self._last_snapshot_time) >= self.snapshot_interval_seconds

    @staticmethod
    def _hours_since(entry_time: datetime) -> float:
        """Calculate hours elapsed since a signal was created."""
        now = datetime.now(timezone.utc)

        # Handle naive datetimes (assume UTC)
        if entry_time.tzinfo is None:
            entry_time = entry_time.replace(tzinfo=timezone.utc)

        delta = now - entry_time
        return round(delta.total_seconds() / 3600, 2)

    async def get_price_for_token(self, contract_address: str, chain: str, ticker: str) -> Optional[float]:
        """
        Public helper: fetch a single token price.
        Useful for ad-hoc lookups outside the update loop.
        """
        return await self._fetch_price(contract_address, chain, ticker)
