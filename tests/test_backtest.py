"""
TDD Tests for Backtesting Framework

Tests historical replay and strategy evaluation.
"""

import pytest
from decimal import Decimal
from datetime import datetime
from src.backtest.engine import BacktestEngine
from src.backtest.data import HistoricalData, OrderBookSnapshot


class TestHistoricalData:
    """Test historical data loading."""

    def test_load_order_book_snapshots(self):
        """Load order book snapshots from data."""
        data = HistoricalData()

        # Simulate loading
        data.add_snapshot(OrderBookSnapshot(
            timestamp=1000,
            token_id="token-1",
            best_bid=Decimal("0.50"),
            best_ask=Decimal("0.52"),
            bid_depth=Decimal("100"),
            ask_depth=Decimal("150"),
        ))

        assert len(data.snapshots) == 1

    def test_iterate_chronologically(self):
        """Data iterates in time order."""
        data = HistoricalData()

        data.add_snapshot(OrderBookSnapshot(timestamp=2000, token_id="t", best_bid=Decimal("0.51"), best_ask=Decimal("0.53"), bid_depth=Decimal("100"), ask_depth=Decimal("100")))
        data.add_snapshot(OrderBookSnapshot(timestamp=1000, token_id="t", best_bid=Decimal("0.50"), best_ask=Decimal("0.52"), bid_depth=Decimal("100"), ask_depth=Decimal("100")))

        snapshots = list(data.iterate())

        assert snapshots[0].timestamp == 1000
        assert snapshots[1].timestamp == 2000


class TestBacktestEngine:
    """Test backtest engine."""

    @pytest.fixture
    def engine(self):
        return BacktestEngine(initial_capital=Decimal("1000"))

    def test_run_backtest(self, engine):
        """Run basic backtest."""
        import math
        data = HistoricalData()
        # Create oscillating prices so orders can get filled
        for i in range(100):
            # Prices oscillate around 0.50 with tight spread
            offset = Decimal(str(math.sin(i * 0.2) * 0.02))
            data.add_snapshot(OrderBookSnapshot(
                timestamp=i * 1000,
                token_id="token-1",
                best_bid=Decimal("0.50") + offset,
                best_ask=Decimal("0.51") + offset,  # Tight 0.01 spread
                bid_depth=Decimal("100"),
                ask_depth=Decimal("100"),
            ))

        result = engine.run(data, strategy="simple_mm")

        assert result.total_trades > 0
        assert result.final_capital is not None

    def test_simulated_fills(self, engine):
        """Orders fill at appropriate prices."""
        # Place order
        order_id = engine.place_order(
            side="BUY",
            price=Decimal("0.50"),
            size=Decimal("10"),
        )

        # Simulate market touching our price
        engine.process_snapshot(OrderBookSnapshot(
            timestamp=1000,
            token_id="token-1",
            best_bid=Decimal("0.49"),
            best_ask=Decimal("0.50"),  # Ask at our bid - we get filled
            bid_depth=Decimal("100"),
            ask_depth=Decimal("100"),
        ))

        order = engine.get_order(order_id)
        assert order.is_filled

    def test_pnl_calculation(self, engine):
        """P&L calculated correctly."""
        # Buy at 0.50
        engine.place_order("BUY", Decimal("0.50"), Decimal("10"))
        engine.process_snapshot(OrderBookSnapshot(
            timestamp=1000, token_id="t",
            best_bid=Decimal("0.49"), best_ask=Decimal("0.50"),
            bid_depth=Decimal("100"), ask_depth=Decimal("100"),
        ))

        # Sell at 0.55
        engine.place_order("SELL", Decimal("0.55"), Decimal("10"))
        engine.process_snapshot(OrderBookSnapshot(
            timestamp=2000, token_id="t",
            best_bid=Decimal("0.55"), best_ask=Decimal("0.56"),
            bid_depth=Decimal("100"), ask_depth=Decimal("100"),
        ))

        # Should profit $0.50 (10 * 0.05)
        assert engine.realized_pnl == pytest.approx(Decimal("0.50"), rel=0.1)


class TestBacktestReport:
    """Test performance reporting."""

    def test_generate_report(self):
        """Generate performance report."""
        engine = BacktestEngine(initial_capital=Decimal("1000"))

        # Run some trades via a backtest
        data = HistoricalData()
        for i in range(10):
            data.add_snapshot(OrderBookSnapshot(
                timestamp=i * 1000,
                token_id="token-1",
                best_bid=Decimal("0.50"),
                best_ask=Decimal("0.52"),
                bid_depth=Decimal("100"),
                ask_depth=Decimal("100"),
            ))

        engine.run(data, strategy="simple_mm")
        report = engine.generate_report()

        assert "total_return" in report
        assert "sharpe_ratio" in report
        assert "max_drawdown" in report
        assert "win_rate" in report
