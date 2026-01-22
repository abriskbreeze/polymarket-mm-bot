"""
TDD Tests for Maker/Taker Classification

Ensures orders are placed to qualify as maker.
"""

import pytest
from decimal import Decimal
from src.strategy.maker_checker import MakerChecker


class TestMakerClassification:
    """Test order classification as maker/taker."""

    @pytest.fixture
    def checker(self):
        return MakerChecker()

    def test_bid_below_ask_is_maker(self, checker):
        """Bid below best ask is maker."""
        is_maker = checker.would_be_maker(
            side="BUY",
            price=Decimal("0.50"),
            best_ask=Decimal("0.52"),
        )
        assert is_maker is True

    def test_bid_at_ask_is_taker(self, checker):
        """Bid at or above best ask is taker."""
        is_maker = checker.would_be_maker(
            side="BUY",
            price=Decimal("0.52"),
            best_ask=Decimal("0.52"),
        )
        assert is_maker is False

    def test_ask_above_bid_is_maker(self, checker):
        """Ask above best bid is maker."""
        is_maker = checker.would_be_maker(
            side="SELL",
            price=Decimal("0.55"),
            best_bid=Decimal("0.53"),
        )
        assert is_maker is True

    def test_adjust_to_maker(self, checker):
        """Adjust price to ensure maker status."""
        adjusted = checker.adjust_to_maker(
            side="BUY",
            price=Decimal("0.52"),
            best_ask=Decimal("0.52"),
        )

        # Should be below the ask
        assert adjusted < Decimal("0.52")
