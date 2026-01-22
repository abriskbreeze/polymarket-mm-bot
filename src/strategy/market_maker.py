"""
Market makers for Polymarket.

SimpleMarketMaker: Fixed spread, basic position limits
SmartMarketMaker: Dynamic spread, inventory skewing, volatility-aware
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
    SPREAD_BASE,
    SPREAD_MIN,
    SPREAD_MAX,
    INVENTORY_SKEW_MAX,
)
from src.models import Order, OrderSide
from src.trading import place_order, cancel_order, cancel_all_orders, OrderError
from src.orders import get_open_orders, get_position
from src.feed import MarketFeed
from src.risk import RiskManager, RiskStatus, get_risk_manager
from src.simulator import get_simulator
from src.utils import setup_logging
from src.strategy.volatility import VolatilityTracker
from src.strategy.book_analyzer import BookAnalyzer
from src.strategy.inventory import InventoryManager

logger = setup_logging()


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
        self.bid_order: Optional[Order] = None
        self.ask_order: Optional[Order] = None
        self.last_mid: Optional[Decimal] = None
        self._running = False
        self._shutdown_event = asyncio.Event()
        self.risk = get_risk_manager()

    async def run(self, install_signals: bool = True):
        """
        Main loop. Runs until stopped.

        Args:
            install_signals: If True, install signal handlers. Set False when
                           called from TUIBotRunner which handles signals itself.
        """
        logger.info(f"Starting market maker for {self.token_id[:16]}...")
        logger.info(f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}")
        logger.info(f"Spread: {self.spread}, Size: {self.size}")

        # Set up signal handlers (skip if caller handles signals)
        loop = asyncio.get_event_loop()
        if install_signals:
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

    def get_state_for_tui(self) -> dict:
        """Get current state for TUI rendering."""
        return {
            'bid_order': self.bid_order,
            'ask_order': self.ask_order,
            'last_mid': self.last_mid,
            'running': self._running,
        }

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

        # Check for simulated fills in DRY_RUN mode
        if DRY_RUN:
            bid = self.feed.get_best_bid(self.token_id)
            ask = self.feed.get_best_ask(self.token_id)
            if bid is not None and ask is not None:
                # Log what we're checking (helps debug why fills don't occur)
                sim = get_simulator()
                open_orders = sim.get_open_orders(self.token_id)
                if open_orders:
                    for o in open_orders:
                        would_fill = (o.side.value == "BUY" and o.price >= Decimal(str(ask))) or \
                                     (o.side.value == "SELL" and o.price <= Decimal(str(bid)))
                        if would_fill:
                            logger.info(f"[SIM] {o.side.value} @ {o.price} CROSSES market (bid={bid}, ask={ask})")
                        else:
                            # Log occasionally to show check is happening (every ~30s based on loop timing)
                            logger.debug(f"[SIM] {o.side.value} @ {o.price} vs market bid={bid} ask={ask} -> no cross")

                filled = sim.check_fills(
                    self.token_id, Decimal(str(bid)), Decimal(str(ask))
                )
                if filled:
                    logger.info(f"[SIM] {filled} order(s) filled")

        # Check if we need to requote
        if self._should_requote(mid):
            await self._update_quotes(mid)
            self.last_mid = mid

    def _should_requote(self, mid: Decimal) -> bool:
        """Check if quotes need updating."""
        # Always quote if we have no quotes
        if self.bid_order is None and self.ask_order is None:
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
            self.bid_order = self._place_quote(OrderSide.BUY, bid_price)
        else:
            logger.info(f"Position {position} at limit - skipping BUY")

        # Skip sell if too short
        if position > -self.position_limit:
            self.ask_order = self._place_quote(OrderSide.SELL, ask_price)
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
        if self.bid_order and self.bid_order.is_live:
            cancel_order(self.bid_order.id)
        if self.ask_order and self.ask_order.is_live:
            cancel_order(self.ask_order.id)

        self.bid_order = None
        self.ask_order = None

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


@dataclass
class SmartMMState:
    """State snapshot for SmartMarketMaker (for TUI display)."""
    # Spread
    base_spread: Decimal
    vol_multiplier: float
    inv_multiplier: float
    final_spread: Decimal

    # Volatility
    volatility_level: str
    realized_vol: float

    # Inventory
    inventory_pct: float
    inventory_level: str
    bid_skew: Decimal
    ask_skew: Decimal

    # Book
    imbalance_signal: str
    imbalance_adjustment: Decimal

    # P&L
    unrealized_pnl: Decimal
    vwap_entry: Optional[Decimal]


class SmartMarketMaker:
    """
    Adaptive market maker with dynamic spread and inventory management.

    Features over SimpleMarketMaker:
    - Dynamic spread based on volatility
    - Gradual inventory skewing (not hard stops)
    - Order book imbalance awareness
    - Competitive quote positioning
    - Unrealized P&L tracking

    Usage:
        mm = SmartMarketMaker(token_id="abc123")
        await mm.run()
    """

    def __init__(
        self,
        token_id: str,
        base_spread: Decimal = SPREAD_BASE,
        min_spread: Decimal = SPREAD_MIN,
        max_spread: Decimal = SPREAD_MAX,
        size: Decimal = MM_SIZE,
        requote_threshold: Decimal = MM_REQUOTE_THRESHOLD,
        position_limit: Decimal = MM_POSITION_LIMIT,
        loop_interval: float = MM_LOOP_INTERVAL,
        skew_max: Decimal = INVENTORY_SKEW_MAX,
    ):
        self.token_id = token_id
        self.base_spread = base_spread
        self.min_spread = min_spread
        self.max_spread = max_spread
        self.size = size
        self.requote_threshold = requote_threshold
        self.position_limit = position_limit
        self.loop_interval = loop_interval

        # Components
        self.volatility = VolatilityTracker(token_id)
        self.book_analyzer = BookAnalyzer()
        self.inventory = InventoryManager(
            token_id,
            position_limit=position_limit,
            skew_max=skew_max,
        )

        # State
        self.feed: Optional[MarketFeed] = None
        self.bid_order: Optional[Order] = None
        self.ask_order: Optional[Order] = None
        self.last_mid: Optional[Decimal] = None
        self._running = False
        self._shutdown_event = asyncio.Event()
        self.risk = get_risk_manager()

        # Computed values (for TUI display)
        self._last_state: Optional[SmartMMState] = None

    async def run(self, install_signals: bool = True):
        """Main loop. Runs until stopped."""
        logger.info(f"Starting SMART market maker for {self.token_id[:16]}...")
        logger.info(f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}")
        logger.info(f"Base spread: {self.base_spread}, Size: {self.size}")

        loop = asyncio.get_event_loop()
        if install_signals:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, self._handle_signal)

        try:
            self.feed = MarketFeed()
            await self.feed.start([self.token_id])
            await self._wait_for_data()

            self._running = True
            logger.info("Smart market maker running. Press Ctrl+C to stop.")

            while self._running and not self._shutdown_event.is_set():
                try:
                    await self._loop_iteration()
                except Exception as e:
                    logger.error(f"Loop error: {e}")

                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=self.loop_interval
                    )
                except asyncio.TimeoutError:
                    pass

        finally:
            await self._shutdown()

    def stop(self):
        """Signal the market maker to stop."""
        logger.info("Stop requested...")
        self._running = False
        self._shutdown_event.set()

    def get_state_for_tui(self) -> dict:
        """Get current state for TUI rendering."""
        return {
            'bid_order': self.bid_order,
            'ask_order': self.ask_order,
            'last_mid': self.last_mid,
            'running': self._running,
            'smart_state': self._last_state,
        }

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
        """Single iteration of the smart market making loop."""
        # Risk check
        check = self.risk.check([self.token_id])
        if check.status == RiskStatus.STOP:
            logger.error(f"Risk stop: {check.reason}")
            await self._cancel_all_quotes()
            self.stop()
            return

        if check.status == RiskStatus.WARN:
            logger.warning(f"Risk warning: {check.reason}")

        # Feed health
        if not self.feed or not self.feed.is_healthy:
            logger.warning("Feed unhealthy - cancelling quotes")
            await self._cancel_all_quotes()
            return

        # Get market data
        mid = self.feed.get_midpoint(self.token_id)
        if mid is None:
            logger.warning("No midpoint available")
            return
        mid = Decimal(str(mid))

        # Update volatility tracker
        self.volatility.update(float(mid))

        # Get order book for analysis
        order_book = None
        if hasattr(self.feed, '_data_store'):
            order_book = self.feed._data_store.get_order_book(self.token_id)

        # Check for simulated fills in DRY_RUN mode
        if DRY_RUN:
            bid = self.feed.get_best_bid(self.token_id)
            ask = self.feed.get_best_ask(self.token_id)
            if bid is not None and ask is not None:
                sim = get_simulator()
                trades_before = len(sim.get_trades(self.token_id))
                filled = sim.check_fills(
                    self.token_id, Decimal(str(bid)), Decimal(str(ask))
                )
                if filled:
                    logger.info(f"[SIM] {filled} order(s) filled")
                    # Record new fills in inventory manager for VWAP tracking
                    all_trades = sim.get_trades(self.token_id)
                    new_trades = all_trades[trades_before:]
                    for trade in new_trades:
                        self.inventory.record_fill(
                            price=trade.price,
                            size=trade.size,
                            side=trade.side.value
                        )

        # Calculate dynamic spread and quotes
        bid_price, ask_price, state = self._calculate_quotes(mid, order_book)

        # Store state for TUI
        self._last_state = state

        # Check if requote needed
        if self._should_requote(mid):
            await self._update_quotes(mid, bid_price, ask_price)
            self.last_mid = mid

    def _calculate_quotes(
        self,
        mid: Decimal,
        order_book,
    ) -> tuple[Decimal, Decimal, SmartMMState]:
        """Calculate optimal bid/ask prices using all signals."""
        # 1. Volatility multiplier
        vol_mult = self.volatility.get_multiplier()
        vol_state = self.volatility.get_state()

        # 2. Inventory state and skews
        inv_state = self.inventory.get_state(mid)

        # Inventory multiplier: widen spread when inventory is high
        inv_mult = 1.0 + abs(inv_state.position_pct) / 200  # +50% at max inventory

        # 3. Book imbalance
        book_analysis = self.book_analyzer.analyze(order_book)
        imbalance_adj = book_analysis.price_adjustment

        # 4. Calculate final spread
        spread = self.base_spread * Decimal(str(vol_mult)) * Decimal(str(inv_mult))
        spread = max(self.min_spread, min(self.max_spread, spread))

        # 5. Calculate bid/ask with all adjustments
        half_spread = spread / 2

        # Base prices
        bid_price = mid - half_spread
        ask_price = mid + half_spread

        # Add inventory skew
        bid_price = bid_price + inv_state.bid_skew
        ask_price = ask_price + inv_state.ask_skew

        # Add imbalance adjustment (shift both in same direction)
        bid_price = bid_price + imbalance_adj
        ask_price = ask_price + imbalance_adj

        # Round to tick
        bid_price = (bid_price * 100).quantize(Decimal("1")) / 100
        ask_price = (ask_price * 100).quantize(Decimal("1")) / 100

        # Ensure valid range and don't cross
        bid_price = max(Decimal("0.01"), min(Decimal("0.98"), bid_price))
        ask_price = max(Decimal("0.02"), min(Decimal("0.99"), ask_price))
        if bid_price >= ask_price:
            # Revert to simple spread around mid
            bid_price = mid - half_spread
            ask_price = mid + half_spread
            bid_price = (bid_price * 100).quantize(Decimal("1")) / 100
            ask_price = (ask_price * 100).quantize(Decimal("1")) / 100

        # Build state for TUI
        state = SmartMMState(
            base_spread=self.base_spread,
            vol_multiplier=vol_mult,
            inv_multiplier=inv_mult,
            final_spread=spread,
            volatility_level=vol_state.level,
            realized_vol=vol_state.realized_vol,
            inventory_pct=inv_state.position_pct,
            inventory_level=inv_state.inventory_level,
            bid_skew=inv_state.bid_skew,
            ask_skew=inv_state.ask_skew,
            imbalance_signal=book_analysis.imbalance_signal,
            imbalance_adjustment=imbalance_adj,
            unrealized_pnl=inv_state.unrealized_pnl,
            vwap_entry=inv_state.vwap_entry,
        )

        return bid_price, ask_price, state

    def _should_requote(self, mid: Decimal) -> bool:
        """Check if quotes need updating."""
        if self.bid_order is None and self.ask_order is None:
            return True

        if self.last_mid is not None:
            move = abs(mid - self.last_mid)
            if move >= self.requote_threshold:
                logger.info(f"Mid moved {move:.4f} - requoting")
                return True

        return False

    async def _update_quotes(self, mid: Decimal, bid_price: Decimal, ask_price: Decimal):
        """Cancel old quotes and place new ones with size adjustments."""
        logger.info(f"Mid: {mid:.2f} -> Bid: {bid_price:.2f}, Ask: {ask_price:.2f}")

        if self._last_state:
            logger.info(
                f"  Spread: {self._last_state.final_spread:.3f} "
                f"(vol={self._last_state.vol_multiplier:.2f}x, "
                f"inv={self._last_state.inv_multiplier:.2f}x)"
            )

        await self._cancel_all_quotes()

        # Get size multipliers from inventory
        bid_size_mult, ask_size_mult = self.inventory.get_size_multipliers()

        bid_size = self.size * Decimal(str(bid_size_mult))
        ask_size = self.size * Decimal(str(ask_size_mult))

        # Round sizes
        bid_size = bid_size.quantize(Decimal("0.01"))
        ask_size = ask_size.quantize(Decimal("0.01"))

        # Ensure minimum size
        from src.config import MIN_ORDER_SIZE
        bid_size = max(MIN_ORDER_SIZE, bid_size)
        ask_size = max(MIN_ORDER_SIZE, ask_size)

        # Place quotes (respecting inventory limits via size reduction, not hard stops)
        inv_state = self.inventory.get_state()

        # Only skip side entirely if at absolute max
        if inv_state.inventory_level != "MAX_LONG":
            self.bid_order = self._place_quote(OrderSide.BUY, bid_price, bid_size)
        else:
            logger.info("MAX_LONG - skipping bid")

        if inv_state.inventory_level != "MAX_SHORT":
            self.ask_order = self._place_quote(OrderSide.SELL, ask_price, ask_size)
        else:
            logger.info("MAX_SHORT - skipping ask")

    def _place_quote(self, side: OrderSide, price: Decimal, size: Decimal) -> Optional[Order]:
        """Place a single quote."""
        try:
            order = place_order(
                token_id=self.token_id,
                side=side,
                price=price,
                size=size
            )
            logger.info(f"Placed {side.value} {size} @ {price}: {order.id}")
            return order
        except OrderError as e:
            logger.error(f"Failed to place {side.value}: {e}")
            return None

    async def _cancel_all_quotes(self):
        """Cancel all our quotes."""
        if self.bid_order and self.bid_order.is_live:
            cancel_order(self.bid_order.id)
        if self.ask_order and self.ask_order.is_live:
            cancel_order(self.ask_order.id)

        self.bid_order = None
        self.ask_order = None

    async def _shutdown(self):
        """Clean shutdown."""
        logger.info("Shutting down smart market maker...")

        summary = self.risk.get_risk_event_summary()
        if summary["total_events"] > 0:
            logger.info(f"Risk Event Summary:")
            logger.info(f"  Total events: {summary['total_events']}")
            logger.info(f"  STOP events: {summary['stop_events']} (enforced: {summary['enforced_events']})")
            logger.info(f"  WARN events: {summary['warn_events']}")
            logger.info(f"  Final P&L: {self.risk.daily_pnl}")

        # Log smart MM specific stats
        if self._last_state:
            logger.info(f"Final state:")
            logger.info(f"  Volatility: {self._last_state.volatility_level} ({self._last_state.realized_vol:.1%})")
            logger.info(f"  Inventory: {self._last_state.inventory_level} ({self._last_state.inventory_pct:.1f}%)")
            logger.info(f"  Unrealized P&L: {self._last_state.unrealized_pnl}")

        logger.info("Cancelling all orders...")
        cancel_all_orders(self.token_id)

        if self.feed:
            logger.info("Stopping feed...")
            await self.feed.stop()

        logger.info("Smart market maker stopped.")


async def run_smart_market_maker(token_id: str, **kwargs):
    """
    Convenience function to run the smart market maker.

    Usage:
        asyncio.run(run_smart_market_maker("token123"))
    """
    mm = SmartMarketMaker(token_id, **kwargs)
    await mm.run()
