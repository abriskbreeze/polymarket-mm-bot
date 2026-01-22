"""
TDD Tests for Kelly Criterion Sizing

Tests Kelly formula implementation and fractional Kelly.
"""

import pytest
from decimal import Decimal
from src.risk.kelly import KellyCalculator


class TestKellyFormula:
    """Test basic Kelly calculation."""

    @pytest.fixture
    def kelly(self):
        # Use full Kelly and high max to test pure formula
        return KellyCalculator(fraction=1.0, max_position_pct=1.0)

    def test_kelly_50_50_no_edge(self, kelly):
        """50/50 with even payoff = 0 Kelly."""
        fraction = kelly.calculate(
            win_rate=0.5,
            win_loss_ratio=1.0,
        )
        assert fraction == pytest.approx(0.0, abs=0.01)

    def test_kelly_60_40_even_payoff(self, kelly):
        """60% win rate, even payoff = 20% Kelly."""
        # f* = (p*b - q) / b = (0.6*1 - 0.4) / 1 = 0.2
        fraction = kelly.calculate(
            win_rate=0.6,
            win_loss_ratio=1.0,
        )
        assert fraction == pytest.approx(0.2, abs=0.01)

    def test_kelly_better_odds(self, kelly):
        """Better win/loss ratio increases Kelly."""
        # 50% win rate but 2:1 payoff
        # f* = (0.5*2 - 0.5) / 2 = 0.25
        fraction = kelly.calculate(
            win_rate=0.5,
            win_loss_ratio=2.0,
        )
        assert fraction == pytest.approx(0.25, abs=0.01)

    def test_kelly_negative_edge(self, kelly):
        """Negative edge returns 0 (don't bet)."""
        fraction = kelly.calculate(
            win_rate=0.4,
            win_loss_ratio=1.0,
        )
        assert fraction == 0.0


class TestFractionalKelly:
    """Test fractional Kelly for safety."""

    @pytest.fixture
    def kelly(self):
        return KellyCalculator(fraction=0.25)  # Quarter Kelly

    def test_fractional_reduces_sizing(self, kelly):
        """Fractional Kelly reduces position size."""
        # Full Kelly would be 20%
        fraction = kelly.calculate(
            win_rate=0.6,
            win_loss_ratio=1.0,
        )
        # Quarter Kelly = 5%
        assert fraction == pytest.approx(0.05, abs=0.01)

    def test_configurable_fraction(self):
        """Kelly fraction is configurable."""
        half_kelly = KellyCalculator(fraction=0.5)
        result = half_kelly.calculate(win_rate=0.6, win_loss_ratio=1.0)
        assert result == pytest.approx(0.1, abs=0.01)


class TestKellyFromHistory:
    """Test Kelly calculation from trade history."""

    @pytest.fixture
    def kelly(self):
        return KellyCalculator(max_position_pct=1.0)

    def test_kelly_from_trades(self, kelly):
        """Calculate Kelly from trade history."""
        trades = [
            {"pnl": Decimal("10")},   # Win
            {"pnl": Decimal("15")},   # Win
            {"pnl": Decimal("-8")},   # Loss
            {"pnl": Decimal("12")},   # Win
            {"pnl": Decimal("-10")},  # Loss
        ]

        fraction = kelly.calculate_from_trades(trades, min_trades=5)

        # 3 wins / 5 trades = 60% win rate
        # Avg win = 12.33, avg loss = 9 -> ratio ~1.37
        assert fraction > 0  # Should be positive

    def test_insufficient_history(self, kelly):
        """Return 0 with insufficient trade history."""
        trades = [{"pnl": Decimal("10")}]  # Only 1 trade

        fraction = kelly.calculate_from_trades(trades, min_trades=10)
        assert fraction == 0.0


class TestKellySizing:
    """Test position sizing from Kelly."""

    def test_size_from_kelly(self):
        """Convert Kelly fraction to position size."""
        kelly = KellyCalculator(fraction=0.25)
        kelly.set_bankroll(Decimal("10000"))

        size = kelly.get_position_size(
            win_rate=0.6,
            win_loss_ratio=1.0,
            price=Decimal("0.50"),
        )

        # 25% Kelly * 20% full Kelly = 5% of bankroll = $500
        # At price 0.50, that's 1000 shares
        assert size == Decimal("1000")
