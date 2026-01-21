"""
Mock MarketFeed for testing without network access.
"""

import asyncio
import time
from typing import List, Optional, Callable, Dict, Any
from src.models import OrderBook, PriceLevel
from src.feed.feed import FeedState


class MockMarketFeed:
    """
    Mock MarketFeed for unit testing.

    Allows injecting data and simulating various conditions
    without network access.

    Usage:
        feed = MockMarketFeed()
        await feed.start(["token1"])

        # Inject data
        feed.set_book("token1", [(0.50, 100)], [(0.55, 200)])

        # Use normally
        mid = feed.get_midpoint("token1")  # Returns 0.525
    """

    def __init__(self):
        self._state = FeedState.STOPPED
        self._tokens: List[str] = []
        self._books: Dict[str, OrderBook] = {}
        self._prices: Dict[str, float] = {}
        self._healthy = True
        self._data_source = "mock"

        # Callbacks
        self.on_price_change: Optional[Callable] = None
        self.on_book_update: Optional[Callable] = None
        self.on_trade: Optional[Callable] = None
        self.on_state_change: Optional[Callable[[FeedState], None]] = None

    # === Lifecycle ===

    async def start(self, token_ids: List[str]) -> bool:
        self._tokens = token_ids.copy()
        self._state = FeedState.RUNNING
        if self.on_state_change:
            self.on_state_change(self._state)
        return True

    async def stop(self):
        self._state = FeedState.STOPPED
        self._tokens.clear()
        self._books.clear()
        self._prices.clear()
        if self.on_state_change:
            self.on_state_change(self._state)

    async def reset(self):
        await self.stop()

    # === State ===

    @property
    def state(self) -> FeedState:
        return self._state

    @property
    def is_healthy(self) -> bool:
        return self._state == FeedState.RUNNING and self._healthy

    @property
    def data_source(self) -> str:
        return self._data_source

    # === Data Access ===

    def get_midpoint(self, token_id: str) -> Optional[float]:
        book = self._books.get(token_id)
        return book.midpoint if book else None

    def get_order_book(self, token_id: str) -> Optional[OrderBook]:
        return self._books.get(token_id)

    def get_spread(self, token_id: str) -> Optional[float]:
        book = self._books.get(token_id)
        return book.spread if book else None

    def get_best_bid(self, token_id: str) -> Optional[float]:
        book = self._books.get(token_id)
        return book.best_bid if book else None

    def get_best_ask(self, token_id: str) -> Optional[float]:
        book = self._books.get(token_id)
        return book.best_ask if book else None

    # === Test Helpers ===

    def set_book(
        self,
        token_id: str,
        bids: List[tuple],  # [(price, size), ...]
        asks: List[tuple]
    ):
        """Set order book for a token."""
        self._books[token_id] = OrderBook(
            token_id=token_id,
            bids=[PriceLevel(price=p, size=s) for p, s in bids],
            asks=[PriceLevel(price=p, size=s) for p, s in asks]
        )

        if self.on_book_update:
            asyncio.create_task(self._invoke_callback(
                self.on_book_update,
                {'event_type': 'book', 'asset_id': token_id}
            ))

    def set_price(self, token_id: str, price: float):
        """Set last price for a token."""
        self._prices[token_id] = price

        if self.on_price_change:
            asyncio.create_task(self._invoke_callback(
                self.on_price_change,
                {'event_type': 'price_change', 'asset_id': token_id, 'price': str(price)}
            ))

    def set_healthy(self, healthy: bool):
        """Set health status."""
        self._healthy = healthy

    def set_state(self, state: FeedState):
        """Set state directly."""
        self._state = state
        if self.on_state_change:
            self.on_state_change(state)

    async def _invoke_callback(self, callback: Callable, data: Any):
        if asyncio.iscoroutinefunction(callback):
            await callback(data)
        else:
            callback(data)
