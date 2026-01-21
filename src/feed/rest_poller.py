"""
REST API poller for fallback when WebSocket is unavailable.

Internal component - use MarketFeed instead.
"""

import asyncio
from typing import List, Optional, Callable
from src.pricing import get_order_book
from src.feed.data_store import DataStore
from src.utils import setup_logging

logger = setup_logging()


class RESTPoller:
    """
    Polls REST API for order books when WebSocket is unavailable.

    Provides data continuity during WebSocket outages.
    """

    def __init__(
        self,
        data_store: DataStore,
        poll_interval: float = 2.0
    ):
        self._data_store = data_store
        self._poll_interval = poll_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._tokens: List[str] = []

        # Callbacks
        self.on_book_update: Optional[Callable[[str], None]] = None

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self, token_ids: List[str]):
        """Start polling."""
        self._tokens = token_ids.copy()
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(f"REST poller started for {len(token_ids)} tokens")

    async def stop(self):
        """Stop polling."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("REST poller stopped")

    def set_tokens(self, token_ids: List[str]):
        """Update tokens to poll."""
        self._tokens = token_ids.copy()

    async def _poll_loop(self):
        """Main polling loop."""
        while self._running:
            try:
                await self._poll_all()
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Poll error: {e}")
                await asyncio.sleep(self._poll_interval)

    async def _poll_all(self):
        """Poll all tokens."""
        for token_id in self._tokens:
            if not self._running:
                break
            try:
                await self._poll_token(token_id)
            except Exception as e:
                logger.debug(f"Error polling {token_id[:16]}...: {e}")

    async def _poll_token(self, token_id: str):
        """Poll a single token."""
        # Run sync function in executor to not block
        loop = asyncio.get_event_loop()
        book = await loop.run_in_executor(None, get_order_book, token_id)

        if book:
            self._data_store.update_book(
                token_id,
                [{'price': str(b.price), 'size': str(b.size)} for b in book.bids],
                [{'price': str(a.price), 'size': str(a.size)} for a in book.asks]
            )
            self._data_store.clear_gaps(token_id)

            if self.on_book_update:
                self.on_book_update(token_id)
