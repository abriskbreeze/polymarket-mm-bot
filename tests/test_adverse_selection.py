"""
TDD Tests for Adverse Selection Detection

Tests detection of informed trading patterns.
"""

import pytest
from decimal import Decimal
import time
from src.risk.adverse_selection import AdverseSelectionDetector, FillAnalysis


class TestToxicityCalculation:
    """Test toxicity metric calculation."""

    @pytest.fixture
    def detector(self):
        return AdverseSelectionDetector(lookback_window=60)

    def test_no_toxicity_random_fills(self, detector):
        """Random fills have low toxicity."""
        # Record fills followed by random price moves (within threshold)
        detector.record_fill(
            price=Decimal("0.50"),
            side="BUY",
            size=Decimal("10"),
        )
        detector.record_price_after(
            fill_id=0,
            price_after=Decimal("0.51"),  # Price went up (good for buyer)
        )

        detector.record_fill(
            price=Decimal("0.52"),
            side="BUY",
            size=Decimal("10"),
        )
        detector.record_price_after(
            fill_id=1,
            price_after=Decimal("0.518"),  # Small drop within threshold (good)
        )

        toxicity = detector.get_toxicity()
        assert toxicity < 0.5  # Not systematically adverse

    def test_high_toxicity_informed_flow(self, detector):
        """Systematically adverse fills have high toxicity."""
        # Every buy is followed by price drop
        for i in range(10):
            detector.record_fill(
                price=Decimal("0.50"),
                side="BUY",
                size=Decimal("10"),
            )
            detector.record_price_after(
                fill_id=i,
                price_after=Decimal("0.48"),  # Always drops after our buy
            )

        toxicity = detector.get_toxicity()
        assert toxicity > 0.7  # High toxicity

    def test_toxicity_by_side(self, detector):
        """Can get toxicity separately for buys and sells."""
        # Buys are toxic
        for i in range(5):
            detector.record_fill(Decimal("0.50"), "BUY", Decimal("10"))
            detector.record_price_after(i, Decimal("0.48"))

        # Sells are fine
        for i in range(5, 10):
            detector.record_fill(Decimal("0.50"), "SELL", Decimal("10"))
            detector.record_price_after(i, Decimal("0.48"))  # Good for seller

        buy_toxicity = detector.get_toxicity(side="BUY")
        sell_toxicity = detector.get_toxicity(side="SELL")

        assert buy_toxicity > sell_toxicity


class TestAdverseSelectionResponse:
    """Test response recommendations."""

    @pytest.fixture
    def detector(self):
        return AdverseSelectionDetector()

    def test_widen_spread_when_toxic(self, detector):
        """Recommend widening spread in toxic conditions."""
        # Create toxic environment
        for i in range(10):
            detector.record_fill(Decimal("0.50"), "BUY", Decimal("10"))
            detector.record_price_after(i, Decimal("0.45"))

        response = detector.get_response()
        assert response.widen_spread is True
        assert response.spread_multiplier > 1.0

    def test_reduce_size_when_toxic(self, detector):
        """Recommend reducing size in toxic conditions."""
        for i in range(10):
            detector.record_fill(Decimal("0.50"), "BUY", Decimal("10"))
            detector.record_price_after(i, Decimal("0.45"))

        response = detector.get_response()
        assert response.size_multiplier < 1.0

    def test_no_change_when_healthy(self, detector):
        """No changes needed when fills are healthy."""
        # Mostly favorable fills (< 40% adverse)
        for i in range(10):
            detector.record_fill(Decimal("0.50"), "BUY", Decimal("10"))
            # 7 good fills, 3 bad (30% adverse)
            price_after = Decimal("0.52") if i < 7 else Decimal("0.48")
            detector.record_price_after(i, price_after)

        response = detector.get_response()
        assert response.spread_multiplier == pytest.approx(1.0, rel=0.1)


class TestFillAnalysis:
    """Test individual fill analysis."""

    @pytest.fixture
    def detector(self):
        return AdverseSelectionDetector()

    def test_analyze_fill_outcome(self, detector):
        """Analyze whether individual fill was adverse."""
        detector.record_fill(Decimal("0.50"), "BUY", Decimal("10"))
        detector.record_price_after(0, Decimal("0.45"))

        analysis = detector.analyze_fill(0)
        assert analysis.was_adverse is True
        assert analysis.adverse_move == Decimal("-0.05")

    def test_time_to_adverse_move(self, detector):
        """Track how quickly adverse moves happen."""
        detector.record_fill(Decimal("0.50"), "BUY", Decimal("10"))
        detector.record_price_after(0, Decimal("0.45"), seconds_after=5)

        analysis = detector.analyze_fill(0)
        assert analysis.seconds_to_adverse == 5
