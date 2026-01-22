"""
TDD Tests for Correlation-Aware Risk

Tests correlation tracking and portfolio risk management.
"""

import pytest
from decimal import Decimal
from src.risk.correlation import CorrelationTracker, PortfolioRisk


class TestCorrelationTracking:
    """Test correlation calculation."""

    @pytest.fixture
    def tracker(self):
        return CorrelationTracker()

    def test_perfect_correlation(self, tracker):
        """Detect perfectly correlated markets."""
        # Same price moves
        for i in range(20):
            tracker.record_price("market_a", 0.50 + i * 0.01)
            tracker.record_price("market_b", 0.50 + i * 0.01)

        corr = tracker.get_correlation("market_a", "market_b")
        assert corr == pytest.approx(1.0, abs=0.1)

    def test_inverse_correlation(self, tracker):
        """Detect inversely correlated markets."""
        for i in range(20):
            tracker.record_price("market_a", 0.50 + i * 0.01)
            tracker.record_price("market_b", 0.50 - i * 0.01)

        corr = tracker.get_correlation("market_a", "market_b")
        assert corr == pytest.approx(-1.0, abs=0.1)

    def test_no_correlation(self, tracker):
        """Independent markets have ~0 correlation."""
        import random
        random.seed(42)

        for _ in range(100):
            tracker.record_price("market_a", random.random())
            tracker.record_price("market_b", random.random())

        corr = tracker.get_correlation("market_a", "market_b")
        assert abs(corr) < 0.3  # Near zero


class TestPortfolioRisk:
    """Test portfolio-level risk management."""

    @pytest.fixture
    def risk(self):
        return PortfolioRisk(max_correlated_exposure=Decimal("200"))

    def test_allow_uncorrelated_positions(self, risk):
        """Allow large positions in uncorrelated markets."""
        risk.set_correlation("market_a", "market_b", 0.0)

        can_add = risk.can_add_position(
            market="market_a",
            size=Decimal("100"),
            existing_positions={"market_b": Decimal("100")},
        )

        assert can_add is True

    def test_limit_correlated_positions(self, risk):
        """Limit positions in correlated markets."""
        risk.set_correlation("market_a", "market_b", 0.9)

        can_add = risk.can_add_position(
            market="market_a",
            size=Decimal("150"),
            existing_positions={"market_b": Decimal("100")},
        )

        assert can_add is False  # Would exceed correlated limit

    def test_portfolio_beta(self, risk):
        """Calculate portfolio beta from correlations."""
        risk.set_correlation("market_a", "market_b", 0.8)

        beta = risk.calculate_portfolio_beta({
            "market_a": Decimal("100"),
            "market_b": Decimal("100"),
        })

        assert beta > 1.0  # Correlated positions increase beta
