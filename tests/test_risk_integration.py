"""
Integration tests for Phase 3 Risk-Adjusted Returns in RiskManager.

Tests that Phase 3 modules are properly integrated into the main RiskManager.
"""

import pytest
from decimal import Decimal
from src.risk.manager import RiskManager
from src.risk.dynamic_limits import MarketConditions


class TestRiskManagerPhase3Integration:
    """Test Phase 3 module integration in RiskManager."""

    @pytest.fixture
    def manager(self):
        return RiskManager(
            max_daily_loss=Decimal("50"),
            max_position=Decimal("100"),
            enforce=False,
        )

    def test_status_includes_phase3_fields(self, manager):
        """Status dict includes Phase 3 metrics."""
        status = manager.get_status()

        assert "dynamic_limit" in status
        assert "toxicity" in status
        assert "toxicity_buy" in status
        assert "toxicity_sell" in status
        assert "adverse_widen_spread" in status
        assert "adverse_spread_mult" in status
        assert "adverse_size_mult" in status
        assert "kelly_from_history" in status

    def test_dynamic_limit_starts_at_base(self, manager):
        """Dynamic limit starts at base position limit."""
        limit = manager.get_dynamic_limit()
        assert limit == Decimal("100")

    def test_dynamic_limit_responds_to_conditions(self, manager):
        """Dynamic limit adjusts based on market conditions."""
        # High confidence should increase limit
        manager.update_market_conditions(MarketConditions(confidence=0.9))
        high_conf_limit = manager.get_dynamic_limit()

        # Low confidence should decrease limit
        manager.update_market_conditions(MarketConditions(confidence=0.2))
        low_conf_limit = manager.get_dynamic_limit()

        # High confidence limit should be higher (after smoothing)
        assert high_conf_limit > low_conf_limit

    def test_adverse_selection_tracking(self, manager):
        """Adverse selection detector tracks fills."""
        # Record some trades
        manager.record_trade("token1", "BUY", Decimal("0.50"), Decimal("10"))
        manager.record_trade("token1", "BUY", Decimal("0.51"), Decimal("10"))

        # Record adverse price movement
        manager.record_price_after_fill(0, Decimal("0.45"))  # Bad for buyer
        manager.record_price_after_fill(1, Decimal("0.45"))  # Bad for buyer

        # Should have high toxicity
        toxicity = manager.get_toxicity()
        assert toxicity > 0.5

    def test_adverse_selection_response(self, manager):
        """Adverse selection detector provides recommendations."""
        # Create toxic environment
        for i in range(10):
            manager.record_trade("token1", "BUY", Decimal("0.50"), Decimal("10"))
            manager.record_price_after_fill(i, Decimal("0.45"))

        response = manager.get_adverse_selection_response()
        assert response.widen_spread is True
        assert response.spread_multiplier > 1.0

    def test_kelly_from_trade_history(self, manager):
        """Kelly calculator uses trade history."""
        # Need enough trades (at least 5 with min_trades override)
        # Kelly uses MIN_TRADES_FOR_KELLY = 20 by default, but returns 0 without enough
        trades_with_wins_and_losses = [
            ("token1", "BUY", Decimal("0.50"), Decimal("10"), Decimal("5")),   # Win
            ("token1", "SELL", Decimal("0.55"), Decimal("10"), Decimal("3")),  # Win
            ("token1", "BUY", Decimal("0.52"), Decimal("10"), Decimal("-2")),  # Loss
            ("token1", "SELL", Decimal("0.48"), Decimal("10"), Decimal("4")),  # Win
            ("token1", "BUY", Decimal("0.50"), Decimal("10"), Decimal("-3")),  # Loss
        ]

        for token, side, price, size, pnl in trades_with_wins_and_losses:
            manager.record_trade(token, side, price, size, realized_pnl=pnl)

        # With only 5 trades, Kelly should return 0 (insufficient history)
        kelly = manager.get_kelly_from_history()
        assert kelly == 0.0  # Need 20+ trades by default

    def test_correlation_tracking(self, manager):
        """Correlation tracker records market prices."""
        # Record correlated price movements
        for i in range(25):
            manager.record_market_price("market_a", 0.50 + i * 0.01)
            manager.record_market_price("market_b", 0.50 + i * 0.01)

        # Should allow position in uncorrelated market
        can_add = manager.can_add_correlated_position(
            "market_a",
            Decimal("100"),
            {"market_c": Decimal("100")},  # Uncorrelated
        )
        assert can_add is True

    def test_trade_feeds_dynamic_limits(self, manager):
        """Trade P&L feeds into dynamic limits."""
        initial_limit = manager.get_dynamic_limit()

        # Record a big loss
        manager.record_trade(
            "token1", "BUY", Decimal("0.50"), Decimal("100"),
            realized_pnl=Decimal("-25")
        )

        # Dynamic limit should decrease due to drawdown
        new_limit = manager.get_dynamic_limit()
        assert new_limit < initial_limit


class TestRiskManagerPhase3Status:
    """Test that status reflects Phase 3 state correctly."""

    @pytest.fixture
    def manager(self):
        return RiskManager(enforce=False)

    def test_toxicity_in_status_updates(self, manager):
        """Status toxicity updates after trades."""
        status1 = manager.get_status()
        assert status1["toxicity"] == 0.0

        # Create toxic fills
        for i in range(5):
            manager.record_trade("token1", "BUY", Decimal("0.50"), Decimal("10"))
            manager.record_price_after_fill(i, Decimal("0.45"))

        status2 = manager.get_status()
        assert status2["toxicity"] > 0.5

    def test_adverse_response_in_status(self, manager):
        """Adverse selection response reflected in status."""
        # Initially healthy
        status1 = manager.get_status()
        assert status1["adverse_widen_spread"] is False
        assert status1["adverse_spread_mult"] == 1.0

        # Make toxic
        for i in range(10):
            manager.record_trade("token1", "BUY", Decimal("0.50"), Decimal("10"))
            manager.record_price_after_fill(i, Decimal("0.40"))  # Very adverse

        status2 = manager.get_status()
        assert status2["adverse_widen_spread"] is True
        assert status2["adverse_spread_mult"] > 1.0
