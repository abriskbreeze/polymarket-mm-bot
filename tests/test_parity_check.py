"""TDD Tests for YES/NO Parity Check."""

import pytest
from decimal import Decimal
from src.strategy.parity import check_parity, ParityStatus


class TestParityCheck:
    """Test YES/NO parity validation."""

    def test_fair_pricing_passes(self):
        """Fair pricing (sum ~$1) passes check."""
        status = check_parity(
            yes_price=Decimal("0.55"),
            no_price=Decimal("0.45"),
        )
        assert status == ParityStatus.FAIR

    def test_overpriced_detected(self):
        """Overpriced (sum > $1.02) detected."""
        status = check_parity(
            yes_price=Decimal("0.55"),
            no_price=Decimal("0.48"),  # Sum = 1.03
        )
        assert status == ParityStatus.OVERPRICED

    def test_underpriced_detected(self):
        """Underpriced (sum < $0.98) detected."""
        status = check_parity(
            yes_price=Decimal("0.50"),
            no_price=Decimal("0.47"),  # Sum = 0.97
        )
        assert status == ParityStatus.UNDERPRICED

    def test_near_arbitrage_detected(self):
        """Near-arbitrage (sum 1.01-1.02) detected."""
        status = check_parity(
            yes_price=Decimal("0.53"),
            no_price=Decimal("0.48"),  # Sum = 1.01
        )
        assert status == ParityStatus.NEAR_ARBITRAGE

    def test_custom_tolerance(self):
        """Custom tolerance works correctly."""
        # With tight tolerance, 1.015 is overpriced
        status = check_parity(
            yes_price=Decimal("0.52"),
            no_price=Decimal("0.495"),  # Sum = 1.015
            tolerance=Decimal("0.01"),
        )
        assert status == ParityStatus.OVERPRICED

    def test_exactly_one_dollar_is_fair(self):
        """Exactly $1.00 is fair."""
        status = check_parity(
            yes_price=Decimal("0.50"),
            no_price=Decimal("0.50"),
        )
        assert status == ParityStatus.FAIR
