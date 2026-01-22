"""
Multi-Market Maker Pool

Orchestrates multiple market makers with shared risk management.
"""

import asyncio
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Set
from src.strategy.market_maker import SmartMarketMaker
from src.risk.manager import get_risk_manager
from src.utils import setup_logging

logger = setup_logging()

@dataclass
class PoolConfig:
    """Pool configuration."""
    max_markets: int = 5
    total_capital: Decimal = Decimal("1000")
    max_total_exposure: Decimal = Decimal("500")
    allocation_method: str = "equal"  # or "scored"

@dataclass
class MarketState:
    """State for a single market."""
    token_id: str
    position: Decimal = Decimal("0")
    pnl: Decimal = Decimal("0")
    allocation: Decimal = Decimal("0")
    is_active: bool = False

class MarketMakerPool:
    """
    Manages multiple market makers with shared risk.

    Usage:
        pool = MarketMakerPool(total_capital=Decimal("1000"))

        # Add markets
        pool.add_market("token-1")
        pool.add_market("token-2")

        # Run all
        await pool.start()

        # Get state
        state = pool.get_state()
    """

    def __init__(
        self,
        max_markets: int = 5,
        total_capital: Decimal = Decimal("1000"),
        max_total_exposure: Decimal = Decimal("500"),
    ):
        self.config = PoolConfig(
            max_markets=max_markets,
            total_capital=total_capital,
            max_total_exposure=max_total_exposure,
        )

        self._markets: Dict[str, MarketState] = {}
        self._market_makers: Dict[str, SmartMarketMaker] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        self._risk = get_risk_manager()

    @property
    def market_count(self) -> int:
        return len(self._markets)

    @property
    def markets(self) -> List[str]:
        return list(self._markets.keys())

    @property
    def active_markets(self) -> Set[str]:
        return {k for k, v in self._markets.items() if v.is_active}

    @property
    def is_running(self) -> bool:
        return self._running

    def add_market(self, token_id: str):
        """Add a market to the pool."""
        if self.market_count >= self.config.max_markets:
            raise ValueError(f"Pool at max capacity ({self.config.max_markets})")

        if token_id in self._markets:
            return

        self._markets[token_id] = MarketState(token_id=token_id)
        self._recalculate_allocations()
        logger.info(f"Added market {token_id[:16]}... to pool")

    def remove_market(self, token_id: str):
        """Remove a market from the pool."""
        if token_id not in self._markets:
            return

        # Stop if running
        if token_id in self._tasks:
            self._tasks[token_id].cancel()
            del self._tasks[token_id]

        if token_id in self._market_makers:
            self._market_makers[token_id].stop()
            del self._market_makers[token_id]

        del self._markets[token_id]
        self._recalculate_allocations()
        logger.info(f"Removed market {token_id[:16]}... from pool")

    def get_allocation(self, token_id: str) -> Decimal:
        """Get capital allocation for a market."""
        state = self._markets.get(token_id)
        return state.allocation if state else Decimal("0")

    def get_max_position(self, token_id: str) -> Decimal:
        """Get maximum position for a market considering pool limits."""
        current_exposure = sum(
            abs(s.position) for k, s in self._markets.items() if k != token_id
        )
        remaining = self.config.max_total_exposure - current_exposure
        allocation = self.get_allocation(token_id)
        return min(remaining, allocation)

    def record_position(self, token_id: str, position: Decimal):
        """Record position update for a market."""
        if token_id in self._markets:
            self._markets[token_id].position = position

    def record_pnl(self, token_id: str, pnl: Decimal):
        """Record P&L for a market."""
        if token_id in self._markets:
            self._markets[token_id].pnl += pnl

    def get_total_pnl(self) -> Decimal:
        """Get total P&L across all markets."""
        return sum((s.pnl for s in self._markets.values()), Decimal("0"))

    def get_total_exposure(self) -> Decimal:
        """Get total exposure across all markets."""
        return sum((abs(s.position) for s in self._markets.values()), Decimal("0"))

    async def start(self):
        """Start all market makers."""
        if self._running:
            return

        self._running = True
        logger.info(f"Starting pool with {self.market_count} markets")

        for token_id in self._markets:
            try:
                mm = self._create_market_maker(token_id)
                self._market_makers[token_id] = mm

                task = asyncio.create_task(
                    self._run_market(token_id, mm),
                    name=f"mm-{token_id[:8]}"
                )
                self._tasks[token_id] = task
                self._markets[token_id].is_active = True

            except Exception as e:
                logger.error(f"Failed to start {token_id[:16]}: {e}")

    async def stop(self):
        """Stop all market makers."""
        if not self._running:
            return

        logger.info("Stopping pool...")
        self._running = False

        # Stop all market makers
        for token_id, mm in self._market_makers.items():
            try:
                mm.stop()
            except Exception as e:
                logger.error(f"Error stopping {token_id[:16]}: {e}")

        # Cancel all tasks
        for task in self._tasks.values():
            task.cancel()

        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)

        self._tasks.clear()
        self._market_makers.clear()

        for state in self._markets.values():
            state.is_active = False

        logger.info("Pool stopped")

    def get_state(self) -> dict:
        """Get aggregate pool state for TUI."""
        return {
            "market_count": self.market_count,
            "active_count": len(self.active_markets),
            "markets": [self.get_market_state(t) for t in self._markets],
            "total_pnl": self.get_total_pnl(),
            "total_exposure": self.get_total_exposure(),
            "max_exposure": self.config.max_total_exposure,
            "is_running": self._running,
        }

    def get_market_state(self, token_id: str) -> Optional[dict]:
        """Get state for individual market."""
        state = self._markets.get(token_id)
        if not state:
            return None

        mm = self._market_makers.get(token_id)
        mm_state = mm.get_state_for_tui() if mm else {}

        return {
            "token_id": token_id,
            "position": state.position,
            "pnl": state.pnl,
            "allocation": state.allocation,
            "is_active": state.is_active,
            **mm_state,
        }

    def _create_market_maker(self, token_id: str) -> SmartMarketMaker:
        """Create market maker for a token."""
        allocation = self.get_allocation(token_id)

        return SmartMarketMaker(
            token_id=token_id,
            position_limit=allocation,
            size=min(Decimal("10"), allocation / 5),
        )

    async def _run_market(self, token_id: str, mm: SmartMarketMaker):
        """Run a single market maker with error handling."""
        try:
            await mm.run(install_signals=False)
        except asyncio.CancelledError:
            logger.info(f"Market {token_id[:16]} cancelled")
        except Exception as e:
            logger.error(f"Market {token_id[:16]} error: {e}")
            self._markets[token_id].is_active = False
        finally:
            if token_id in self._market_makers:
                del self._market_makers[token_id]

    def _recalculate_allocations(self):
        """Recalculate capital allocations."""
        if not self._markets:
            return

        # Simple equal allocation for now
        per_market = self.config.total_capital / len(self._markets)

        for state in self._markets.values():
            state.allocation = per_market
