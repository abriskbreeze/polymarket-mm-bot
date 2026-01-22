"""
TDD Tests for Dynamic Position Limits

Tests adaptive position limit calculation.
"""

import pytest
from decimal import Decimal
from src.risk.dynamic_limits import DynamicLimitManager, MarketConditions


class TestBasicLimits:
    """Test basic limit calculations."""

    @pytest.fixture
    def manager(self):
        return DynamicLimitManager(base_limit=Decimal("100"))

    def test_default_limit_is_base(self, manager):
        """With neutral conditions, limit equals base."""
        limit = manager.get_limit()
        assert limit == Decimal("100")

    def test_limit_increases_with_confidence(self, manager):
        """Limit increases when confidence is high."""
        manager.set_conditions(MarketConditions(confidence=0.9))
        limit = manager.get_limit()
        assert limit > Decimal("100")

    def test_limit_decreases_with_drawdown(self, manager):
        """Limit decreases during drawdown."""
        manager.record_pnl(Decimal("-30"))  # -30% of base
        limit = manager.get_limit()
        assert limit < Decimal("100")

    def test_limit_never_below_minimum(self, manager):
        """Limit never goes below configured minimum."""
        manager.record_pnl(Decimal("-200"))  # Huge loss
        limit = manager.get_limit()
        assert limit >= Decimal("20")  # 20% floor

    def test_limit_never_above_maximum(self, manager):
        """Limit never exceeds configured maximum."""
        manager.set_conditions(MarketConditions(confidence=1.0))
        manager.record_pnl(Decimal("500"))  # Big win
        limit = manager.get_limit()
        assert limit <= Decimal("200")  # 2x ceiling


class TestConfidenceFactors:
    """Test confidence-based adjustments."""

    @pytest.fixture
    def manager(self):
        return DynamicLimitManager(base_limit=Decimal("100"))

    def test_low_volatility_increases_confidence(self, manager):
        """Low volatility increases confidence."""
        manager.set_conditions(MarketConditions(
            volatility_level="LOW",
            fill_rate=0.5,
        ))
        limit = manager.get_limit()
        assert limit > Decimal("100")

    def test_high_volatility_decreases_confidence(self, manager):
        """High volatility decreases confidence."""
        manager.set_conditions(MarketConditions(
            volatility_level="HIGH",
            fill_rate=0.5,
        ))
        limit = manager.get_limit()
        assert limit < Decimal("100")

    def test_high_fill_rate_increases_confidence(self, manager):
        """High fill rate indicates good conditions."""
        manager.set_conditions(MarketConditions(
            volatility_level="NORMAL",
            fill_rate=0.9,
        ))
        limit = manager.get_limit()
        assert limit > Decimal("100")

    def test_low_fill_rate_decreases_confidence(self, manager):
        """Low fill rate indicates poor conditions."""
        manager.set_conditions(MarketConditions(
            volatility_level="NORMAL",
            fill_rate=0.2,
        ))
        limit = manager.get_limit()
        assert limit < Decimal("100")


class TestDrawdownPenalty:
    """Test drawdown-based limit reduction."""

    @pytest.fixture
    def manager(self):
        return DynamicLimitManager(
            base_limit=Decimal("100"),
            max_daily_loss=Decimal("50"),
        )

    def test_no_penalty_without_loss(self, manager):
        """No penalty when P&L is positive."""
        manager.record_pnl(Decimal("20"))
        penalty = manager.get_drawdown_penalty()
        assert penalty == 0.0

    def test_linear_penalty_with_loss(self, manager):
        """Penalty scales linearly with loss."""
        manager.record_pnl(Decimal("-25"))  # 50% of max loss
        penalty = manager.get_drawdown_penalty()
        assert penalty == pytest.approx(0.25, rel=0.1)  # ~25% penalty

    def test_max_penalty_at_limit(self, manager):
        """Penalty maxes out at daily loss limit."""
        manager.record_pnl(Decimal("-50"))  # At limit
        penalty = manager.get_drawdown_penalty()
        assert penalty >= 0.5  # 50%+ penalty

    def test_penalty_applied_to_limit(self, manager):
        """Drawdown penalty reduces effective limit."""
        manager.record_pnl(Decimal("-25"))
        limit = manager.get_limit()

        # Base 100 with ~25% penalty applied via formula
        # Should be noticeably below base
        assert limit < Decimal("90")
        assert limit > Decimal("60")


class TestLimitHistory:
    """Test limit change tracking."""

    @pytest.fixture
    def manager(self):
        return DynamicLimitManager(base_limit=Decimal("100"))

    def test_tracks_limit_changes(self, manager):
        """Manager tracks history of limit changes."""
        manager.set_conditions(MarketConditions(confidence=0.9))
        _ = manager.get_limit()

        manager.set_conditions(MarketConditions(confidence=0.5))
        _ = manager.get_limit()

        history = manager.get_limit_history()
        assert len(history) >= 2

    def test_smooth_transitions(self, manager):
        """Limits should change gradually, not jump."""
        manager.set_conditions(MarketConditions(confidence=0.3))
        limit1 = manager.get_limit()

        manager.set_conditions(MarketConditions(confidence=0.9))
        limit2 = manager.get_limit()

        # Should not instantly double
        assert limit2 / limit1 < Decimal("1.5")
