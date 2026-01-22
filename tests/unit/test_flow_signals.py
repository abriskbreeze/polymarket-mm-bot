"""Tests for FlowAnalyzer order flow signal generation."""

import pytest
from decimal import Decimal
from unittest.mock import patch
import time

from src.alpha.flow_signals import (
    FlowAnalyzer,
    FlowSignal,
    FlowState,
    TradeEvent,
)


class TestFlowAnalyzerBasic:
    """Basic FlowAnalyzer functionality tests."""

    def test_initialization(self):
        """Test analyzer initializes with correct defaults."""
        analyzer = FlowAnalyzer(token_id="test-token")
        assert analyzer.token_id == "test-token"
        assert analyzer.window_seconds == 60.0
        assert analyzer.decay_half_life == 30.0
        assert len(analyzer._trades) == 0

    def test_record_trade(self):
        """Test recording a trade event."""
        analyzer = FlowAnalyzer(token_id="test")
        analyzer.record_trade(
            price=Decimal("0.55"),
            size=Decimal("100"),
            side="BUY",
            is_aggressive=True,
        )
        assert len(analyzer._trades) == 1
        trade = analyzer._trades[0]
        assert trade.price == Decimal("0.55")
        assert trade.size == Decimal("100")
        assert trade.side == "BUY"
        assert trade.is_aggressive is True

    def test_side_normalization(self):
        """Test that side is normalized to uppercase."""
        analyzer = FlowAnalyzer(token_id="test")
        analyzer.record_trade(Decimal("1"), Decimal("1"), "buy")
        analyzer.record_trade(Decimal("1"), Decimal("1"), "Sell")
        assert analyzer._trades[0].side == "BUY"
        assert analyzer._trades[1].side == "SELL"


class TestFlowStateCalculation:
    """Tests for flow state calculation."""

    def test_empty_state(self):
        """Test state with no trades."""
        analyzer = FlowAnalyzer(token_id="test")
        state = analyzer.get_state()
        assert state.signal == FlowSignal.NEUTRAL
        assert state.buy_volume == Decimal("0")
        assert state.sell_volume == Decimal("0")
        assert state.trade_count == 0
        assert state.signal_strength == 0.0

    def test_neutral_with_few_trades(self):
        """Test that fewer than MIN_TRADES results in neutral signal."""
        analyzer = FlowAnalyzer(token_id="test")
        # Add only 4 trades (below MIN_TRADES=5)
        for _ in range(4):
            analyzer.record_trade(Decimal("1"), Decimal("100"), "BUY")
        state = analyzer.get_state()
        assert state.signal == FlowSignal.NEUTRAL
        assert state.trade_count == 4

    def test_bullish_signal(self):
        """Test bullish signal from buy imbalance."""
        analyzer = FlowAnalyzer(token_id="test")
        # Add 6 buys, 1 sell -> buy imbalance
        for _ in range(6):
            analyzer.record_trade(Decimal("1"), Decimal("100"), "BUY")
        analyzer.record_trade(Decimal("1"), Decimal("50"), "SELL")

        state = analyzer.get_state()
        assert state.signal in (FlowSignal.BULLISH, FlowSignal.STRONGLY_BULLISH)
        assert state.imbalance > 0

    def test_bearish_signal(self):
        """Test bearish signal from sell imbalance."""
        analyzer = FlowAnalyzer(token_id="test")
        # Add 6 sells, 1 buy -> sell imbalance
        for _ in range(6):
            analyzer.record_trade(Decimal("1"), Decimal("100"), "SELL")
        analyzer.record_trade(Decimal("1"), Decimal("50"), "BUY")

        state = analyzer.get_state()
        assert state.signal in (FlowSignal.BEARISH, FlowSignal.STRONGLY_BEARISH)
        assert state.imbalance < 0

    def test_strongly_bullish_threshold(self):
        """Test strongly bullish signal at 30%+ imbalance."""
        analyzer = FlowAnalyzer(token_id="test")
        # Need >30% imbalance for strongly bullish
        for _ in range(8):
            analyzer.record_trade(Decimal("1"), Decimal("100"), "BUY")
        for _ in range(2):
            analyzer.record_trade(Decimal("1"), Decimal("100"), "SELL")

        state = analyzer.get_state()
        # Should be strongly bullish (60% imbalance)
        assert state.signal == FlowSignal.STRONGLY_BULLISH

    def test_aggressive_weight(self):
        """Test that aggressive trades are weighted 2x."""
        # Equal size trades, but aggressive buy should dominate
        analyzer = FlowAnalyzer(token_id="test")
        for _ in range(5):
            analyzer.record_trade(Decimal("1"), Decimal("100"), "BUY", is_aggressive=True)
        for _ in range(5):
            analyzer.record_trade(Decimal("1"), Decimal("100"), "SELL", is_aggressive=False)

        state = analyzer.get_state()
        # Buy volume should be ~2x sell volume due to aggressive weight
        assert state.buy_volume > state.sell_volume
        assert state.aggressive_ratio == 0.5  # 5 of 10 trades aggressive


class TestTimeDecay:
    """Tests for time decay functionality."""

    def test_recent_trades_weighted_more(self):
        """Test that recent trades have more weight than old trades."""
        analyzer = FlowAnalyzer(token_id="test", window_seconds=60, decay_half_life=30)

        # Record old sell first, then recent buy
        with patch.object(time, 'time') as mock_time:
            mock_time.return_value = 1000.0
            analyzer.record_trade(Decimal("1"), Decimal("100"), "SELL")

            # Advance time by 30 seconds (one half-life)
            mock_time.return_value = 1030.0
            analyzer.record_trade(Decimal("1"), Decimal("100"), "BUY")

            # Add more trades to meet MIN_TRADES
            for _ in range(4):
                analyzer.record_trade(Decimal("1"), Decimal("10"), "BUY")

            # Get state at current time
            state = analyzer.get_state()

        # The recent buy should outweigh the older sell
        assert state.buy_volume > state.sell_volume

    def test_old_trades_excluded(self):
        """Test that trades outside window are excluded."""
        analyzer = FlowAnalyzer(token_id="test", window_seconds=60)

        with patch.object(time, 'time') as mock_time:
            mock_time.return_value = 1000.0
            analyzer.record_trade(Decimal("1"), Decimal("1000"), "SELL")

            # Advance past window
            mock_time.return_value = 1061.0
            for _ in range(5):
                analyzer.record_trade(Decimal("1"), Decimal("10"), "BUY")

            state = analyzer.get_state()

        # Old sell should not be counted
        assert state.sell_volume == Decimal("0")
        assert state.trade_count == 5


class TestShouldWidenSpread:
    """Tests for spread widening recommendation."""

    def test_should_widen_high_aggressive(self):
        """Test widening recommended when high aggressive ratio."""
        analyzer = FlowAnalyzer(token_id="test")
        # More than 50% aggressive and >10 trades
        for _ in range(8):
            analyzer.record_trade(Decimal("1"), Decimal("10"), "BUY", is_aggressive=True)
        for _ in range(5):
            analyzer.record_trade(Decimal("1"), Decimal("10"), "SELL", is_aggressive=False)

        assert analyzer.should_widen_spread() is True

    def test_should_not_widen_low_aggressive(self):
        """Test no widening when low aggressive ratio."""
        analyzer = FlowAnalyzer(token_id="test")
        for _ in range(11):
            analyzer.record_trade(Decimal("1"), Decimal("10"), "BUY", is_aggressive=False)

        assert analyzer.should_widen_spread() is False

    def test_should_not_widen_few_trades(self):
        """Test no widening with few trades even if aggressive."""
        analyzer = FlowAnalyzer(token_id="test")
        for _ in range(5):
            analyzer.record_trade(Decimal("1"), Decimal("10"), "BUY", is_aggressive=True)

        # Only 5 trades, need >10
        assert analyzer.should_widen_spread() is False


class TestRecommendedSkew:
    """Tests for recommended price skew."""

    def test_bullish_skew_positive(self):
        """Test that bullish imbalance gives positive skew."""
        analyzer = FlowAnalyzer(token_id="test")
        for _ in range(10):
            analyzer.record_trade(Decimal("1"), Decimal("100"), "BUY")

        state = analyzer.get_state()
        assert state.recommended_skew > 0

    def test_bearish_skew_negative(self):
        """Test that bearish imbalance gives negative skew."""
        analyzer = FlowAnalyzer(token_id="test")
        for _ in range(10):
            analyzer.record_trade(Decimal("1"), Decimal("100"), "SELL")

        state = analyzer.get_state()
        assert state.recommended_skew < 0

    def test_skew_bounded(self):
        """Test that skew is bounded to ~1 cent max."""
        analyzer = FlowAnalyzer(token_id="test")
        for _ in range(100):
            analyzer.record_trade(Decimal("1"), Decimal("1000"), "BUY")

        state = analyzer.get_state()
        # Max imbalance is 1.0, so max skew is 0.01
        assert abs(state.recommended_skew) <= Decimal("0.01")
