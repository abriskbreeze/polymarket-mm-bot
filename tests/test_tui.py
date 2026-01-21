"""
TUI component tests.

Run with: pytest tests/test_tui.py -v
"""

import pytest
from decimal import Decimal
from datetime import datetime


class TestBotState:
    """Test BotState dataclass."""

    def test_state_creation(self):
        """Test BotState can be created."""
        from src.tui.state import BotState, BotMode, BotStatus

        state = BotState()

        assert state.mode == BotMode.DRY_RUN
        assert state.status == BotStatus.STOPPED
        assert state.uptime_seconds == 0.0

        print("✓ BotState created")

    def test_state_with_market(self):
        """Test BotState with market data."""
        from src.tui.state import BotState, MarketState

        market = MarketState(
            token_id="test123",
            market_question="Test market?",
            best_bid=Decimal("0.45"),
            best_ask=Decimal("0.55"),
            midpoint=Decimal("0.50"),
            spread=Decimal("0.10"),
            spread_bps=20.0
        )

        state = BotState(market=market)

        assert state.market.best_bid == Decimal("0.45")
        assert state.market.spread_bps == 20.0

        print("✓ BotState with market data")

    def test_state_with_position(self):
        """Test position P&L calculations."""
        from src.tui.state import PositionState

        pos = PositionState(
            token_id="test123",
            position=Decimal("100"),
            unrealized_pnl=Decimal("10"),
            realized_pnl=Decimal("5")
        )

        assert pos.total_pnl == Decimal("15")

        print("✓ Position P&L calculations")

    def test_risk_state_percentages(self):
        """Test risk state percentage calculations."""
        from src.tui.state import RiskState

        risk = RiskState(
            daily_pnl=Decimal("-50"),
            daily_loss_limit=Decimal("100"),
            current_position=Decimal("75"),
            position_limit=Decimal("100")
        )

        assert risk.loss_pct == 50.0
        assert risk.position_pct == 75.0

        print("✓ Risk percentages calculated")

    def test_uptime_update(self):
        """Test uptime calculation."""
        from src.tui.state import BotState
        import time

        state = BotState(start_time=datetime.now())
        time.sleep(0.1)
        state.update_uptime()

        assert state.uptime_seconds >= 0.1

        print(f"✓ Uptime updated: {state.uptime_seconds:.2f}s")


class TestOrderState:
    """Test OrderState calculations."""

    def test_remaining_size(self):
        """Test remaining size calculation."""
        from src.tui.state import OrderState

        order = OrderState(
            order_id="test123",
            side="BUY",
            price=Decimal("0.50"),
            size=Decimal("100"),
            filled=Decimal("40")
        )

        assert order.remaining == Decimal("60")
        assert order.fill_pct == 40.0

        print("✓ Order remaining calculated")


class TestStateCollector:
    """Test StateCollector."""

    def test_collector_creation(self):
        """Test collector can be created."""
        from src.tui.collector import StateCollector

        collector = StateCollector()
        state = collector.collect()

        assert state is not None
        assert state.market is None  # No feed set

        print("✓ Collector created")

    def test_collector_status(self):
        """Test collector status tracking."""
        from src.tui.collector import StateCollector
        from src.tui.state import BotStatus

        collector = StateCollector()
        collector.set_status(BotStatus.RUNNING)

        state = collector.collect()

        assert state.status == BotStatus.RUNNING
        assert state.start_time is not None

        print("✓ Collector status tracked")

    def test_collector_counters(self):
        """Test collector quote counters."""
        from src.tui.collector import StateCollector

        collector = StateCollector()
        collector.record_quote_placed()
        collector.record_quote_placed()
        collector.record_quote_cancelled()

        state = collector.collect()

        assert state.quotes_placed == 2
        assert state.quotes_cancelled == 1

        print("✓ Collector counters work")

    def test_global_collector(self):
        """Test global collector instance."""
        from src.tui.collector import get_collector, reset_collector

        reset_collector()

        c1 = get_collector()
        c2 = get_collector()

        assert c1 is c2

        print("✓ Global collector singleton")


class TestTUIRenderer:
    """Test TUIRenderer."""

    def test_renderer_creation(self):
        """Test renderer can be created."""
        from src.tui.renderer import TUIRenderer

        renderer = TUIRenderer()

        assert renderer is not None
        assert renderer.refresh_rate == 4.0

        print("✓ Renderer created")

    def test_progress_bar(self):
        """Test progress bar generation."""
        from src.tui.renderer import TUIRenderer

        renderer = TUIRenderer()

        bar_50 = renderer._progress_bar(50, width=10)
        bar_90 = renderer._progress_bar(90, width=10, danger_threshold=80)

        assert "50%" in bar_50.plain
        assert "90%" in bar_90.plain

        print("✓ Progress bars generated")

    def test_render_empty_state(self):
        """Test rendering empty state doesn't crash."""
        from src.tui.renderer import TUIRenderer
        from src.tui.state import BotState

        renderer = TUIRenderer()
        state = BotState()

        # Should not raise
        layout = renderer._render(state)

        assert layout is not None

        print("✓ Empty state renders")

    def test_render_full_state(self):
        """Test rendering full state."""
        from src.tui.renderer import TUIRenderer
        from src.tui.state import (
            BotState, BotMode, BotStatus,
            MarketState, OrderState, PositionState,
            RiskState, FeedState
        )

        state = BotState(
            mode=BotMode.DRY_RUN,
            status=BotStatus.RUNNING,
            start_time=datetime.now(),
            market=MarketState(
                token_id="test",
                market_question="Will it work?",
                best_bid=Decimal("0.45"),
                best_ask=Decimal("0.55"),
                midpoint=Decimal("0.50"),
                spread=Decimal("0.10"),
                spread_bps=20.0
            ),
            bid_order=OrderState(
                order_id="bid123",
                side="BUY",
                price=Decimal("0.48"),
                size=Decimal("10")
            ),
            ask_order=OrderState(
                order_id="ask123",
                side="SELL",
                price=Decimal("0.52"),
                size=Decimal("10")
            ),
            position=PositionState(
                token_id="test",
                position=Decimal("50"),
                unrealized_pnl=Decimal("5"),
                realized_pnl=Decimal("10")
            ),
            risk=RiskState(
                daily_pnl=Decimal("-20"),
                daily_loss_limit=Decimal("100"),
                risk_status="OK"
            ),
            feed=FeedState(
                status="RUNNING",
                is_healthy=True,
                data_source="websocket"
            ),
            total_trades=5,
            quotes_placed=20,
            quotes_cancelled=8
        )

        renderer = TUIRenderer()
        layout = renderer._render(state)

        assert layout is not None

        print("✓ Full state renders")


class TestIntegration:
    """Integration tests."""

    def test_full_workflow(self):
        """Test full collector -> renderer workflow."""
        from src.tui.collector import StateCollector
        from src.tui.renderer import TUIRenderer
        from src.tui.state import BotStatus

        collector = StateCollector()
        renderer = TUIRenderer()

        collector.set_status(BotStatus.RUNNING)
        collector.set_market_info("test123", "Test question?")
        collector.record_quote_placed()

        state = collector.collect()
        layout = renderer._render(state)

        assert state.status == BotStatus.RUNNING
        assert state.quotes_placed == 1
        assert layout is not None

        print("✓ Full workflow works")
