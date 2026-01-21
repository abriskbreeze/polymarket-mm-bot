"""
Simple market maker.

Places two-sided quotes around the midpoint.
Updates quotes when price moves.
Respects position limits.
"""

import asyncio
import signal
from decimal import Decimal
from typing import Optional
from dataclasses import dataclass

from src.config import (
    DRY_RUN,
    MM_SPREAD,
    MM_SIZE,
    MM_REQUOTE_THRESHOLD,
    MM_POSITION_LIMIT,
    MM_LOOP_INTERVAL,
)
from src.models import Order, OrderSide
from src.trading import place_order, cancel_order, cancel_all_orders, OrderError
from src.orders import get_open_orders, get_position
from src.feed import MarketFeed
from src.risk import RiskManager, RiskStatus, get_risk_manager
from src.utils import setup_logging

logger = setup_logging()


@dataclass
class Quote:
    """Represents a single quote (bid or ask)."""
    order: Optional[Order] = None
    target_price: Optional[Decimal] = None


class SimpleMarketMaker:
    """
    Simple market maker for a single token.

    Usage:
        mm = SimpleMarketMaker(token_id="abc123")
        await mm.run()  # Runs until stopped

    Stop with Ctrl+C or call mm.stop()
    """

    def __init__(
        self,
        token_id: str,
        spread: Decimal = MM_SPREAD,
        size: Decimal = MM_SIZE,
        requote_threshold: Decimal = MM_REQUOTE_THRESHOLD,
        position_limit: Decimal = MM_POSITION_LIMIT,
        loop_interval: float = MM_LOOP_INTERVAL,
    ):
        self.token_id = token_id
        self.spread = spread
        self.size = size
        self.requote_threshold = requote_threshold
        self.position_limit = position_limit
        self.loop_interval = loop_interval

        self.feed: Optional[MarketFeed] = None
        self.bid = Quote()
        self.ask = Quote()
        self.last_mid: Optional[Decimal] = None
        self._running = False
        self._shutdown_event = asyncio.Event()
        self.risk = get_risk_manager()

    async def run(self):
        """
        Main loop. Runs until stopped.

        Call stop() or send SIGINT (Ctrl+C) to stop.
        """
        logger.info(f"Starting market maker for {self.token_id[:16]}...")
        logger.info(f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}")
        logger.info(f"Spread: {self.spread}, Size: {self.size}")

        # Set up signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._handle_signal)

        try:
            # Start feed
            self.feed = MarketFeed()
            await self.feed.start([self.token_id])

            # Wait for initial data
            await self._wait_for_data()

            self._running = True
            logger.info("Market maker running. Press Ctrl+C to stop.")

            # Main loop
            while self._running and not self._shutdown_event.is_set():
                try:
                    await self._loop_iteration()
                except Exception as e:
                    logger.error(f"Loop error: {e}")

                # Wait for next iteration or shutdown
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=self.loop_interval
                    )
                except asyncio.TimeoutError:
                    pass  # Normal - continue loop

        finally:
            await self._shutdown()

    def stop(self):
        """Signal the market maker to stop."""
        logger.info("Stop requested...")
        self._running = False
        self._shutdown_event.set()

    def _handle_signal(self):
        """Handle shutdown signals."""
        self.stop()

    async def _wait_for_data(self, timeout: float = 10.0):
        """Wait for feed to have data."""
        logger.info("Waiting for market data...")
        start = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start < timeout:
            if self.feed and self.feed.is_healthy:
                mid = self.feed.get_midpoint(self.token_id)
                if mid is not None:
                    logger.info(f"Got initial mid: {mid}")
                    return
            await asyncio.sleep(0.5)

        raise RuntimeError("Timeout waiting for market data")

    async def _loop_iteration(self):
        """Single iteration of the market making loop."""
        # === RISK CHECK ===
        check = self.risk.check([self.token_id])

        if check.status == RiskStatus.STOP:
            # In enforce mode: stop trading
            # In data-gather mode: this won't happen (check returns OK)
            logger.error(f"Risk stop: {check.reason}")
            await self._cancel_all_quotes()
            self.stop()
            return

        if check.status == RiskStatus.WARN:
            logger.warning(f"Risk warning: {check.reason}")
            # Could reduce size here in future

        # Check feed health
        if not self.feed or not self.feed.is_healthy:
            logger.warning("Feed unhealthy - cancelling quotes")
            await self._cancel_all_quotes()
            return

        # Get current mid
        mid = self.feed.get_midpoint(self.token_id)
        if mid is None:
            logger.warning("No midpoint available")
            return

        mid = Decimal(str(mid))

        # Check if we need to requote
        if self._should_requote(mid):
            await self._update_quotes(mid)
            self.last_mid = mid

    def _should_requote(self, mid: Decimal) -> bool:
        """Check if quotes need updating."""
        # Always quote if we have no quotes
        if self.bid.order is None and self.ask.order is None:
            return True

        # Requote if mid moved beyond threshold
        if self.last_mid is not None:
            move = abs(mid - self.last_mid)
            if move >= self.requote_threshold:
                logger.info(f"Mid moved {move:.4f} - requoting")
                return True

        return False

    async def _update_quotes(self, mid: Decimal):
        """Cancel old quotes and place new ones."""
        # Calculate target prices
        half_spread = self.spread / 2
        bid_price = mid - half_spread
        ask_price = mid + half_spread

        # Round to tick (0.01)
        bid_price = (bid_price * 100).quantize(Decimal("1")) / 100
        ask_price = (ask_price * 100).quantize(Decimal("1")) / 100

        # Ensure valid range
        bid_price = max(Decimal("0.01"), min(Decimal("0.98"), bid_price))
        ask_price = max(Decimal("0.02"), min(Decimal("0.99"), ask_price))

        logger.info(f"Mid: {mid:.2f} -> Bid: {bid_price:.2f}, Ask: {ask_price:.2f}")

        # Cancel existing quotes
        await self._cancel_all_quotes()

        # Check position for skewing
        position = get_position(self.token_id)

        # Place new quotes
        # Skip buy if too long
        if position < self.position_limit:
            self.bid.order = self._place_quote(OrderSide.BUY, bid_price)
            self.bid.target_price = bid_price
        else:
            logger.info(f"Position {position} at limit - skipping BUY")

        # Skip sell if too short
        if position > -self.position_limit:
            self.ask.order = self._place_quote(OrderSide.SELL, ask_price)
            self.ask.target_price = ask_price
        else:
            logger.info(f"Position {position} at limit - skipping SELL")

    def _place_quote(self, side: OrderSide, price: Decimal) -> Optional[Order]:
        """Place a single quote."""
        try:
            order = place_order(
                token_id=self.token_id,
                side=side,
                price=price,
                size=self.size
            )
            logger.info(f"Placed {side.value} @ {price}: {order.id}")
            return order
        except OrderError as e:
            logger.error(f"Failed to place {side.value}: {e}")
            return None

    async def _cancel_all_quotes(self):
        """Cancel all our quotes."""
        if self.bid.order and self.bid.order.is_live:
            cancel_order(self.bid.order.id)
        if self.ask.order and self.ask.order.is_live:
            cancel_order(self.ask.order.id)

        self.bid.order = None
        self.ask.order = None

    async def _shutdown(self):
        """Clean shutdown."""
        logger.info("Shutting down market maker...")

        # Log risk event summary
        summary = self.risk.get_risk_event_summary()
        if summary["total_events"] > 0:
            logger.info(f"Risk Event Summary:")
            logger.info(f"  Total events: {summary['total_events']}")
            logger.info(f"  STOP events: {summary['stop_events']} (enforced: {summary['enforced_events']})")
            logger.info(f"  WARN events: {summary['warn_events']}")
            logger.info(f"  Final P&L: {self.risk.daily_pnl}")

        # Cancel all orders
        logger.info("Cancelling all orders...")
        cancel_all_orders(self.token_id)

        # Stop feed
        if self.feed:
            logger.info("Stopping feed...")
            await self.feed.stop()

        logger.info("Market maker stopped.")


async def run_market_maker(token_id: str, **kwargs):
    """
    Convenience function to run a market maker.

    Usage:
        asyncio.run(run_market_maker("token123"))
    """
    mm = SimpleMarketMaker(token_id, **kwargs)
    await mm.run()
