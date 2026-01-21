"""
MarketFeed - Simple interface for real-time market data.

This is the main public interface. Use this, not the internal components.
"""

import json
import asyncio
from enum import Enum, auto
from typing import List, Optional, Callable, Dict, Any

from src.models import OrderBook
from src.feed.data_store import DataStore
from src.feed.websocket_conn import WebSocketConnection
from src.feed.rest_poller import RESTPoller
from src.utils import setup_logging

logger = setup_logging()


class FeedState(Enum):
    """Feed states - kept simple."""
    STOPPED = auto()   # Not running
    STARTING = auto()  # Connecting/subscribing
    RUNNING = auto()   # Receiving data
    ERROR = auto()     # Failed, needs reset


class MarketFeed:
    """
    Simple interface for real-time market data.

    Features:
    - Automatic WebSocket connection and reconnection
    - Automatic REST fallback when WebSocket is unhealthy
    - Simple health check: is_healthy
    - Non-blocking callbacks via async queue

    Usage:
        feed = MarketFeed()
        feed.on_book_update = my_handler  # Optional

        await feed.start(["token1", "token2"])

        if feed.is_healthy:
            mid = feed.get_midpoint("token1")

        await feed.stop()
    """

    def __init__(
        self,
        stale_threshold: float = 30.0,
        rest_poll_interval: float = 2.0,
        rest_recovery_delay: float = 30.0
    ):
        """
        Args:
            stale_threshold: Seconds without data before considered stale
            rest_poll_interval: How often REST fallback polls
            rest_recovery_delay: How long WS must be healthy before stopping REST
        """
        self._stale_threshold = stale_threshold
        self._rest_recovery_delay = rest_recovery_delay

        # State
        self._state = FeedState.STOPPED
        self._tokens: List[str] = []
        self._data_source = "none"

        # Components
        self._data_store = DataStore(stale_threshold=stale_threshold)
        self._ws = WebSocketConnection()
        self._rest = RESTPoller(self._data_store, poll_interval=rest_poll_interval)

        # Message queue for non-blocking callbacks
        self._message_queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self._queue_task: Optional[asyncio.Task] = None

        # Health monitor
        self._health_task: Optional[asyncio.Task] = None
        self._ws_healthy_since: float = 0

        # User callbacks - simple attributes instead of properties
        self.on_price_change: Optional[Callable] = None
        self.on_book_update: Optional[Callable] = None
        self.on_trade: Optional[Callable] = None
        self.on_state_change: Optional[Callable[[FeedState], None]] = None

        # Wire up internal callbacks
        self._ws.on_message = self._handle_ws_message
        self._ws.on_connect = self._handle_ws_connect
        self._ws.on_disconnect = self._handle_ws_disconnect
        self._ws.on_max_retries = self._handle_max_retries

    # === Lifecycle ===

    async def start(self, token_ids: List[str]) -> bool:
        """
        Start receiving data for these tokens.

        Returns True when successfully receiving data.
        """
        if self._state not in (FeedState.STOPPED, FeedState.ERROR):
            logger.warning(f"Cannot start from state {self._state.name}")
            return False

        self._tokens = token_ids.copy()
        self._set_state(FeedState.STARTING)

        # Register tokens in data store
        for token_id in token_ids:
            self._data_store.register_token(token_id)

        # Start message queue processor
        self._queue_task = asyncio.create_task(self._process_queue())

        # Try WebSocket first
        ws_connected = await self._ws.connect()

        if ws_connected:
            ws_subscribed = await self._ws.subscribe(token_ids)
            if ws_subscribed:
                self._data_source = "websocket"
                self._set_state(FeedState.RUNNING)

                # Start health monitor
                self._health_task = asyncio.create_task(self._health_monitor())

                return True

        # WebSocket failed, start REST fallback
        logger.info("WebSocket unavailable, starting REST fallback")
        await self._rest.start(token_ids)
        self._data_source = "rest"
        self._set_state(FeedState.RUNNING)

        # Start health monitor
        self._health_task = asyncio.create_task(self._health_monitor())

        return True

    async def stop(self):
        """Stop receiving data and disconnect."""
        logger.info("Stopping MarketFeed")

        # Stop health monitor
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass

        # Stop queue processor
        if self._queue_task:
            self._queue_task.cancel()
            try:
                await self._queue_task
            except asyncio.CancelledError:
                pass

        # Disconnect
        await self._ws.disconnect()
        await self._rest.stop()

        # Clear data
        self._data_store.clear()
        self._tokens.clear()
        self._data_source = "none"

        self._set_state(FeedState.STOPPED)

    async def reset(self):
        """Reset from ERROR state to STOPPED."""
        if self._state != FeedState.ERROR:
            logger.warning(f"Cannot reset from state {self._state.name}")
            return

        await self.stop()

    # === State ===

    @property
    def state(self) -> FeedState:
        """Current state."""
        return self._state

    @property
    def is_healthy(self) -> bool:
        """
        Is the data reliable enough to trade on?

        Returns True only when:
        - State is RUNNING
        - Data is fresh (received recently)
        - No unresolved sequence gaps
        """
        if self._state != FeedState.RUNNING:
            return False

        # Check if we've received ANY message recently (heartbeat)
        if self._data_store.seconds_since_any_message() > 45:
            return False

        if not self._data_store.all_fresh():
            return False

        # Gaps are OK if we're on REST (it resyncs automatically)
        if self._data_source == "websocket" and self._data_store.has_gaps():
            return False

        return True

    @property
    def data_source(self) -> str:
        """Current data source: 'websocket', 'rest', or 'none'."""
        return self._data_source

    # === Data Access ===

    def get_midpoint(self, token_id: str) -> Optional[float]:
        """Get current midpoint price."""
        return self._data_store.get_midpoint(token_id)

    def get_order_book(self, token_id: str) -> Optional[OrderBook]:
        """Get current order book."""
        return self._data_store.get_order_book(token_id)

    def get_spread(self, token_id: str) -> Optional[float]:
        """Get current bid-ask spread."""
        return self._data_store.get_spread(token_id)

    def get_best_bid(self, token_id: str) -> Optional[float]:
        """Get best bid price."""
        return self._data_store.get_best_bid(token_id)

    def get_best_ask(self, token_id: str) -> Optional[float]:
        """Get best ask price."""
        return self._data_store.get_best_ask(token_id)

    # === Callbacks ===

    # === Internal Methods ===

    def _set_state(self, new_state: FeedState):
        """Update state and notify."""
        old_state = self._state
        self._state = new_state

        if old_state != new_state:
            logger.info(f"State: {old_state.name} -> {new_state.name}")
            if self.on_state_change:
                self.on_state_change(new_state)

    def _handle_ws_message(self, raw_message: str):
        """Handle raw WebSocket message."""
        try:
            # Queue for async processing (non-blocking)
            self._message_queue.put_nowait(raw_message)
        except asyncio.QueueFull:
            logger.warning("Message queue full, dropping message")

    def _handle_ws_connect(self):
        """Handle WebSocket connected."""
        logger.debug("WebSocket connected callback")

        # Re-subscribe if we have tokens
        if self._tokens and self._state == FeedState.RUNNING:
            asyncio.create_task(self._resubscribe())

    async def _resubscribe(self):
        """Re-subscribe after reconnection."""
        await self._ws.subscribe(self._tokens)
        self._data_source = "websocket"

    def _handle_ws_disconnect(self):
        """Handle WebSocket disconnected."""
        logger.debug("WebSocket disconnected callback")

    def _handle_max_retries(self):
        """Handle max reconnection attempts exceeded."""
        logger.error("WebSocket max retries exceeded")

        # If REST is running, we're still OK (degraded)
        if self._rest.is_running:
            logger.info("Continuing with REST fallback")
            self._data_source = "rest"
        else:
            # No data source available
            self._set_state(FeedState.ERROR)

    async def _process_queue(self):
        """Process messages from queue (async worker)."""
        while True:
            try:
                raw_message = await self._message_queue.get()
                await self._process_message(raw_message)
                self._message_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Queue processing error: {e}")

    async def _process_message(self, raw_message: str):
        """Process a single message."""
        self._data_store.record_message_received()

        try:
            data = json.loads(raw_message)
        except json.JSONDecodeError:
            return

        event_type = data.get('event_type')
        token_id = data.get('asset_id')

        if not event_type:
            return

        # Check sequence
        seq = data.get('sequence')
        if token_id and seq is not None:
            self._data_store.check_sequence(token_id, seq)

        # Update data store and invoke callbacks
        if event_type == 'book':
            self._data_store.update_book(
                token_id,
                data.get('bids', []),
                data.get('asks', []),
                data.get('timestamp')
            )
            await self._invoke_callback(self.on_book_update, data)

        elif event_type == 'price_change':
            price = data.get('price')
            if price:
                self._data_store.update_price(token_id, float(price))
            await self._invoke_callback(self.on_price_change, data)

        elif event_type == 'last_trade_price':
            price = data.get('price')
            size = data.get('size')
            side = data.get('side')
            if price:
                self._data_store.update_trade(
                    token_id,
                    float(price),
                    float(size) if size else None,
                    side
                )
            await self._invoke_callback(self.on_trade, data)

    async def _invoke_callback(self, callback: Optional[Callable], data: Any):
        """Invoke callback (supports sync and async)."""
        if callback is None:
            return

        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(data)
            else:
                callback(data)
        except Exception as e:
            logger.error(f"Callback error: {e}")

    async def _health_monitor(self):
        """Monitor health and manage failover."""
        import time

        while True:
            try:
                await asyncio.sleep(5.0)

                ws_connected = self._ws.is_connected
                data_fresh = self._data_store.all_fresh()

                # Check if WS is healthy
                if ws_connected and data_fresh:
                    if self._ws_healthy_since == 0:
                        self._ws_healthy_since = time.time()

                    # If WS healthy long enough, stop REST
                    if self._rest.is_running:
                        healthy_duration = time.time() - self._ws_healthy_since
                        if healthy_duration >= self._rest_recovery_delay:
                            logger.info("WebSocket recovered, stopping REST fallback")
                            await self._rest.stop()
                            self._data_source = "websocket"
                else:
                    self._ws_healthy_since = 0

                    # If WS unhealthy and REST not running, start it
                    if not self._rest.is_running and self._state == FeedState.RUNNING:
                        logger.warning("WebSocket unhealthy, starting REST fallback")
                        await self._rest.start(self._tokens)
                        self._data_source = "rest"

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
