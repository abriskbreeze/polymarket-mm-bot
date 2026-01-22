"""
Fill Feed - WebSocket subscription for order fills.

For LIVE trading only - provides real-time fill notifications.
"""

import asyncio
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Callable, List, Any
import websockets

from src.config import POLY_API_KEY
from src.utils import setup_logging

logger = setup_logging()

@dataclass
class FillEvent:
    """A fill event from WebSocket."""
    order_id: str
    price: float
    size: float
    side: str
    timestamp: int
    fee: float = 0.0

    @classmethod
    def from_ws_message(cls, data: dict) -> "FillEvent":
        """Parse from WebSocket message."""
        return cls(
            order_id=data.get("order_id", ""),
            price=float(data.get("price", 0)),
            size=float(data.get("size", 0)),
            side=data.get("side", ""),
            timestamp=data.get("timestamp", 0),
            fee=float(data.get("fee", 0)),
        )

class FillFeed:
    """
    WebSocket feed for order fills.

    Usage:
        feed = FillFeed()

        @feed.on_fill
        def handle_fill(event: FillEvent):
            print(f"Filled: {event.order_id}")

        await feed.start()
    """

    WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/user"

    def __init__(self):
        self._ws: Any = None
        self._callbacks: List[Callable[[FillEvent], None]] = []
        self._running = False
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def on_fill(self, callback: Callable[[FillEvent], None]):
        """Register fill callback."""
        self._callbacks.append(callback)

    async def start(self):
        """Start the fill feed."""
        if self._running:
            return

        self._running = True
        await self._connect()
        asyncio.create_task(self._listen())

    async def stop(self):
        """Stop the fill feed."""
        self._running = False
        self._connected = False
        if self._ws:
            await self._ws.close()

    async def _connect(self):
        """Connect to WebSocket."""
        try:
            self._ws = await websockets.connect(
                self.WS_URL,
                extra_headers={"Authorization": f"Bearer {POLY_API_KEY}"},
            )

            # Subscribe to fills
            await self._ws.send(json.dumps({
                "type": "subscribe",
                "channel": "user",
                "events": ["trade"],
            }))

            self._connected = True
            logger.info("Connected to fill WebSocket")

        except Exception as e:
            logger.error(f"Failed to connect to fill WS: {e}")
            self._ws = None
            self._connected = False

    async def _listen(self):
        """Listen for messages."""
        while self._running and self._ws:
            try:
                message = await self._ws.recv()
                data = json.loads(message)
                self._handle_message(data)

            except websockets.ConnectionClosed:
                logger.warning("Fill WS connection closed")
                self._connected = False
                if self._running:
                    await asyncio.sleep(5)
                    await self._connect()

            except Exception as e:
                logger.error(f"Fill WS error: {e}")

    def _handle_message(self, data: dict):
        """Handle incoming WebSocket message."""
        msg_type = data.get("type")

        if msg_type == "trade":
            event = FillEvent.from_ws_message(data)

            for callback in self._callbacks:
                try:
                    callback(event)
                except Exception as e:
                    logger.error(f"Fill callback error: {e}")
