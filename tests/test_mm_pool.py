"""
TDD Tests for Multi-Market Pool

Tests market maker pool orchestration.
"""

import pytest
import asyncio
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch
from src.strategy.pool import MarketMakerPool, PoolConfig


class TestPoolCreation:
    """Test pool creation and management."""

    def test_create_empty_pool(self):
        """Create pool with no markets."""
        pool = MarketMakerPool()
        assert pool.market_count == 0
        assert pool.is_running is False

    def test_add_market(self):
        """Add market to pool."""
        pool = MarketMakerPool()
        pool.add_market("token-123")

        assert pool.market_count == 1
        assert "token-123" in pool.markets

    def test_remove_market(self):
        """Remove market from pool."""
        pool = MarketMakerPool()
        pool.add_market("token-123")
        pool.remove_market("token-123")

        assert pool.market_count == 0

    def test_max_markets_enforced(self):
        """Pool enforces maximum market count."""
        pool = MarketMakerPool(max_markets=2)
        pool.add_market("token-1")
        pool.add_market("token-2")

        with pytest.raises(ValueError):
            pool.add_market("token-3")


class TestPoolRiskManagement:
    """Test portfolio-level risk management."""

    @pytest.fixture
    def pool(self):
        return MarketMakerPool(
            total_capital=Decimal("1000"),
            max_total_exposure=Decimal("500"),
        )

    def test_capital_allocation(self, pool):
        """Capital is allocated across markets."""
        pool.add_market("token-1")
        pool.add_market("token-2")

        alloc = pool.get_allocation("token-1")

        # With 2 markets, each gets roughly half
        assert alloc > Decimal("200")
        assert alloc < Decimal("600")

    def test_exposure_limit_shared(self, pool):
        """Total exposure limit is shared."""
        pool.add_market("token-1")
        pool.add_market("token-2")

        # After token-1 uses 300 exposure
        pool.record_position("token-1", Decimal("300"))

        # Token-2 can only use remaining 200
        max_for_2 = pool.get_max_position("token-2")
        assert max_for_2 <= Decimal("200")

    def test_pnl_aggregation(self, pool):
        """P&L is aggregated across markets."""
        pool.add_market("token-1")
        pool.add_market("token-2")

        pool.record_pnl("token-1", Decimal("50"))
        pool.record_pnl("token-2", Decimal("-20"))

        total_pnl = pool.get_total_pnl()
        assert total_pnl == Decimal("30")


class TestPoolLifecycle:
    """Test pool start/stop lifecycle."""

    @pytest.fixture
    def pool(self):
        return MarketMakerPool()

    @pytest.mark.asyncio
    async def test_start_all_markets(self, pool):
        """Starting pool starts all market makers."""
        pool.add_market("token-1")
        pool.add_market("token-2")

        with patch.object(pool, '_create_market_maker') as mock_create:
            mock_mm = AsyncMock()
            mock_create.return_value = mock_mm

            await pool.start()

            assert pool.is_running
            assert mock_create.call_count == 2

    @pytest.mark.asyncio
    async def test_stop_all_markets(self, pool):
        """Stopping pool stops all market makers."""
        pool.add_market("token-1")

        with patch.object(pool, '_create_market_maker') as mock_create:
            mock_mm = Mock()
            mock_mm.run = AsyncMock()
            mock_mm.stop = Mock()
            mock_create.return_value = mock_mm

            await pool.start()
            await pool.stop()

            assert pool.is_running is False
            mock_mm.stop.assert_called()

    @pytest.mark.asyncio
    async def test_graceful_market_failure(self, pool):
        """Pool handles individual market failure gracefully."""
        pool.add_market("token-1")
        pool.add_market("token-2")

        # Token-1 will fail
        async def fail_run():
            raise Exception("Market error")

        with patch.object(pool, '_create_market_maker') as mock_create:
            mock_mm1 = Mock()
            mock_mm1.run = fail_run
            mock_mm1.stop = Mock()

            mock_mm2 = AsyncMock()
            mock_mm2.stop = Mock()

            mock_create.side_effect = [mock_mm1, mock_mm2]

            # Should not crash entire pool
            await pool.start()

            # Give tasks time to run
            await asyncio.sleep(0.1)

            # Token-2 should still be running
            assert "token-2" in pool.active_markets


class TestPoolState:
    """Test pool state for TUI."""

    @pytest.fixture
    def pool(self):
        pool = MarketMakerPool()
        pool.add_market("token-1")
        pool.add_market("token-2")
        return pool

    def test_get_pool_state(self, pool):
        """Get aggregate state for TUI."""
        state = pool.get_state()

        assert "markets" in state
        assert "total_pnl" in state
        assert "total_exposure" in state
        assert len(state["markets"]) == 2

    def test_get_market_state(self, pool):
        """Get individual market state."""
        state = pool.get_market_state("token-1")

        assert state is not None
        assert "token_id" in state
