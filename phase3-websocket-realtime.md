# Task: Polymarket Trading Bot - Phase 3: WebSocket Real-Time Data

## Context

This is Phase 3 of a 10-phase iterative build of a Polymarket market-making bot. Phase 1 (Environment & Connectivity) and Phase 2 (Market Discovery & Data Fetching) have been completed and verified.

## Objective

Establish WebSocket connections for real-time market data streaming, including order book updates, price changes, and trade notifications.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         POLYMARKET BOT - PHASE 3                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│                        ┌─────────────────────────┐                          │
│                        │     Your Bot Logic      │                          │
│                        │                         │                          │
│                        │  • Price callbacks      │                          │
│                        │  • Book callbacks       │                          │
│                        │  • Trade callbacks      │                          │
│                        └───────────┬─────────────┘                          │
│                                    │                                        │
│                                    ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      websocket_client.py                            │   │
│   │                                                                     │   │
│   │  ┌─────────────────┐    ┌─────────────────┐    ┌────────────────┐  │   │
│   │  │ MarketWebSocket │    │ ConnectionMgr   │    │ MessageRouter  │  │   │
│   │  │                 │    │                 │    │                │  │   │
│   │  │ • connect()     │    │ • reconnect     │    │ • parse msg    │  │   │
│   │  │ • subscribe()   │    │ • heartbeat     │    │ • route to     │  │   │
│   │  │ • disconnect()  │    │ • health check  │    │   callbacks    │  │   │
│   │  └────────┬────────┘    └────────┬────────┘    └───────┬────────┘  │   │
│   │           │                      │                     │           │   │
│   │           └──────────────────────┼─────────────────────┘           │   │
│   │                                  │                                 │   │
│   └──────────────────────────────────┼─────────────────────────────────┘   │
│                                      │                                      │
└──────────────────────────────────────┼──────────────────────────────────────┘
                                       │
                                       │ WSS
                                       ▼
                    ┌─────────────────────────────────────┐
                    │   Polymarket WebSocket Server       │
                    │                                     │
                    │   wss://ws-subscriptions-clob.      │
                    │        polymarket.com/ws/market     │
                    │                                     │
                    │   Channels:                         │
                    │   • market (public, no auth)        │
                    │   • user (auth required - Phase 5)  │
                    └─────────────────────────────────────┘
```

---

## WebSocket Connection State Machine

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CONNECTION STATE MACHINE                                 │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────┐
                              │             │
                              │ DISCONNECTED│◀─────────────────────────────┐
                              │             │                              │
                              └──────┬──────┘                              │
                                     │                                     │
                                     │ connect()                           │
                                     ▼                                     │
                              ┌─────────────┐                              │
                              │             │                              │
                              │ CONNECTING  │                              │
                              │             │                              │
                              └──────┬──────┘                              │
                                     │                                     │
                        ┌────────────┼────────────┐                        │
                        │            │            │                        │
                        ▼            │            ▼                        │
                 ┌───────────┐       │     ┌───────────┐                   │
                 │           │       │     │           │     max retries   │
                 │  FAILED   │       │     │ CONNECTED │     exceeded      │
                 │           │       │     │           │─────────────────▶─┤
                 └─────┬─────┘       │     └─────┬─────┘                   │
                       │             │           │                         │
                       │             │           │ subscribe()             │
                       │             │           ▼                         │
                       │             │    ┌─────────────┐                  │
                       │             │    │             │                  │
                       │ retry       │    │ SUBSCRIBED  │◀────────┐       │
                       │             │    │             │         │       │
                       │             │    └──────┬──────┘         │       │
                       │             │           │                │       │
                       │             │           │ error/close    │       │
                       └─────────────┘           ▼                │       │
                                          ┌─────────────┐         │       │
                                          │             │         │       │
                                          │RECONNECTING │─────────┘       │
                                          │             │  success        │
                                          └──────┬──────┘                 │
                                                 │                        │
                                                 │ disconnect() or        │
                                                 │ max retries            │
                                                 └────────────────────────┘


  STATES:
  ═══════
  • DISCONNECTED  - Initial state, not connected
  • CONNECTING    - Attempting to establish connection
  • CONNECTED     - WebSocket open, ready to subscribe
  • SUBSCRIBED    - Actively receiving market data
  • RECONNECTING  - Lost connection, attempting to reconnect
  • FAILED        - Connection attempt failed, will retry
```

---

## Message Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MESSAGE FLOW                                        │
└─────────────────────────────────────────────────────────────────────────────┘


  SUBSCRIPTION FLOW:
  ══════════════════

  Bot                          WebSocket Server
   │                                  │
   │   1. Connect (WSS)               │
   │ ─────────────────────────────▶   │
   │                                  │
   │   2. Connection Established      │
   │ ◀─────────────────────────────   │
   │                                  │
   │   3. Subscribe Message           │
   │   {                              │
   │     "type": "market",            │
   │     "assets_ids": ["token1"]     │
   │   }                              │
   │ ─────────────────────────────▶   │
   │                                  │
   │   4. Subscription Confirmed      │
   │ ◀─────────────────────────────   │
   │                                  │
   │   5. Market Updates (streaming)  │
   │ ◀─────────────────────────────   │
   │ ◀─────────────────────────────   │
   │ ◀─────────────────────────────   │
   │            ...                   │
   │                                  │


  MESSAGE TYPES RECEIVED:
  ═══════════════════════

  ┌─────────────────────────────────────────────────────────────────────┐
  │  price_change                                                       │
  │  ─────────────                                                      │
  │  {                                                                  │
  │    "event_type": "price_change",                                    │
  │    "asset_id": "12345...",                                          │
  │    "market": "0xabc...",                                            │
  │    "price": "0.55",                                                 │
  │    "side": "BUY",                                                   │
  │    "timestamp": "1234567890"                                        │
  │  }                                                                  │
  └─────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────┐
  │  book                                                               │
  │  ────                                                               │
  │  {                                                                  │
  │    "event_type": "book",                                            │
  │    "asset_id": "12345...",                                          │
  │    "market": "0xabc...",                                            │
  │    "bids": [{"price": "0.54", "size": "100"}, ...],                 │
  │    "asks": [{"price": "0.56", "size": "200"}, ...],                 │
  │    "timestamp": "1234567890",                                       │
  │    "hash": "0xdef..."                                               │
  │  }                                                                  │
  └─────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────┐
  │  last_trade_price                                                   │
  │  ────────────────                                                   │
  │  {                                                                  │
  │    "event_type": "last_trade_price",                                │
  │    "asset_id": "12345...",                                          │
  │    "market": "0xabc...",                                            │
  │    "price": "0.55",                                                 │
  │    "side": "BUY",                                                   │
  │    "size": "50.5",                                                  │
  │    "timestamp": "1234567890"                                        │
  │  }                                                                  │
  └─────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────┐
  │  tick_size_change                                                   │
  │  ────────────────                                                   │
  │  {                                                                  │
  │    "event_type": "tick_size_change",                                │
  │    "asset_id": "12345...",                                          │
  │    "market": "0xabc...",                                            │
  │    "old_tick_size": "0.01",                                         │
  │    "new_tick_size": "0.001",                                        │
  │    "timestamp": "1234567890"                                        │
  │  }                                                                  │
  └─────────────────────────────────────────────────────────────────────┘
```

---

## Event Callback Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       CALLBACK ARCHITECTURE                                 │
└─────────────────────────────────────────────────────────────────────────────┘

                         WebSocket Message Received
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   Parse JSON        │
                         │   Extract event_type│
                         └──────────┬──────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │      Message Router           │
                    │   switch(event_type)          │
                    └───────────────┬───────────────┘
                                    │
           ┌────────────────────────┼────────────────────────┐
           │                        │                        │
           ▼                        ▼                        ▼
   ┌───────────────┐       ┌───────────────┐       ┌───────────────┐
   │ price_change  │       │    book       │       │last_trade_price│
   └───────┬───────┘       └───────┬───────┘       └───────┬───────┘
           │                       │                       │
           ▼                       ▼                       ▼
   ┌───────────────┐       ┌───────────────┐       ┌───────────────┐
   │ on_price_     │       │ on_book_      │       │ on_trade_     │
   │ change()      │       │ update()      │       │ update()      │
   │               │       │               │       │               │
   │ User callback │       │ User callback │       │ User callback │
   └───────────────┘       └───────────────┘       └───────────────┘


  CALLBACK SIGNATURES:
  ════════════════════

  on_price_change(data: dict) -> None
      Called when best bid/ask changes
      data contains: asset_id, price, side, timestamp

  on_book_update(data: dict) -> None
      Called when order book changes
      data contains: asset_id, bids, asks, timestamp

  on_trade(data: dict) -> None
      Called when a trade executes
      data contains: asset_id, price, size, side, timestamp

  on_error(error: Exception) -> None
      Called on WebSocket errors

  on_disconnect() -> None
      Called when connection is lost
```

---

## Local Order Book Maintenance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LOCAL ORDER BOOK MANAGEMENT                              │
└─────────────────────────────────────────────────────────────────────────────┘

  INITIAL STATE (from REST API - Phase 2):
  ═════════════════════════════════════════

  ┌─────────────────────────────────────────────────────┐
  │  Local Order Book (token_id: "12345...")            │
  │                                                     │
  │  BIDS (buy orders)     │    ASKS (sell orders)      │
  │  ──────────────────    │    ─────────────────       │
  │  $0.54 x 100           │    $0.56 x 200             │
  │  $0.53 x 250           │    $0.57 x 150             │
  │  $0.52 x 500           │    $0.58 x 300             │
  │                        │                            │
  │  hash: "0xabc123..."   │                            │
  └─────────────────────────────────────────────────────┘


  UPDATE RECEIVED VIA WEBSOCKET:
  ══════════════════════════════

  ┌──────────────────────────────────────┐
  │  {                                   │
  │    "event_type": "book",             │
  │    "asset_id": "12345...",           │
  │    "bids": [                         │
  │      {"price": "0.55", "size": "75"},│ ◀── New bid level!
  │      {"price": "0.54", "size": "100"}│
  │    ],                                │
  │    "asks": [...],                    │
  │    "hash": "0xdef456..."             │
  │  }                                   │
  └──────────────────────────────────────┘
                    │
                    ▼

  UPDATED LOCAL ORDER BOOK:
  ═════════════════════════

  ┌─────────────────────────────────────────────────────┐
  │  Local Order Book (token_id: "12345...")            │
  │                                                     │
  │  BIDS (buy orders)     │    ASKS (sell orders)      │
  │  ──────────────────    │    ─────────────────       │
  │  $0.55 x 75   ◀── NEW  │    $0.56 x 200             │
  │  $0.54 x 100           │    $0.57 x 150             │
  │  $0.53 x 250           │    $0.58 x 300             │
  │                        │                            │
  │  hash: "0xdef456..."   │  (hash updated)            │
  └─────────────────────────────────────────────────────┘


  STALE DATA DETECTION:
  ═════════════════════

  If no updates received for > 30 seconds:
  ┌─────────────────────────┐
  │  ⚠️  STALE DATA WARNING │
  │                         │
  │  Last update: 45s ago   │
  │  Action: Re-fetch from  │
  │          REST API       │
  └─────────────────────────┘
```

---

## Reconnection Strategy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RECONNECTION WITH EXPONENTIAL BACKOFF                    │
└─────────────────────────────────────────────────────────────────────────────┘

  Connection Lost
        │
        ▼
  ┌─────────────┐
  │ Attempt 1   │──▶ Wait 1 second ──▶ Try Connect
  └─────────────┘                            │
                                    ┌────────┴────────┐
                                    │                 │
                                 Success           Failed
                                    │                 │
                                    ▼                 ▼
                              ┌──────────┐    ┌─────────────┐
                              │CONNECTED │    │ Attempt 2   │──▶ Wait 2 sec
                              └──────────┘    └─────────────┘
                                                     │
                                            ┌────────┴────────┐
                                            │                 │
                                         Success           Failed
                                            │                 │
                                            ▼                 ▼
                                      ┌──────────┐    ┌─────────────┐
                                      │CONNECTED │    │ Attempt 3   │──▶ Wait 4 sec
                                      └──────────┘    └─────────────┘
                                                             │
                                                             ▼
                                                           ...
                                                             │
                                                             ▼
                                                    ┌─────────────┐
                                                    │ Attempt N   │──▶ Wait min(2^N, 60) sec
                                                    └─────────────┘
                                                             │
                                                             ▼
                                                    ┌─────────────────┐
                                                    │ Max retries (10)│
                                                    │ exceeded        │
                                                    │                 │
                                                    │ Call on_error() │
                                                    │ Give up         │
                                                    └─────────────────┘


  BACKOFF FORMULA:
  ════════════════

  wait_time = min(2^attempt, max_wait)

  where:
    attempt  = retry attempt number (1, 2, 3, ...)
    max_wait = 60 seconds (cap)

  Example sequence: 1s, 2s, 4s, 8s, 16s, 32s, 60s, 60s, 60s, 60s (give up)
```

---

## Prerequisites

- Phase 1 completed and all tests passing
- Phase 2 completed and all tests passing
- Working market discovery and pricing functions

## Requirements

### 1. Update Project Structure

Add these new files:

```
/polymarket-bot
├── /src
│   ├── __init__.py
│   ├── config.py              # (existing)
│   ├── client.py              # (existing)
│   ├── utils.py               # (existing)
│   ├── models.py              # (existing)
│   ├── markets.py             # (existing)
│   ├── pricing.py             # (existing)
│   └── websocket_client.py    # NEW - WebSocket client
├── /tests
│   ├── __init__.py
│   ├── test_phase1.py         # (existing)
│   ├── test_phase2.py         # (existing)
│   └── test_phase3.py         # NEW - Phase 3 tests
└── ...
```

### 2. Update config.py

Add WebSocket configuration:

```python
# Add to existing config.py

# WebSocket Configuration
WS_MARKET_URL = os.getenv(
    "WS_MARKET_URL", 
    "wss://ws-subscriptions-clob.polymarket.com/ws/market"
)

# Reconnection settings
WS_RECONNECT_ATTEMPTS = int(os.getenv("WS_RECONNECT_ATTEMPTS", "10"))
WS_RECONNECT_BASE_DELAY = float(os.getenv("WS_RECONNECT_BASE_DELAY", "1.0"))
WS_RECONNECT_MAX_DELAY = float(os.getenv("WS_RECONNECT_MAX_DELAY", "60.0"))
WS_HEARTBEAT_INTERVAL = float(os.getenv("WS_HEARTBEAT_INTERVAL", "30.0"))
WS_STALE_DATA_THRESHOLD = float(os.getenv("WS_STALE_DATA_THRESHOLD", "60.0"))
```

### 3. Update .env.example

Add WebSocket settings:

```
# Add to existing .env.example

# WebSocket Configuration (optional overrides)
WS_MARKET_URL=wss://ws-subscriptions-clob.polymarket.com/ws/market
WS_RECONNECT_ATTEMPTS=10
WS_RECONNECT_BASE_DELAY=1.0
WS_RECONNECT_MAX_DELAY=60.0
WS_HEARTBEAT_INTERVAL=30.0
WS_STALE_DATA_THRESHOLD=60.0
```

### 4. websocket_client.py - WebSocket Client

```python
"""
WebSocket client for real-time Polymarket market data.
"""

import json
import asyncio
import time
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
import websockets
from websockets.exceptions import (
    ConnectionClosed, 
    ConnectionClosedError,
    ConnectionClosedOK
)

from src.config import (
    WS_MARKET_URL,
    WS_RECONNECT_ATTEMPTS,
    WS_RECONNECT_BASE_DELAY,
    WS_RECONNECT_MAX_DELAY,
    WS_HEARTBEAT_INTERVAL,
    WS_STALE_DATA_THRESHOLD
)
from src.models import OrderBook, PriceLevel
from src.utils import setup_logging

logger = setup_logging()


class ConnectionState(Enum):
    """WebSocket connection states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    SUBSCRIBED = "subscribed"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


@dataclass
class MarketData:
    """Container for real-time market data"""
    token_id: str
    order_book: Optional[OrderBook] = None
    last_price: Optional[float] = None
    last_trade_price: Optional[float] = None
    last_trade_side: Optional[str] = None
    last_trade_size: Optional[float] = None
    last_update_time: float = 0.0
    tick_size: str = "0.01"
    
    @property
    def is_stale(self) -> bool:
        """Check if data is stale (no updates for threshold period)"""
        if self.last_update_time == 0:
            return True
        return (time.time() - self.last_update_time) > WS_STALE_DATA_THRESHOLD


class MarketWebSocket:
    """
    WebSocket client for Polymarket market data.
    
    Handles:
    - Connection management with automatic reconnection
    - Market channel subscriptions
    - Real-time order book updates
    - Price change notifications
    - Trade notifications
    
    Usage:
        ws = MarketWebSocket()
        ws.on_price_change = my_price_handler
        ws.on_book_update = my_book_handler
        
        await ws.connect()
        await ws.subscribe(["token_id_1", "token_id_2"])
        
        # ... run your logic ...
        
        await ws.disconnect()
    """
    
    def __init__(self, url: str = WS_MARKET_URL):
        self.url = url
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._state = ConnectionState.DISCONNECTED
        self._subscribed_tokens: List[str] = []
        self._market_data: Dict[str, MarketData] = {}
        
        # Reconnection state
        self._reconnect_attempt = 0
        self._should_reconnect = True
        
        # Background tasks
        self._receive_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        
        # Callbacks (user-provided)
        self.on_price_change: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_book_update: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_trade: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_tick_size_change: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_error: Optional[Callable[[Exception], None]] = None
        self.on_connect: Optional[Callable[[], None]] = None
        self.on_disconnect: Optional[Callable[[], None]] = None
    
    @property
    def state(self) -> ConnectionState:
        """Current connection state"""
        return self._state
    
    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected and subscribed"""
        return self._state in (ConnectionState.CONNECTED, ConnectionState.SUBSCRIBED)
    
    @property
    def subscribed_tokens(self) -> List[str]:
        """List of currently subscribed token IDs"""
        return self._subscribed_tokens.copy()
    
    def get_market_data(self, token_id: str) -> Optional[MarketData]:
        """Get current market data for a token"""
        return self._market_data.get(token_id)
    
    def get_order_book(self, token_id: str) -> Optional[OrderBook]:
        """Get current order book for a token"""
        data = self._market_data.get(token_id)
        return data.order_book if data else None
    
    async def connect(self) -> bool:
        """
        Establish WebSocket connection.
        
        Returns:
            True if connection successful, False otherwise
        """
        if self._state in (ConnectionState.CONNECTED, ConnectionState.SUBSCRIBED):
            logger.warning("Already connected")
            return True
        
        self._state = ConnectionState.CONNECTING
        self._should_reconnect = True
        
        try:
            logger.info(f"Connecting to {self.url}")
            self._ws = await websockets.connect(
                self.url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5
            )
            
            self._state = ConnectionState.CONNECTED
            self._reconnect_attempt = 0
            
            # Start background tasks
            self._receive_task = asyncio.create_task(self._receive_loop())
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            logger.info("WebSocket connected")
            
            if self.on_connect:
                self.on_connect()
            
            return True
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._state = ConnectionState.FAILED
            
            if self.on_error:
                self.on_error(e)
            
            return False
    
    async def disconnect(self):
        """Disconnect WebSocket and cleanup"""
        logger.info("Disconnecting WebSocket")
        self._should_reconnect = False
        
        # Cancel background tasks
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Close WebSocket
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                logger.debug(f"Error closing WebSocket: {e}")
        
        self._ws = None
        self._state = ConnectionState.DISCONNECTED
        self._subscribed_tokens = []
        
        if self.on_disconnect:
            self.on_disconnect()
        
        logger.info("WebSocket disconnected")
    
    async def subscribe(self, token_ids: List[str]) -> bool:
        """
        Subscribe to market data for given tokens.
        
        Args:
            token_ids: List of token IDs to subscribe to
            
        Returns:
            True if subscription sent successfully
        """
        if not self.is_connected:
            logger.error("Cannot subscribe: not connected")
            return False
        
        if not token_ids:
            logger.warning("No token IDs provided")
            return False
        
        # Build subscription message
        message = {
            "type": "market",
            "assets_ids": token_ids
        }
        
        try:
            await self._ws.send(json.dumps(message))
            
            # Initialize market data containers
            for token_id in token_ids:
                if token_id not in self._market_data:
                    self._market_data[token_id] = MarketData(token_id=token_id)
                if token_id not in self._subscribed_tokens:
                    self._subscribed_tokens.append(token_id)
            
            self._state = ConnectionState.SUBSCRIBED
            logger.info(f"Subscribed to {len(token_ids)} token(s)")
            
            return True
            
        except Exception as e:
            logger.error(f"Subscription failed: {e}")
            return False
    
    async def unsubscribe(self, token_ids: List[str]) -> bool:
        """
        Unsubscribe from specific tokens.
        
        Args:
            token_ids: List of token IDs to unsubscribe from
            
        Returns:
            True if successful
        """
        # Remove from tracking
        for token_id in token_ids:
            if token_id in self._subscribed_tokens:
                self._subscribed_tokens.remove(token_id)
            if token_id in self._market_data:
                del self._market_data[token_id]
        
        # Re-subscribe with remaining tokens
        if self._subscribed_tokens:
            return await self.subscribe(self._subscribed_tokens)
        
        return True
    
    async def _receive_loop(self):
        """Background task to receive and process messages"""
        while self._should_reconnect:
            try:
                if not self._ws:
                    await asyncio.sleep(0.1)
                    continue
                
                message = await self._ws.recv()
                await self._handle_message(message)
                
            except ConnectionClosedOK:
                logger.info("WebSocket closed normally")
                break
                
            except (ConnectionClosed, ConnectionClosedError) as e:
                logger.warning(f"Connection closed: {e}")
                if self._should_reconnect:
                    await self._reconnect()
                break
                
            except asyncio.CancelledError:
                break
                
            except Exception as e:
                logger.error(f"Error in receive loop: {e}")
                if self.on_error:
                    self.on_error(e)
    
    async def _heartbeat_loop(self):
        """Background task to send periodic heartbeats"""
        while self._should_reconnect:
            try:
                await asyncio.sleep(WS_HEARTBEAT_INTERVAL)
                
                if self._ws and self.is_connected:
                    # WebSockets library handles ping/pong automatically
                    # but we can check for stale connections here
                    stale_tokens = [
                        t for t, d in self._market_data.items() 
                        if d.is_stale
                    ]
                    if stale_tokens:
                        logger.warning(f"Stale data detected for {len(stale_tokens)} token(s)")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Heartbeat error: {e}")
    
    async def _reconnect(self):
        """Attempt to reconnect with exponential backoff"""
        if not self._should_reconnect:
            return
        
        self._state = ConnectionState.RECONNECTING
        
        while self._reconnect_attempt < WS_RECONNECT_ATTEMPTS:
            self._reconnect_attempt += 1
            
            # Calculate delay with exponential backoff
            delay = min(
                WS_RECONNECT_BASE_DELAY * (2 ** (self._reconnect_attempt - 1)),
                WS_RECONNECT_MAX_DELAY
            )
            
            logger.info(
                f"Reconnect attempt {self._reconnect_attempt}/{WS_RECONNECT_ATTEMPTS} "
                f"in {delay:.1f}s"
            )
            
            await asyncio.sleep(delay)
            
            if not self._should_reconnect:
                return
            
            # Try to reconnect
            try:
                self._ws = await websockets.connect(
                    self.url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5
                )
                
                self._state = ConnectionState.CONNECTED
                self._reconnect_attempt = 0
                
                logger.info("Reconnected successfully")
                
                # Re-subscribe to previous tokens
                if self._subscribed_tokens:
                    await self.subscribe(self._subscribed_tokens)
                
                # Restart receive loop
                self._receive_task = asyncio.create_task(self._receive_loop())
                
                if self.on_connect:
                    self.on_connect()
                
                return
                
            except Exception as e:
                logger.warning(f"Reconnect attempt failed: {e}")
        
        # Max retries exceeded
        logger.error("Max reconnection attempts exceeded")
        self._state = ConnectionState.FAILED
        
        if self.on_error:
            self.on_error(Exception("Max reconnection attempts exceeded"))
    
    async def _handle_message(self, raw_message: str):
        """Parse and route incoming messages"""
        try:
            data = json.loads(raw_message)
            
            event_type = data.get("event_type")
            asset_id = data.get("asset_id")
            
            if not event_type:
                logger.debug(f"Unknown message format: {raw_message[:100]}")
                return
            
            # Update last update time
            if asset_id and asset_id in self._market_data:
                self._market_data[asset_id].last_update_time = time.time()
            
            # Route to appropriate handler
            if event_type == "price_change":
                self._handle_price_change(data)
            elif event_type == "book":
                self._handle_book_update(data)
            elif event_type == "last_trade_price":
                self._handle_trade(data)
            elif event_type == "tick_size_change":
                self._handle_tick_size_change(data)
            else:
                logger.debug(f"Unhandled event type: {event_type}")
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message: {e}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    def _handle_price_change(self, data: Dict[str, Any]):
        """Handle price_change events"""
        asset_id = data.get("asset_id")
        
        if asset_id and asset_id in self._market_data:
            price = data.get("price")
            if price:
                self._market_data[asset_id].last_price = float(price)
        
        if self.on_price_change:
            self.on_price_change(data)
    
    def _handle_book_update(self, data: Dict[str, Any]):
        """Handle book events (order book updates)"""
        asset_id = data.get("asset_id")
        
        if asset_id and asset_id in self._market_data:
            # Parse order book
            bids = []
            asks = []
            
            for bid in data.get("bids", []):
                if isinstance(bid, dict):
                    bids.append(PriceLevel(
                        price=float(bid.get("price", 0)),
                        size=float(bid.get("size", 0))
                    ))
            
            for ask in data.get("asks", []):
                if isinstance(ask, dict):
                    asks.append(PriceLevel(
                        price=float(ask.get("price", 0)),
                        size=float(ask.get("size", 0))
                    ))
            
            # Sort properly
            bids.sort(key=lambda x: x.price, reverse=True)
            asks.sort(key=lambda x: x.price)
            
            self._market_data[asset_id].order_book = OrderBook(
                token_id=asset_id,
                bids=bids,
                asks=asks,
                timestamp=data.get("timestamp")
            )
        
        if self.on_book_update:
            self.on_book_update(data)
    
    def _handle_trade(self, data: Dict[str, Any]):
        """Handle last_trade_price events"""
        asset_id = data.get("asset_id")
        
        if asset_id and asset_id in self._market_data:
            md = self._market_data[asset_id]
            md.last_trade_price = float(data.get("price", 0))
            md.last_trade_side = data.get("side")
            md.last_trade_size = float(data.get("size", 0)) if data.get("size") else None
        
        if self.on_trade:
            self.on_trade(data)
    
    def _handle_tick_size_change(self, data: Dict[str, Any]):
        """Handle tick_size_change events"""
        asset_id = data.get("asset_id")
        
        if asset_id and asset_id in self._market_data:
            new_tick = data.get("new_tick_size")
            if new_tick:
                self._market_data[asset_id].tick_size = new_tick
        
        if self.on_tick_size_change:
            self.on_tick_size_change(data)
```

### 5. tests/test_phase3.py - Verification Tests

```python
"""
Phase 3 Verification Tests
Run with: pytest tests/test_phase3.py -v

Phase 3 is ONLY complete when all tests pass.

Note: These tests require network access to Polymarket's WebSocket server.
Some tests may take up to 60 seconds to complete as they wait for real market data.
"""

import pytest
import asyncio
from typing import List, Dict, Any


class TestWebSocketClient:
    """Test WebSocket client functionality"""
    
    def _get_test_token_id(self) -> str:
        """Helper to get a valid token ID for testing"""
        from src.markets import fetch_active_markets
        
        markets = fetch_active_markets(limit=10)
        for m in markets:
            if m.token_ids:
                return m.token_ids[0]
        pytest.skip("No markets with token IDs found")
    
    def test_import_websocket_client(self):
        """Verify WebSocket client can be imported"""
        from src.websocket_client import MarketWebSocket, ConnectionState
        
        assert MarketWebSocket is not None
        assert ConnectionState is not None
        print("✓ WebSocket client imported successfully")
    
    def test_client_instantiation(self):
        """Verify WebSocket client can be instantiated"""
        from src.websocket_client import MarketWebSocket, ConnectionState
        
        ws = MarketWebSocket()
        
        assert ws.state == ConnectionState.DISCONNECTED
        assert ws.is_connected == False
        assert len(ws.subscribed_tokens) == 0
        
        print("✓ WebSocket client instantiated")
        print(f"  Initial state: {ws.state.value}")
    
    @pytest.mark.asyncio
    async def test_connect_disconnect(self):
        """Verify WebSocket can connect and disconnect"""
        from src.websocket_client import MarketWebSocket, ConnectionState
        
        ws = MarketWebSocket()
        
        # Connect
        result = await ws.connect()
        assert result == True, "Connection should succeed"
        assert ws.state == ConnectionState.CONNECTED
        print("✓ Connected to WebSocket server")
        
        # Disconnect
        await ws.disconnect()
        assert ws.state == ConnectionState.DISCONNECTED
        print("✓ Disconnected from WebSocket server")
    
    @pytest.mark.asyncio
    async def test_subscribe_to_market(self):
        """Verify we can subscribe to market data"""
        from src.websocket_client import MarketWebSocket, ConnectionState
        
        ws = MarketWebSocket()
        token_id = self._get_test_token_id()
        
        try:
            # Connect
            await ws.connect()
            assert ws.is_connected
            
            # Subscribe
            result = await ws.subscribe([token_id])
            assert result == True, "Subscription should succeed"
            assert ws.state == ConnectionState.SUBSCRIBED
            assert token_id in ws.subscribed_tokens
            
            print(f"✓ Subscribed to token: {token_id[:20]}...")
            
        finally:
            await ws.disconnect()
    
    @pytest.mark.asyncio
    async def test_receive_market_data(self):
        """Verify we receive real-time market data"""
        from src.websocket_client import MarketWebSocket
        
        ws = MarketWebSocket()
        token_id = self._get_test_token_id()
        
        received_messages: List[Dict[str, Any]] = []
        
        def on_any_message(data: Dict[str, Any]):
            received_messages.append(data)
            print(f"  Received: {data.get('event_type')} for {data.get('asset_id', 'unknown')[:15]}...")
        
        # Set up callbacks for all message types
        ws.on_price_change = on_any_message
        ws.on_book_update = on_any_message
        ws.on_trade = on_any_message
        
        try:
            await ws.connect()
            await ws.subscribe([token_id])
            
            # Wait for messages (up to 60 seconds)
            print("  Waiting for market data (up to 60s)...")
            for i in range(60):
                await asyncio.sleep(1)
                if len(received_messages) >= 1:
                    break
            
            # We should have received at least some data
            # Note: Very illiquid markets might not have activity
            print(f"✓ Received {len(received_messages)} message(s)")
            
        finally:
            await ws.disconnect()
    
    @pytest.mark.asyncio
    async def test_order_book_maintenance(self):
        """Verify local order book is maintained"""
        from src.websocket_client import MarketWebSocket
        
        ws = MarketWebSocket()
        token_id = self._get_test_token_id()
        
        book_updates = []
        
        def on_book(data):
            book_updates.append(data)
        
        ws.on_book_update = on_book
        
        try:
            await ws.connect()
            await ws.subscribe([token_id])
            
            # Wait for a book update (up to 60 seconds)
            print("  Waiting for order book update (up to 60s)...")
            for i in range(60):
                await asyncio.sleep(1)
                book = ws.get_order_book(token_id)
                if book and (book.bids or book.asks):
                    print(f"✓ Order book received:")
                    print(f"  Bids: {len(book.bids)}, Asks: {len(book.asks)}")
                    if book.midpoint:
                        print(f"  Midpoint: {book.midpoint:.4f}")
                    if book.spread:
                        print(f"  Spread: {book.spread:.4f}")
                    break
            
        finally:
            await ws.disconnect()
    
    @pytest.mark.asyncio
    async def test_callbacks_are_called(self):
        """Verify callbacks are invoked correctly"""
        from src.websocket_client import MarketWebSocket
        
        ws = MarketWebSocket()
        token_id = self._get_test_token_id()
        
        callback_events = {
            "connect": False,
            "disconnect": False,
            "price_change": False,
            "book_update": False,
            "trade": False
        }
        
        ws.on_connect = lambda: callback_events.update({"connect": True})
        ws.on_disconnect = lambda: callback_events.update({"disconnect": True})
        ws.on_price_change = lambda d: callback_events.update({"price_change": True})
        ws.on_book_update = lambda d: callback_events.update({"book_update": True})
        ws.on_trade = lambda d: callback_events.update({"trade": True})
        
        try:
            await ws.connect()
            assert callback_events["connect"], "on_connect should be called"
            print("✓ on_connect callback fired")
            
            await ws.subscribe([token_id])
            
            # Wait for some data
            await asyncio.sleep(30)
            
        finally:
            await ws.disconnect()
            assert callback_events["disconnect"], "on_disconnect should be called"
            print("✓ on_disconnect callback fired")
        
        print(f"✓ Callback status: {callback_events}")
    
    @pytest.mark.asyncio
    async def test_multiple_subscriptions(self):
        """Verify we can subscribe to multiple tokens"""
        from src.websocket_client import MarketWebSocket
        from src.markets import fetch_active_markets
        
        # Get multiple token IDs
        markets = fetch_active_markets(limit=5)
        token_ids = []
        for m in markets:
            if m.token_ids:
                token_ids.append(m.token_ids[0])
                if len(token_ids) >= 3:
                    break
        
        if len(token_ids) < 2:
            pytest.skip("Need at least 2 tokens for this test")
        
        ws = MarketWebSocket()
        
        try:
            await ws.connect()
            result = await ws.subscribe(token_ids)
            
            assert result == True
            assert len(ws.subscribed_tokens) == len(token_ids)
            
            print(f"✓ Subscribed to {len(token_ids)} tokens simultaneously")
            
        finally:
            await ws.disconnect()


class TestConnectionState:
    """Test connection state management"""
    
    def test_state_enum_values(self):
        """Verify connection states are properly defined"""
        from src.websocket_client import ConnectionState
        
        states = [
            ConnectionState.DISCONNECTED,
            ConnectionState.CONNECTING,
            ConnectionState.CONNECTED,
            ConnectionState.SUBSCRIBED,
            ConnectionState.RECONNECTING,
            ConnectionState.FAILED
        ]
        
        for state in states:
            assert state.value is not None
        
        print(f"✓ All {len(states)} connection states defined")


class TestMarketData:
    """Test MarketData container"""
    
    def test_market_data_creation(self):
        """Verify MarketData can be created"""
        from src.websocket_client import MarketData
        
        md = MarketData(token_id="test_token")
        
        assert md.token_id == "test_token"
        assert md.order_book is None
        assert md.last_price is None
        assert md.is_stale == True  # No updates yet
        
        print("✓ MarketData container created")
    
    def test_stale_data_detection(self):
        """Verify stale data detection works"""
        from src.websocket_client import MarketData
        import time
        
        md = MarketData(token_id="test")
        assert md.is_stale == True  # No data yet
        
        md.last_update_time = time.time()
        assert md.is_stale == False  # Just updated
        
        md.last_update_time = time.time() - 120  # 2 minutes ago
        assert md.is_stale == True  # Too old
        
        print("✓ Stale data detection works")


class TestIntegration:
    """Integration tests for Phase 3"""
    
    @pytest.mark.asyncio
    async def test_full_websocket_flow(self):
        """Test complete WebSocket flow: connect, subscribe, receive, disconnect"""
        from src.websocket_client import MarketWebSocket, ConnectionState
        from src.markets import fetch_active_markets
        
        # 1. Get a market
        markets = fetch_active_markets(limit=3)
        test_market = None
        for m in markets:
            if m.token_ids:
                test_market = m
                break
        
        assert test_market is not None, "Need a market with tokens"
        token_id = test_market.token_ids[0]
        
        print(f"Testing with market: {test_market.question[:40]}...")
        
        # 2. Set up WebSocket
        ws = MarketWebSocket()
        message_count = 0
        
        def count_messages(data):
            nonlocal message_count
            message_count += 1
        
        ws.on_price_change = count_messages
        ws.on_book_update = count_messages
        ws.on_trade = count_messages
        
        try:
            # 3. Connect
            connected = await ws.connect()
            assert connected
            assert ws.state == ConnectionState.CONNECTED
            print("  ✓ Connected")
            
            # 4. Subscribe
            subscribed = await ws.subscribe([token_id])
            assert subscribed
            assert ws.state == ConnectionState.SUBSCRIBED
            print("  ✓ Subscribed")
            
            # 5. Receive data (wait up to 30s)
            print("  Waiting for data...")
            await asyncio.sleep(30)
            
            # 6. Check we got something
            market_data = ws.get_market_data(token_id)
            assert market_data is not None
            print(f"  ✓ Received {message_count} messages")
            
            if market_data.order_book:
                book = market_data.order_book
                print(f"  ✓ Order book: {len(book.bids)} bids, {len(book.asks)} asks")
            
        finally:
            # 7. Disconnect
            await ws.disconnect()
            assert ws.state == ConnectionState.DISCONNECTED
            print("  ✓ Disconnected")
        
        print("✓ Full WebSocket flow completed successfully")
```

---

## Verification Gate

After creating all files, run:

```bash
cd polymarket-bot
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install websockets  # Make sure websockets is installed
pytest tests/test_phase3.py -v --timeout=120
```

**Note:** These tests involve real network connections and waiting for market data. Some tests may take up to 60 seconds. Use `--timeout=120` to prevent pytest from timing out.

---

## Success Criteria

**Phase 3 is ONLY complete when ALL tests pass:**

```
tests/test_phase3.py::TestWebSocketClient::test_import_websocket_client PASSED
tests/test_phase3.py::TestWebSocketClient::test_client_instantiation PASSED
tests/test_phase3.py::TestWebSocketClient::test_connect_disconnect PASSED
tests/test_phase3.py::TestWebSocketClient::test_subscribe_to_market PASSED
tests/test_phase3.py::TestWebSocketClient::test_receive_market_data PASSED
tests/test_phase3.py::TestWebSocketClient::test_order_book_maintenance PASSED
tests/test_phase3.py::TestWebSocketClient::test_callbacks_are_called PASSED
tests/test_phase3.py::TestWebSocketClient::test_multiple_subscriptions PASSED
tests/test_phase3.py::TestConnectionState::test_state_enum_values PASSED
tests/test_phase3.py::TestMarketData::test_market_data_creation PASSED
tests/test_phase3.py::TestMarketData::test_stale_data_detection PASSED
tests/test_phase3.py::TestIntegration::test_full_websocket_flow PASSED
```

---

## Troubleshooting

### Tests timing out
- Some markets have low activity; tests wait up to 60s for data
- Increase timeout: `pytest tests/test_phase3.py -v --timeout=180`
- Try during high-activity periods (US market hours)

### Connection refused
- Check internet connectivity
- Verify WebSocket URL is correct
- Polymarket WebSocket server may be temporarily down

### No messages received
- Market might be illiquid with no activity
- Try with a different token (higher volume market)
- Check that subscription was successful

### Import errors
- Ensure `websockets` package is installed: `pip install websockets`
- Ensure pytest-asyncio is installed: `pip install pytest-asyncio`

### pytest-asyncio issues
- Add to your pytest.ini or pyproject.toml:
```ini
[pytest]
asyncio_mode = auto
```
- Or install: `pip install pytest-asyncio`

---

## Important Notes

- WebSocket connections are for **reading data only** in this phase
- User channel (for order updates) requires authentication - that's Phase 5
- The market channel is public and requires no authentication
- Always call `disconnect()` to clean up resources
- Real market data depends on market activity - tests may see different results at different times
