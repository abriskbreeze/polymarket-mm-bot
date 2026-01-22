"""TDD Tests for Per-Market P&L Tracking."""

import pytest
from decimal import Decimal
from src.risk.market_pnl import MarketPnLTracker


class TestMarketPnL:
    """Test market P&L tracking."""

    @pytest.fixture
    def tracker(self):
        return MarketPnLTracker()

    def test_record_trade(self, tracker):
        """Record trade updates P&L."""
        tracker.record_trade(
            market_id="market-1",
            side="BUY",
            price=Decimal("0.50"),
            size=Decimal("10"),
        )

        stats = tracker.get_market_stats("market-1")
        assert stats.trade_count == 1
        assert stats.total_bought == Decimal("10")

    def test_calculate_realized_pnl(self, tracker):
        """Calculate realized P&L from round trips."""
        # Buy at 0.50
        tracker.record_trade("m1", "BUY", Decimal("0.50"), Decimal("10"))
        # Sell at 0.55
        tracker.record_trade("m1", "SELL", Decimal("0.55"), Decimal("10"))

        stats = tracker.get_market_stats("m1")
        # Profit = 10 * (0.55 - 0.50) = $0.50
        assert stats.realized_pnl == Decimal("0.50")

    def test_win_rate_calculation(self, tracker):
        """Calculate win rate correctly."""
        # 2 wins
        tracker.record_trade("m1", "BUY", Decimal("0.50"), Decimal("10"))
        tracker.record_trade("m1", "SELL", Decimal("0.55"), Decimal("10"))  # +$0.50

        tracker.record_trade("m1", "BUY", Decimal("0.45"), Decimal("10"))
        tracker.record_trade("m1", "SELL", Decimal("0.48"), Decimal("10"))  # +$0.30

        # 1 loss
        tracker.record_trade("m1", "BUY", Decimal("0.60"), Decimal("10"))
        tracker.record_trade("m1", "SELL", Decimal("0.55"), Decimal("10"))  # -$0.50

        stats = tracker.get_market_stats("m1")
        assert stats.win_rate == pytest.approx(0.67, rel=0.1)  # 2/3

    def test_best_worst_markets(self, tracker):
        """Identify best and worst markets."""
        # Good market
        tracker.record_trade("good", "BUY", Decimal("0.50"), Decimal("10"))
        tracker.record_trade("good", "SELL", Decimal("0.60"), Decimal("10"))  # +$1

        # Bad market
        tracker.record_trade("bad", "BUY", Decimal("0.50"), Decimal("10"))
        tracker.record_trade("bad", "SELL", Decimal("0.40"), Decimal("10"))  # -$1

        best = tracker.get_best_markets(top_n=1)
        worst = tracker.get_worst_markets(top_n=1)

        assert best[0].market_id == "good"
        assert worst[0].market_id == "bad"

    def test_total_pnl_across_markets(self, tracker):
        """Total P&L sums across all markets."""
        # Market 1: +$0.50
        tracker.record_trade("m1", "BUY", Decimal("0.50"), Decimal("10"))
        tracker.record_trade("m1", "SELL", Decimal("0.55"), Decimal("10"))

        # Market 2: +$0.30
        tracker.record_trade("m2", "BUY", Decimal("0.40"), Decimal("10"))
        tracker.record_trade("m2", "SELL", Decimal("0.43"), Decimal("10"))

        total = tracker.get_total_pnl()
        assert total == Decimal("0.80")

    def test_partial_fills_tracked(self, tracker):
        """Partial fills are tracked correctly."""
        # Buy 20
        tracker.record_trade("m1", "BUY", Decimal("0.50"), Decimal("20"))
        # Sell 10 at profit
        tracker.record_trade("m1", "SELL", Decimal("0.55"), Decimal("10"))

        stats = tracker.get_market_stats("m1")
        assert stats.realized_pnl == Decimal("0.50")  # 10 * 0.05
        # Still have 10 open

    def test_unknown_market_returns_none(self, tracker):
        """Unknown market returns None."""
        assert tracker.get_market_stats("nonexistent") is None
