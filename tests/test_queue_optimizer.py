"""
TDD Tests for Queue Position Optimization

Tests queue analysis and smart placement decisions.
"""

import pytest
from decimal import Decimal
from src.strategy.queue_optimizer import QueueOptimizer, PlacementDecision


class TestQueueAnalysis:
    """Test queue depth analysis."""

    @pytest.fixture
    def optimizer(self):
        return QueueOptimizer(tick_size=Decimal("0.01"))

    def test_empty_queue_no_improvement(self, optimizer):
        """Don't improve if queue is empty."""
        decision = optimizer.analyze_placement(
            side="BUY",
            best_price=Decimal("0.50"),
            queue_depth_at_best=0,
            our_size=Decimal("10"),
        )

        assert decision.should_improve is False
        assert decision.recommended_price == Decimal("0.50")

    def test_improve_on_long_queue(self, optimizer):
        """Improve by one tick when queue is long."""
        decision = optimizer.analyze_placement(
            side="BUY",
            best_price=Decimal("0.50"),
            queue_depth_at_best=500,  # $500 ahead of us
            our_size=Decimal("10"),
        )

        assert decision.should_improve is True
        assert decision.recommended_price == Decimal("0.51")  # +1 tick

    def test_no_improve_short_queue(self, optimizer):
        """Don't improve if queue is short - save edge."""
        decision = optimizer.analyze_placement(
            side="BUY",
            best_price=Decimal("0.50"),
            queue_depth_at_best=20,  # Only $20 ahead
            our_size=Decimal("10"),
        )

        assert decision.should_improve is False

    def test_sell_side_improvement(self, optimizer):
        """Sell side improves by lowering price."""
        decision = optimizer.analyze_placement(
            side="SELL",
            best_price=Decimal("0.55"),
            queue_depth_at_best=500,
            our_size=Decimal("10"),
        )

        assert decision.should_improve is True
        assert decision.recommended_price == Decimal("0.54")  # -1 tick

    def test_never_cross_spread(self, optimizer):
        """Never recommend crossing the spread."""
        decision = optimizer.analyze_placement(
            side="BUY",
            best_price=Decimal("0.50"),
            queue_depth_at_best=1000,
            our_size=Decimal("10"),
            opposite_best=Decimal("0.51"),
        )

        # Should not recommend 0.51 if ask is at 0.51
        assert decision.recommended_price < Decimal("0.51")


class TestQueueMetrics:
    """Test queue metric tracking."""

    @pytest.fixture
    def optimizer(self):
        return QueueOptimizer()

    def test_fill_rate_tracking(self, optimizer):
        """Track fill rate by queue position."""
        # Record some fills
        optimizer.record_fill(queue_position=10, filled=True)
        optimizer.record_fill(queue_position=100, filled=True)
        optimizer.record_fill(queue_position=500, filled=False)

        # Front of queue should have higher fill rate
        rate_front = optimizer.get_fill_rate(queue_position=10)
        rate_back = optimizer.get_fill_rate(queue_position=500)

        assert rate_front > rate_back

    def test_optimal_position_calculation(self, optimizer):
        """Calculate optimal queue position based on history."""
        # Build up history
        for _ in range(10):
            optimizer.record_fill(queue_position=50, filled=True)
            optimizer.record_fill(queue_position=200, filled=False)

        optimal = optimizer.get_optimal_position()

        # Should recommend being near positions that fill
        assert optimal < 100
