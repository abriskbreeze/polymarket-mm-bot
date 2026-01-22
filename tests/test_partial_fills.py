"""
TDD Tests for Partial Fill Handling

Tests detection and response to partial fills.
"""

import pytest
from decimal import Decimal
from src.strategy.partial_fill_handler import PartialFillHandler, FillEvent


class TestPartialFillDetection:
    """Test detecting partial fills."""

    @pytest.fixture
    def handler(self):
        return PartialFillHandler()

    def test_detect_partial_fill(self, handler):
        """Detect when order is partially filled."""
        handler.track_order(
            order_id="order-1",
            side="BUY",
            size=Decimal("100"),
            price=Decimal("0.50"),
        )

        event = handler.record_fill(
            order_id="order-1",
            filled_size=Decimal("30"),
        )

        assert event.is_partial is True
        assert event.remaining_size == Decimal("70")

    def test_detect_full_fill(self, handler):
        """Detect full fill."""
        handler.track_order(
            order_id="order-1",
            side="BUY",
            size=Decimal("100"),
            price=Decimal("0.50"),
        )

        event = handler.record_fill(
            order_id="order-1",
            filled_size=Decimal("100"),
        )

        assert event.is_partial is False
        assert event.remaining_size == Decimal("0")


class TestPartialFillResponse:
    """Test response strategies for partial fills."""

    @pytest.fixture
    def handler(self):
        return PartialFillHandler()

    def test_hedge_recommendation_on_partial(self, handler):
        """Recommend hedging after partial fill."""
        handler.track_order(
            order_id="order-1",
            side="BUY",
            size=Decimal("100"),
            price=Decimal("0.50"),
        )

        event = handler.record_fill(
            order_id="order-1",
            filled_size=Decimal("50"),
        )

        response = handler.get_response(event)

        # Should recommend tightening the opposite side
        assert response.tighten_opposite_spread is True
        assert response.hedge_urgency > 0

    def test_no_hedge_on_small_partial(self, handler):
        """Don't hedge urgently on tiny partial fills."""
        handler.track_order(
            order_id="order-1",
            side="BUY",
            size=Decimal("100"),
            price=Decimal("0.50"),
        )

        event = handler.record_fill(
            order_id="order-1",
            filled_size=Decimal("5"),  # Only 5%
        )

        response = handler.get_response(event)

        # Small partial shouldn't trigger urgent hedge
        assert response.hedge_urgency < 0.5


class TestPartialFillStatistics:
    """Test partial fill tracking for analysis."""

    @pytest.fixture
    def handler(self):
        return PartialFillHandler()

    def test_partial_fill_rate(self, handler):
        """Track rate of partial vs full fills."""
        # Record some fills
        for i in range(10):
            handler.track_order(f"order-{i}", "BUY", Decimal("100"), Decimal("0.50"))

        # 3 full fills
        for i in range(3):
            handler.record_fill(f"order-{i}", Decimal("100"))

        # 7 partial fills
        for i in range(3, 10):
            handler.record_fill(f"order-{i}", Decimal("50"))

        stats = handler.get_statistics()

        assert stats.partial_fill_rate == pytest.approx(0.7, rel=0.1)
