"""
Market maker for Polymarket.

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
from src.strategy.parity import check_parity, ParityStatus
from src.risk.market_pnl import MarketPnLTracker
from src.telemetry.trade_logger import TradeLogger
from src.alpha import (
    ArbitrageDetector,
    PairTracker,
    FlowAnalyzer,
    EventTracker,
    TokenPair,
)
from src.config import (
    ARB_MIN_PROFIT_BPS,
    FLOW_WINDOW_SECONDS,
)

logger = setup_logging()


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

    Features:
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
        complement_token_id: Optional[str] = None,
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
        self.pnl_tracker = MarketPnLTracker()
        self.trade_logger = TradeLogger(log_file=f"logs/trades_{token_id[:8]}.jsonl")
        self.complement_token_id = complement_token_id

        # Alpha modules
        self.arb_detector = ArbitrageDetector(min_profit_bps=ARB_MIN_PROFIT_BPS)
        self.pair_tracker = PairTracker()
        self.flow_analyzer = FlowAnalyzer(
            token_id=token_id,
            window_seconds=FLOW_WINDOW_SECONDS,
        )
        self.event_tracker = EventTracker()

        # Register YES/NO pair for arbitrage detection
        if self.complement_token_id:
            pair = TokenPair(
                condition_id=f"pair-{token_id[:8]}",
                yes_token_id=token_id,
                no_token_id=self.complement_token_id,
                market_slug="",
            )
            self.arb_detector.register_pair(pair)
            self.pair_tracker._pairs[pair.condition_id] = pair
            logger.info(f"Registered arbitrage pair: {token_id[:8]} <-> {self.complement_token_id[:8]}")

        # State
        self.feed: Optional[MarketFeed] = None
        self.bid_order: Optional[Order] = None
        self.ask_order: Optional[Order] = None
        self.last_mid: Optional[Decimal] = None
        self._running = False
        self._shutdown_event = asyncio.Event()
        self.risk = get_risk_manager()
        self._loop_count = 0
        self._last_heartbeat = 0.0

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
            # Subscribe to both tokens if we have a complement (for arbitrage)
            tokens_to_watch = [self.token_id]
            if self.complement_token_id:
                tokens_to_watch.append(self.complement_token_id)
                logger.info(f"Subscribing to YES + NO tokens for arbitrage")
            await self.feed.start(tokens_to_watch)
            await self._wait_for_data()

            # Register flow analyzer callback
            def flow_callback(price, size, side, is_taker):
                self.flow_analyzer.record_trade(price, size, side, is_taker)

            self.feed.register_flow_callback(self.token_id, flow_callback)

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
        pnl_stats = self.pnl_tracker.get_market_stats(self.token_id)
        return {
            'bid_order': self.bid_order,
            'ask_order': self.ask_order,
            'last_mid': self.last_mid,
            'running': self._running,
            'smart_state': self._last_state,
            'realized_pnl': pnl_stats.realized_pnl if pnl_stats else Decimal("0"),
            'trade_count': pnl_stats.trade_count if pnl_stats else 0,
            'win_rate': pnl_stats.win_rate if pnl_stats else 0.0,
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
        import time
        self._loop_count += 1

        # Heartbeat every 30 seconds
        now = time.time()
        if now - self._last_heartbeat >= 30:
            pnl_stats = self.pnl_tracker.get_market_stats(self.token_id)
            pnl_str = f"${pnl_stats.realized_pnl:.2f}" if pnl_stats else "$0.00"
            fills = pnl_stats.trade_count if pnl_stats else 0
            logger.info(
                f"[HEARTBEAT] Loop #{self._loop_count} | "
                f"Mid: {self.last_mid or 'N/A'} | "
                f"Fills: {fills} | P&L: {pnl_str}"
            )
            self._last_heartbeat = now

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

        # Scan for arbitrage opportunities
        if self.complement_token_id and self.feed:
            def price_getter(token_id: str) -> Optional[Decimal]:
                if not self.feed:
                    return None
                price = self.feed.get_midpoint(token_id)
                return Decimal(str(price)) if price is not None else None

            # Get prices for debugging
            yes_price = price_getter(self.token_id)
            no_price = price_getter(self.complement_token_id)

            signals = self.arb_detector.scan_all(price_getter)

            # Debug log on first loop
            if self._loop_count == 1 and yes_price and no_price:
                logger.info(
                    f"[ARB] Scanning: YES={yes_price:.4f} NO={no_price:.4f} "
                    f"Sum={yes_price + no_price:.4f}"
                )

            if signals:
                for signal in signals:
                    logger.info(
                        f"[ARB] {signal.type.value}: {signal.recommended_action} "
                        f"({signal.profit_bps}bps)"
                    )

        # Get market data
        mid = self.feed.get_midpoint(self.token_id)
        if mid is None:
            logger.warning("No midpoint available")
            return
        mid = Decimal(str(mid))

        # Check YES/NO parity for arbitrage detection
        if self.complement_token_id:
            no_mid = self.feed.get_midpoint(self.complement_token_id)
            if no_mid is not None:
                parity = check_parity(mid, Decimal(str(no_mid)))
                if parity == ParityStatus.OVERPRICED:
                    logger.warning(
                        f"Arbitrage opportunity: YES+NO = {mid + Decimal(str(no_mid)):.3f} "
                        "(overpriced, skipping quotes)"
                    )
                    self.trade_logger.log_event(
                        "arbitrage_detected",
                        yes_price=str(mid),
                        no_price=str(no_mid),
                        status=parity.value,
                    )
                    return
                elif parity == ParityStatus.NEAR_ARBITRAGE:
                    logger.info(f"Near-arbitrage: YES+NO = {mid + Decimal(str(no_mid)):.3f}")

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
                        # Track P&L per market
                        self.pnl_tracker.record_trade(
                            market_id=self.token_id,
                            side=trade.side.value,
                            price=trade.price,
                            size=trade.size,
                        )
                        # Log trade for analysis
                        self.trade_logger.log_trade(
                            market_id=self.token_id,
                            side=trade.side.value,
                            price=trade.price,
                            size=trade.size,
                            fill_type="maker",
                            order_id=trade.order_id if hasattr(trade, 'order_id') else None,
                        )

        # Calculate dynamic spread and quotes
        result = self._calculate_quotes(mid, order_book)
        if result is None:
            # Event signal says not to trade - cancel quotes
            await self._cancel_all_quotes()
            return

        bid_price, ask_price, state = result

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
    ) -> Optional[tuple[Decimal, Decimal, SmartMMState]]:
        """Calculate optimal bid/ask prices using all signals. Returns None if should not quote."""
        # Check event signal first - may prohibit trading
        event_signal = self.event_tracker.get_signal(self.token_id)
        if not event_signal.should_trade:
            logger.warning(f"[EVENT] {event_signal.reason} - not quoting")
            return None

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

        # 6. Alpha signal adjustments

        # 6a. Arbitrage detector - skew quotes based on YES/NO price divergence
        bid_price, ask_price = self.arb_detector.get_quote_adjustment(
            self.token_id, bid_price, ask_price
        )

        # 6b. Flow analyzer - adjust based on order flow direction
        flow_state = self.flow_analyzer.get_state()

        # Log flow state if non-neutral
        if flow_state.signal.value != "neutral" and flow_state.trade_count > 0:
            logger.info(
                f"[FLOW] {flow_state.signal.value.upper()}: "
                f"{flow_state.trade_count} trades, "
                f"imbalance={flow_state.imbalance:.2f}, "
                f"skew={flow_state.recommended_skew:.4f}"
            )

        bid_price = bid_price + flow_state.recommended_skew
        ask_price = ask_price + flow_state.recommended_skew

        # Widen spread if high aggression detected (informed traders)
        if self.flow_analyzer.should_widen_spread():
            logger.info(f"[FLOW] High aggression detected - widening spread 20%")
            spread = spread * Decimal("1.2")  # 20% wider
            # Recalculate with wider spread but keep skews
            half_spread_new = spread / 2
            bid_price = mid - half_spread_new + inv_state.bid_skew + imbalance_adj + flow_state.recommended_skew
            ask_price = mid + half_spread_new + inv_state.ask_skew + imbalance_adj + flow_state.recommended_skew
            bid_price, ask_price = self.arb_detector.get_quote_adjustment(
                self.token_id, bid_price, ask_price
            )

        # 6c. Event tracker spread adjustment (should_trade already checked)
        if event_signal.spread_multiplier != 1.0:
            logger.info(
                f"[EVENT] Spread multiplier: {event_signal.spread_multiplier:.2f}x - {event_signal.reason}"
            )
            # Widen spread near events (risk management)
            spread = spread * Decimal(str(event_signal.spread_multiplier))
            half_spread_evt = spread / 2
            bid_price = mid - half_spread_evt + inv_state.bid_skew + imbalance_adj + flow_state.recommended_skew
            ask_price = mid + half_spread_evt + inv_state.ask_skew + imbalance_adj + flow_state.recommended_skew

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

        # Log quote update
        self.trade_logger.log_quote(
            market_id=self.token_id,
            bid_price=bid_price,
            ask_price=ask_price,
            bid_size=bid_size,
            ask_size=ask_size,
            spread=ask_price - bid_price,
            mid=mid,
        )

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
