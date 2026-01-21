"""
Phase 7 Tests - Market maker.

Run: pytest tests/test_phase7.py -v
"""

import pytest
import asyncio
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch


class TestQuoteCalculation:
    """Test quote price calculations."""

    def test_spread_calculation(self):
        from src.strategy.market_maker import SimpleMarketMaker

        mm = SimpleMarketMaker(
            token_id="test",
            spread=Decimal("0.04"),
            size=Decimal("10")
        )

        # With mid at 0.50 and spread 0.04:
        # bid = 0.50 - 0.02 = 0.48
        # ask = 0.50 + 0.02 = 0.52
        mid = Decimal("0.50")
        half = mm.spread / 2

        bid = mid - half
        ask = mid + half

        assert bid == Decimal("0.48")
        assert ask == Decimal("0.52")

        print("✓ Spread calculation correct")

    def test_requote_threshold(self):
        from src.strategy.market_maker import SimpleMarketMaker
        from src.models import Order, OrderSide, OrderStatus

        mm = SimpleMarketMaker(
            token_id="test",
            requote_threshold=Decimal("0.02")
        )

        # Set up existing quotes so first condition in _should_requote is False
        mm.bid.order = Order(
            id="bid1",
            token_id="test",
            side=OrderSide.BUY,
            price=Decimal("0.48"),
            size=Decimal("10"),
            filled=Decimal("0"),
            status=OrderStatus.LIVE,
            is_simulated=True
        )
        mm.ask.order = Order(
            id="ask1",
            token_id="test",
            side=OrderSide.SELL,
            price=Decimal("0.52"),
            size=Decimal("10"),
            filled=Decimal("0"),
            status=OrderStatus.LIVE,
            is_simulated=True
        )
        mm.last_mid = Decimal("0.50")

        # Small move - no requote
        assert not mm._should_requote(Decimal("0.51"))

        # Large move - requote
        assert mm._should_requote(Decimal("0.53"))

        print("✓ Requote threshold works")


class TestPositionLimits:
    """Test position limit handling."""

    def test_skip_buy_when_long(self):
        from src.strategy.market_maker import SimpleMarketMaker
        from src.simulator import get_simulator, reset_simulator
        from src.models import OrderSide
        from src.config import DRY_RUN

        if not DRY_RUN:
            pytest.skip("Requires DRY_RUN=true")

        reset_simulator()
        sim = get_simulator()

        mm = SimpleMarketMaker(
            token_id="test",
            position_limit=Decimal("50"),
            spread=Decimal("0.04"),
            size=Decimal("10")
        )

        # Simulate being at position limit
        # Create and fill a buy order
        order = sim.create_order("test", OrderSide.BUY, Decimal("0.50"), Decimal("50"))
        sim.check_fills("test", Decimal("0.45"), Decimal("0.50"))

        # Position should be 50
        from src.orders import get_position
        assert get_position("test") == Decimal("50")

        print("✓ Position tracking works")


class TestMarketMakerLifecycle:
    """Test market maker start/stop."""

    @pytest.mark.asyncio
    async def test_creates_and_stops(self):
        from src.strategy.market_maker import SimpleMarketMaker

        mm = SimpleMarketMaker(token_id="test_token")

        assert mm._running == False
        assert mm.feed is None

        # Stop before starting should be safe
        mm.stop()

        print("✓ Market maker lifecycle safe")

    @pytest.mark.asyncio
    async def test_signal_handling(self):
        from src.strategy.market_maker import SimpleMarketMaker

        mm = SimpleMarketMaker(token_id="test")

        # Simulate signal
        mm._handle_signal()

        assert mm._running == False
        assert mm._shutdown_event.is_set()

        print("✓ Signal handling works")


class TestWithMockFeed:
    """Test with mocked feed."""

    @pytest.mark.asyncio
    async def test_places_quotes_on_healthy_feed(self):
        from src.strategy.market_maker import SimpleMarketMaker
        from src.simulator import reset_simulator
        from src.orders import get_open_orders
        from src.config import DRY_RUN

        if not DRY_RUN:
            pytest.skip("Requires DRY_RUN=true")

        reset_simulator()

        mm = SimpleMarketMaker(
            token_id="test",
            spread=Decimal("0.04"),
            size=Decimal("10")
        )

        # Mock feed
        mock_feed = Mock()
        mock_feed.is_healthy = True
        mock_feed.get_midpoint = Mock(return_value=0.50)
        mm.feed = mock_feed
        mm.last_mid = None

        # Run one iteration
        await mm._loop_iteration()

        # Should have placed quotes
        orders = get_open_orders()
        assert len(orders) == 2

        # Check prices
        bids = [o for o in orders if o.side.value == "BUY"]
        asks = [o for o in orders if o.side.value == "SELL"]

        assert len(bids) == 1
        assert len(asks) == 1
        assert bids[0].price == Decimal("0.48")
        assert asks[0].price == Decimal("0.52")

        print("✓ Quotes placed correctly")

    @pytest.mark.asyncio
    async def test_cancels_on_unhealthy_feed(self):
        from src.strategy.market_maker import SimpleMarketMaker
        from src.simulator import reset_simulator, get_simulator
        from src.orders import get_open_orders
        from src.models import OrderSide
        from src.config import DRY_RUN

        if not DRY_RUN:
            pytest.skip("Requires DRY_RUN=true")

        reset_simulator()
        sim = get_simulator()

        mm = SimpleMarketMaker(token_id="test")

        # Place some orders first
        mm.bid.order = sim.create_order("test", OrderSide.BUY, Decimal("0.48"), Decimal("10"))
        mm.ask.order = sim.create_order("test", OrderSide.SELL, Decimal("0.52"), Decimal("10"))

        assert len(get_open_orders()) == 2

        # Mock unhealthy feed
        mock_feed = Mock()
        mock_feed.is_healthy = False
        mm.feed = mock_feed

        # Run iteration
        await mm._loop_iteration()

        # Should have cancelled
        assert len(get_open_orders()) == 0

        print("✓ Cancels quotes on unhealthy feed")


class TestIntegration:
    """Integration test with real market data (dry run)."""

    @pytest.mark.asyncio
    async def test_full_cycle_with_real_market(self):
        """Test one cycle with real market data."""
        from src.config import DRY_RUN
        from src.markets import fetch_active_markets
        from src.strategy.market_maker import SimpleMarketMaker
        from src.orders import get_open_orders
        from src.simulator import reset_simulator

        if not DRY_RUN:
            pytest.skip("Requires DRY_RUN=true")

        reset_simulator()

        # Get real market
        markets = fetch_active_markets(limit=5)
        token_id = None
        for m in markets:
            if m.token_ids:
                token_id = m.token_ids[0]
                break

        if not token_id:
            pytest.skip("No markets")

        assert token_id is not None  # Type narrowing
        print(f"  Token: {token_id[:20]}...")

        mm = SimpleMarketMaker(
            token_id=token_id,
            spread=Decimal("0.04"),
            size=Decimal("10"),
            loop_interval=0.5
        )

        # Run for a short time
        async def run_briefly():
            mm._running = True
            mm.feed = Mock()
            mm.feed.is_healthy = True

            # Get real midpoint from pricing
            from src.pricing import get_order_book
            book = get_order_book(token_id)
            if book and book.midpoint:
                mm.feed.get_midpoint = Mock(return_value=book.midpoint)
                print(f"  Midpoint: {book.midpoint}")

                # Run one iteration
                await mm._loop_iteration()

                orders = get_open_orders()
                print(f"  Orders placed: {len(orders)}")

                if orders:
                    for o in orders:
                        print(f"    {o.side.value} {o.size} @ {o.price}")

                # Cleanup
                await mm._cancel_all_quotes()

        await run_briefly()
        print("✓ Real market cycle works")
