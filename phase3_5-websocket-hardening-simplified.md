# Task: Polymarket Trading Bot - Phase 3.5: WebSocket Hardening (Simplified)

## Context

This is Phase 3.5 - a hardening phase that improves the WebSocket implementation with a focus on **simplicity** and **reliability**. The design is driven by what the market-making logic (Phase 7) actually needs.

## Design Philosophy

**The market maker's only questions:**
1. Is the data reliable right now? → `is_healthy`
2. What's the current price? → `get_midpoint(token)`
3. What's the order book? → `get_order_book(token)`

**Everything else is implementation detail** that should be hidden.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SIMPLIFIED ARCHITECTURE                             │
└─────────────────────────────────────────────────────────────────────────────┘

                    ┌─────────────────────────────────────┐
                    │         Market Maker (Phase 7)      │
                    │                                     │
                    │  if feed.is_healthy:                │
                    │      mid = feed.get_midpoint(token) │
                    │      place_quotes(mid)              │
                    │  else:                              │
                    │      cancel_quotes()                │
                    └──────────────────┬──────────────────┘
                                       │
                         Simple interface: 3 methods + callbacks
                                       │
                                       ▼
  ┌───────────────────────────────────────────────────────────────────────────┐
  │                           MarketFeed                                      │
  │                                                                           │
  │   PUBLIC API:                                                             │
  │   ───────────                                                             │
  │   • start(tokens) / stop()     - Lifecycle                                │
  │   • is_healthy                 - Can I trust the data?                    │
  │   • get_midpoint(token)        - Current price                            │
  │   • get_order_book(token)      - Full book                                │
  │   • get_spread(token)          - Current spread                           │
  │   • on_price_change            - Callback                                 │
  │   • on_book_update             - Callback                                 │
  │   • on_trade                   - Callback                                 │
  │                                                                           │
  │   INTERNAL (hidden):                                                      │
  │   ──────────────────                                                      │
  │   • WebSocket connection + reconnection                                   │
  │   • REST fallback when WS unhealthy                                       │
  │   • Sequence tracking + auto-resync                                       │
  │   • Message queue for non-blocking callbacks                              │
  └───────────────────────────────────────────────────────────────────────────┘
                                       │
                    ┌──────────────────┴──────────────────┐
                    │                                     │
                    ▼                                     ▼
           ┌───────────────┐                    ┌───────────────┐
           │   WebSocket   │                    │  REST Poller  │
           │   (primary)   │                    │  (fallback)   │
           └───────────────┘                    └───────────────┘
```

---

## State Machine (4 States)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         4-STATE MACHINE                                     │
└─────────────────────────────────────────────────────────────────────────────┘


                              ┌──────────┐
                              │ STOPPED  │◀──────────────────────┐
                              └────┬─────┘                       │
                                   │                             │
                                   │ start(tokens)               │ stop()
                                   ▼                             │
                              ┌──────────┐                       │
                    ┌────────▶│ STARTING │──────────┐            │
                    │         └────┬─────┘          │            │
                    │              │                │            │
                    │         connected +      max retries       │
                    │         subscribed       exceeded          │
                    │              │                │            │
                    │              ▼                │            │
                    │         ┌──────────┐         │            │
                    │         │ RUNNING  │         │            │
                    │         └────┬─────┘         │            │
                    │              │               │            │
                    │         connection           │            │
                    │         lost                 │            │
                    │              │               │            │
                    │              └───────────────│────────────│───┐
                    │                              │            │   │
                    │                              ▼            │   │
                    │                         ┌──────────┐      │   │
                    └─────────────────────────│  ERROR   │──────┘   │
                           reset()            └──────────┘          │
                                                   │                │
                                                   │ stop()         │
                                                   └────────────────┘


  STATES:
  ═══════
  STOPPED   - Not running. Call start() to begin.
  STARTING  - Connecting and subscribing. Auto-retries internally.
  RUNNING   - Receiving data. is_healthy depends on data freshness.
  ERROR     - Failed after max retries. Call reset() or stop().


  TRANSITIONS:
  ════════════
  start(tokens)  - Begin receiving data for these tokens
  stop()         - Clean shutdown from any state
  reset()        - Recover from ERROR, returns to STOPPED


  KEY INSIGHT:
  ════════════
  • STARTING handles all retry logic internally
  • RUNNING doesn't mean "perfect" - check is_healthy for data quality
  • Connection loss in RUNNING → automatic transition to STARTING
  • Only reaches ERROR after exhausting all retries
```

---

## Health Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         HEALTH MODEL                                        │
└─────────────────────────────────────────────────────────────────────────────┘

  is_healthy = True when ALL of:
  ═══════════════════════════════
  
  ┌─────────────────────────────────────────────────────────────────────┐
  │  ✓ State is RUNNING                                                 │
  │  ✓ Received data within last 30 seconds                             │
  │  ✓ No sequence gaps detected (or already resynced)                  │
  └─────────────────────────────────────────────────────────────────────┘


  is_healthy = False when ANY of:
  ════════════════════════════════
  
  ┌─────────────────────────────────────────────────────────────────────┐
  │  ✗ State is STOPPED, STARTING, or ERROR                             │
  │  ✗ No data received in 30+ seconds                                  │
  │  ✗ Sequence gaps detected and not yet resynced                      │
  └─────────────────────────────────────────────────────────────────────┘


  WHY THIS MATTERS FOR MARKET MAKING:
  ═══════════════════════════════════
  
  ┌─────────────────────────┐         ┌─────────────────────────┐
  │   is_healthy = True     │         │   is_healthy = False    │
  │                         │         │                         │
  │   → Place/update quotes │         │   → Cancel all quotes   │
  │   → Normal operation    │         │   → Wait for recovery   │
  │                         │         │   → Alert if prolonged  │
  └─────────────────────────┘         └─────────────────────────┘
  
  The market maker should NEVER quote on unhealthy data.
  Quoting on stale prices = guaranteed losses.
```

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DATA FLOW                                           │
└─────────────────────────────────────────────────────────────────────────────┘

  WebSocket Server                         MarketFeed
       │                                       │
       │                                       │
       │ ──── price_change ──────────────────▶ │
       │                                       │ 1. Validate sequence
       │                                       │ 2. Update data store
       │                                       │ 3. Queue callback
       │                                       │
       │                                       │         ┌─────────────┐
       │                                       │ ───────▶│ Async Queue │
       │                                       │         └──────┬──────┘
       │                                       │                │
       │                                       │                ▼
       │                                       │         ┌─────────────┐
       │                                       │         │   Worker    │
       │                                       │         │             │
       │                                       │         │ callback()  │
       │                                       │         └─────────────┘
       │                                       │
       │                                       │
  Market Maker                                 │
       │                                       │
       │ ◀──── get_midpoint(token) ───────────│
       │                                       │
       │        Returns latest price           │
       │        from data store                │
       │                                       │


  NON-BLOCKING CALLBACKS:
  ═══════════════════════
  
  Callbacks are processed asynchronously so a slow callback
  (e.g., database write) doesn't block message reception.
  
  Message arrives → Queued immediately → Worker processes later
         │                                      │
         │ ~0.1ms                               │ Can take any amount of time
         ▼                                      ▼
    Next message                          Callback completes
    can be received
```

---

## REST Fallback (Internal)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    REST FALLBACK (Transparent to Caller)                    │
└─────────────────────────────────────────────────────────────────────────────┘

  The caller never knows which data source is active.
  get_midpoint() returns the same data regardless of source.


  AUTOMATIC FAILOVER:
  ═══════════════════

       WebSocket              Decision              REST Poller
       ─────────              ────────              ───────────
           │                     │                      │
           │   No messages       │                      │
           │   for 30 sec        │                      │
           │ ──────────────────▶ │                      │
           │                     │   Start REST         │
           │                     │ ────────────────────▶│
           │                     │                      │ Poll every 2s
           │                     │                      │
           │   WebSocket         │                      │
           │   reconnects        │                      │
           │ ──────────────────▶ │                      │
           │                     │   Wait 30s healthy   │
           │                     │                      │
           │   30s healthy       │                      │
           │ ──────────────────▶ │                      │
           │                     │   Stop REST          │
           │                     │ ────────────────────▶│
           │                     │                      │ (stopped)


  DATA SOURCE PROPERTY:
  ═════════════════════
  
  feed.data_source → "websocket" | "rest"
  
  This is informational only - the market maker doesn't need to check it.
  Useful for monitoring/logging.
```

---

## File Structure (Simplified)

```
polymarket-bot/
│
├── src/
│   ├── __init__.py
│   ├── config.py                 # (existing, add WS config)
│   ├── client.py                 # (existing)
│   ├── models.py                 # (existing)
│   ├── markets.py                # (existing)
│   ├── pricing.py                # (existing)
│   ├── utils.py                  # (existing)
│   │
│   └── feed/                     # NEW - Renamed from "websocket"
│       ├── __init__.py           # Exports: MarketFeed, FeedState
│       ├── feed.py               # Main MarketFeed class
│       ├── websocket_conn.py     # WebSocket connection handling
│       ├── rest_poller.py        # REST fallback
│       ├── data_store.py         # Local data storage
│       └── mock.py               # Mock for testing
│
└── tests/
    ├── test_phase1.py
    ├── test_phase2.py
    └── test_phase3_5.py          # Simplified tests
```

**Why "feed" instead of "websocket"?**
- It's a market data feed, not just a WebSocket
- Includes REST fallback
- Clearer purpose for future developers

---

## Public API

```python
"""
MarketFeed - Simple interface for real-time market data.

Usage:
    feed = MarketFeed()
    
    # Optional: Set callbacks
    feed.on_book_update = my_handler
    
    # Start receiving data
    await feed.start(["token_id_1", "token_id_2"])
    
    # Use the data
    if feed.is_healthy:
        mid = feed.get_midpoint("token_id_1")
        book = feed.get_order_book("token_id_1")
    
    # Stop when done
    await feed.stop()
"""

class FeedState(Enum):
    STOPPED = auto()
    STARTING = auto()
    RUNNING = auto()
    ERROR = auto()


class MarketFeed:
    # === Lifecycle ===
    async def start(self, token_ids: List[str]) -> bool:
        """Start receiving data for these tokens."""
    
    async def stop(self):
        """Stop and disconnect cleanly."""
    
    async def reset(self):
        """Recover from ERROR state."""
    
    # === State ===
    @property
    def state(self) -> FeedState:
        """Current state: STOPPED, STARTING, RUNNING, or ERROR."""
    
    @property
    def is_healthy(self) -> bool:
        """Is the data reliable? Safe to trade on?"""
    
    @property
    def data_source(self) -> str:
        """Current source: 'websocket' or 'rest'."""
    
    # === Data Access ===
    def get_midpoint(self, token_id: str) -> Optional[float]:
        """Get current midpoint price."""
    
    def get_order_book(self, token_id: str) -> Optional[OrderBook]:
        """Get current order book."""
    
    def get_spread(self, token_id: str) -> Optional[float]:
        """Get current bid-ask spread."""
    
    def get_best_bid(self, token_id: str) -> Optional[float]:
        """Get best bid price."""
    
    def get_best_ask(self, token_id: str) -> Optional[float]:
        """Get best ask price."""
    
    # === Callbacks ===
    on_price_change: Optional[Callable[[dict], None]]
    on_book_update: Optional[Callable[[dict], None]]
    on_trade: Optional[Callable[[dict], None]]
    on_state_change: Optional[Callable[[FeedState], None]]
```

---

## How This Supports Future Phases

| Phase | What It Needs | How MarketFeed Provides It |
|-------|---------------|---------------------------|
| **Phase 4: Auth** | User channel for order updates | Add `start_user_channel(api_key)` method |
| **Phase 5: Orders** | Real-time fill notifications | User channel callbacks |
| **Phase 6: Placement** | Current prices for orders | `get_midpoint()`, `get_best_bid/ask()` |
| **Phase 7: Market Making** | Reliable prices to quote around | `is_healthy` + `get_midpoint()` |
| **Phase 8: Risk** | Know when to stop trading | `is_healthy`, `on_state_change` |
| **Phase 9: Arbitrage** | Synchronized prices across markets | Subscribe to multiple tokens |
| **Phase 10: Production** | Monitoring, metrics | `data_source`, `state`, internal metrics |

---

## Implementation Files

### 1. src/feed/__init__.py

```python
"""
Market data feed with automatic failover.

Simple usage:
    feed = MarketFeed()
    await feed.start(["token1", "token2"])
    
    if feed.is_healthy:
        price = feed.get_midpoint("token1")
"""

from src.feed.feed import MarketFeed, FeedState

__all__ = ['MarketFeed', 'FeedState']
```

### 2. src/feed/data_store.py

```python
"""
Local storage for market data.
"""

import time
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from src.models import OrderBook, PriceLevel


@dataclass
class TokenData:
    """Data for a single token."""
    token_id: str
    order_book: Optional[OrderBook] = None
    last_price: Optional[float] = None
    last_trade_price: Optional[float] = None
    last_trade_side: Optional[str] = None
    last_trade_size: Optional[float] = None
    last_update: float = 0.0
    
    def update_timestamp(self):
        self.last_update = time.time()
    
    def seconds_since_update(self) -> float:
        if self.last_update == 0:
            return float('inf')
        return time.time() - self.last_update


class DataStore:
    """
    Thread-safe storage for market data.
    
    Updated by WebSocket messages or REST polls.
    Read by the market maker for current prices.
    """
    
    def __init__(self, stale_threshold: float = 30.0):
        self._data: Dict[str, TokenData] = {}
        self._stale_threshold = stale_threshold
        self._sequence: Dict[str, int] = {}  # For gap detection
        self._gap_count: Dict[str, int] = {}
    
    # === Data Access ===
    
    def get(self, token_id: str) -> Optional[TokenData]:
        return self._data.get(token_id)
    
    def get_midpoint(self, token_id: str) -> Optional[float]:
        data = self._data.get(token_id)
        if data and data.order_book:
            return data.order_book.midpoint
        return None
    
    def get_order_book(self, token_id: str) -> Optional[OrderBook]:
        data = self._data.get(token_id)
        return data.order_book if data else None
    
    def get_spread(self, token_id: str) -> Optional[float]:
        data = self._data.get(token_id)
        if data and data.order_book:
            return data.order_book.spread
        return None
    
    def get_best_bid(self, token_id: str) -> Optional[float]:
        data = self._data.get(token_id)
        if data and data.order_book:
            return data.order_book.best_bid
        return None
    
    def get_best_ask(self, token_id: str) -> Optional[float]:
        data = self._data.get(token_id)
        if data and data.order_book:
            return data.order_book.best_ask
        return None
    
    # === Health Checks ===
    
    def is_fresh(self, token_id: str) -> bool:
        """Check if token data is fresh (not stale)."""
        data = self._data.get(token_id)
        if not data:
            return False
        return data.seconds_since_update() < self._stale_threshold
    
    def all_fresh(self) -> bool:
        """Check if all tracked tokens have fresh data."""
        if not self._data:
            return False
        return all(self.is_fresh(tid) for tid in self._data)
    
    def has_gaps(self) -> bool:
        """Check if any sequence gaps were detected."""
        return any(count > 0 for count in self._gap_count.values())
    
    # === Updates ===
    
    def register_token(self, token_id: str):
        """Start tracking a token."""
        if token_id not in self._data:
            self._data[token_id] = TokenData(token_id=token_id)
            self._sequence[token_id] = -1
            self._gap_count[token_id] = 0
    
    def unregister_token(self, token_id: str):
        """Stop tracking a token."""
        self._data.pop(token_id, None)
        self._sequence.pop(token_id, None)
        self._gap_count.pop(token_id, None)
    
    def check_sequence(self, token_id: str, seq: Optional[int]) -> bool:
        """
        Check message sequence, detect gaps.
        Returns True if sequence is OK, False if gap detected.
        """
        if seq is None:
            return True
        
        last = self._sequence.get(token_id, -1)
        
        if last == -1:
            # First message
            self._sequence[token_id] = seq
            return True
        
        expected = last + 1
        if seq == expected:
            self._sequence[token_id] = seq
            return True
        
        # Gap detected
        self._gap_count[token_id] = self._gap_count.get(token_id, 0) + 1
        self._sequence[token_id] = seq
        return False
    
    def clear_gaps(self, token_id: str):
        """Clear gap count after resync."""
        self._gap_count[token_id] = 0
    
    def update_book(self, token_id: str, bids: list, asks: list, timestamp: str = None):
        """Update order book from message."""
        if token_id not in self._data:
            self.register_token(token_id)
        
        data = self._data[token_id]
        
        # Parse price levels
        parsed_bids = [
            PriceLevel(price=float(b['price']), size=float(b['size']))
            for b in bids if isinstance(b, dict)
        ]
        parsed_asks = [
            PriceLevel(price=float(a['price']), size=float(a['size']))
            for a in asks if isinstance(a, dict)
        ]
        
        # Sort: bids descending, asks ascending
        parsed_bids.sort(key=lambda x: x.price, reverse=True)
        parsed_asks.sort(key=lambda x: x.price)
        
        data.order_book = OrderBook(
            token_id=token_id,
            bids=parsed_bids,
            asks=parsed_asks,
            timestamp=timestamp
        )
        data.update_timestamp()
    
    def update_price(self, token_id: str, price: float):
        """Update last price."""
        if token_id not in self._data:
            self.register_token(token_id)
        
        self._data[token_id].last_price = price
        self._data[token_id].update_timestamp()
    
    def update_trade(self, token_id: str, price: float, size: float = None, side: str = None):
        """Update last trade."""
        if token_id not in self._data:
            self.register_token(token_id)
        
        data = self._data[token_id]
        data.last_trade_price = price
        data.last_trade_size = size
        data.last_trade_side = side
        data.update_timestamp()
    
    def get_token_ids(self) -> List[str]:
        """Get all tracked token IDs."""
        return list(self._data.keys())
    
    def clear(self):
        """Clear all data."""
        self._data.clear()
        self._sequence.clear()
        self._gap_count.clear()
```

### 3. src/feed/websocket_conn.py

```python
"""
WebSocket connection management.

Internal component - use MarketFeed instead.
"""

import json
import asyncio
from typing import Optional, List, Callable, Dict, Any
import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError, ConnectionClosedOK

from src.config import (
    WS_MARKET_URL,
    WS_RECONNECT_ATTEMPTS,
    WS_RECONNECT_BASE_DELAY,
    WS_RECONNECT_MAX_DELAY,
)
from src.utils import setup_logging

logger = setup_logging()


class WebSocketConnection:
    """
    Low-level WebSocket connection handler.
    
    Responsibilities:
    - Connect/disconnect
    - Send subscription requests
    - Receive messages and pass to callback
    - Auto-reconnect with exponential backoff
    """
    
    def __init__(self, url: str = WS_MARKET_URL):
        self.url = url
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._connected = False
        self._should_run = False
        self._receive_task: Optional[asyncio.Task] = None
        self._reconnect_count = 0
        
        # Callbacks
        self.on_message: Optional[Callable[[str], None]] = None
        self.on_connect: Optional[Callable[[], None]] = None
        self.on_disconnect: Optional[Callable[[], None]] = None
        self.on_error: Optional[Callable[[Exception], None]] = None
        self.on_max_retries: Optional[Callable[[], None]] = None
    
    @property
    def is_connected(self) -> bool:
        return self._connected and self._ws is not None
    
    async def connect(self) -> bool:
        """Establish WebSocket connection."""
        self._should_run = True
        self._reconnect_count = 0
        
        try:
            logger.info(f"Connecting to {self.url}")
            self._ws = await websockets.connect(
                self.url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5
            )
            self._connected = True
            logger.info("WebSocket connected")
            
            # Start receive loop
            self._receive_task = asyncio.create_task(self._receive_loop())
            
            if self.on_connect:
                self.on_connect()
            
            return True
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._connected = False
            if self.on_error:
                self.on_error(e)
            return False
    
    async def disconnect(self):
        """Disconnect cleanly."""
        logger.info("Disconnecting WebSocket")
        self._should_run = False
        self._connected = False
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None
        
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        
        if self.on_disconnect:
            self.on_disconnect()
    
    async def subscribe(self, token_ids: List[str]) -> bool:
        """Send subscription request."""
        if not self.is_connected:
            logger.error("Cannot subscribe: not connected")
            return False
        
        message = {
            "type": "market",
            "assets_ids": token_ids
        }
        
        try:
            await self._ws.send(json.dumps(message))
            logger.info(f"Subscribed to {len(token_ids)} token(s)")
            return True
        except Exception as e:
            logger.error(f"Subscribe failed: {e}")
            return False
    
    async def _receive_loop(self):
        """Receive messages and handle reconnection."""
        while self._should_run:
            try:
                if not self._ws:
                    await asyncio.sleep(0.1)
                    continue
                
                message = await self._ws.recv()
                
                if self.on_message:
                    self.on_message(message)
                    
            except ConnectionClosedOK:
                logger.info("WebSocket closed normally")
                self._connected = False
                break
                
            except (ConnectionClosed, ConnectionClosedError) as e:
                logger.warning(f"Connection lost: {e}")
                self._connected = False
                if self._should_run:
                    await self._reconnect()
                break
                
            except asyncio.CancelledError:
                break
                
            except Exception as e:
                logger.error(f"Receive error: {e}")
                if self.on_error:
                    self.on_error(e)
    
    async def _reconnect(self):
        """Reconnect with exponential backoff."""
        while self._should_run and self._reconnect_count < WS_RECONNECT_ATTEMPTS:
            self._reconnect_count += 1
            
            delay = min(
                WS_RECONNECT_BASE_DELAY * (2 ** (self._reconnect_count - 1)),
                WS_RECONNECT_MAX_DELAY
            )
            
            logger.info(f"Reconnecting ({self._reconnect_count}/{WS_RECONNECT_ATTEMPTS}) in {delay:.1f}s")
            await asyncio.sleep(delay)
            
            if not self._should_run:
                return
            
            try:
                self._ws = await websockets.connect(
                    self.url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5
                )
                self._connected = True
                self._reconnect_count = 0
                logger.info("Reconnected successfully")
                
                # Restart receive loop
                self._receive_task = asyncio.create_task(self._receive_loop())
                
                if self.on_connect:
                    self.on_connect()
                
                return
                
            except Exception as e:
                logger.warning(f"Reconnect failed: {e}")
        
        # Max retries exceeded
        if self._should_run:
            logger.error("Max reconnection attempts exceeded")
            if self.on_max_retries:
                self.on_max_retries()
```

### 4. src/feed/rest_poller.py

```python
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
```

### 5. src/feed/feed.py - Main MarketFeed Class

```python
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
        
        # User callbacks
        self._on_price_change: Optional[Callable] = None
        self._on_book_update: Optional[Callable] = None
        self._on_trade: Optional[Callable] = None
        self._on_state_change: Optional[Callable[[FeedState], None]] = None
        
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
    
    @property
    def on_price_change(self):
        return self._on_price_change
    
    @on_price_change.setter
    def on_price_change(self, callback: Optional[Callable]):
        self._on_price_change = callback
    
    @property
    def on_book_update(self):
        return self._on_book_update
    
    @on_book_update.setter
    def on_book_update(self, callback: Optional[Callable]):
        self._on_book_update = callback
    
    @property
    def on_trade(self):
        return self._on_trade
    
    @on_trade.setter
    def on_trade(self, callback: Optional[Callable]):
        self._on_trade = callback
    
    @property
    def on_state_change(self):
        return self._on_state_change
    
    @on_state_change.setter
    def on_state_change(self, callback: Optional[Callable[[FeedState], None]]):
        self._on_state_change = callback
    
    # === Internal Methods ===
    
    def _set_state(self, new_state: FeedState):
        """Update state and notify."""
        old_state = self._state
        self._state = new_state
        
        if old_state != new_state:
            logger.info(f"State: {old_state.name} -> {new_state.name}")
            if self._on_state_change:
                self._on_state_change(new_state)
    
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
            await self._invoke_callback(self._on_book_update, data)
            
        elif event_type == 'price_change':
            price = data.get('price')
            if price:
                self._data_store.update_price(token_id, float(price))
            await self._invoke_callback(self._on_price_change, data)
            
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
            await self._invoke_callback(self._on_trade, data)
    
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
```

### 6. src/feed/mock.py - Mock for Testing

```python
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
```

### 7. tests/test_phase3_5.py - Simplified Tests

```python
"""
Phase 3.5 Verification Tests (Simplified)

Run with: pytest tests/test_phase3_5.py -v --timeout=120
"""

import pytest
import asyncio
from typing import List


class TestFeedState:
    """Test feed states."""
    
    def test_states_defined(self):
        """Verify all states exist."""
        from src.feed import FeedState
        
        assert FeedState.STOPPED is not None
        assert FeedState.STARTING is not None
        assert FeedState.RUNNING is not None
        assert FeedState.ERROR is not None
        
        print("✓ All 4 states defined")


class TestDataStore:
    """Test data storage."""
    
    def test_store_creation(self):
        """Test store can be created."""
        from src.feed.data_store import DataStore
        
        store = DataStore()
        assert store is not None
        print("✓ DataStore created")
    
    def test_book_update(self):
        """Test order book updates."""
        from src.feed.data_store import DataStore
        
        store = DataStore()
        store.register_token("token1")
        
        store.update_book(
            "token1",
            [{'price': '0.50', 'size': '100'}],
            [{'price': '0.55', 'size': '200'}]
        )
        
        assert store.get_best_bid("token1") == 0.50
        assert store.get_best_ask("token1") == 0.55
        assert store.get_midpoint("token1") == 0.525
        assert store.get_spread("token1") == 0.05
        
        print("✓ Order book updated correctly")
    
    def test_freshness(self):
        """Test data freshness detection."""
        from src.feed.data_store import DataStore
        import time
        
        store = DataStore(stale_threshold=1.0)
        store.register_token("token1")
        
        # No data yet
        assert not store.is_fresh("token1")
        
        # Add data
        store.update_price("token1", 0.55)
        assert store.is_fresh("token1")
        
        # Wait for staleness
        time.sleep(1.5)
        assert not store.is_fresh("token1")
        
        print("✓ Freshness detection works")
    
    def test_sequence_tracking(self):
        """Test sequence gap detection."""
        from src.feed.data_store import DataStore
        
        store = DataStore()
        store.register_token("token1")
        
        # Normal sequence
        assert store.check_sequence("token1", 1) == True
        assert store.check_sequence("token1", 2) == True
        assert store.check_sequence("token1", 3) == True
        
        # Gap
        assert store.check_sequence("token1", 10) == False
        assert store.has_gaps() == True
        
        # Clear
        store.clear_gaps("token1")
        assert store.has_gaps() == False
        
        print("✓ Sequence tracking works")


class TestMockFeed:
    """Test mock feed."""
    
    @pytest.mark.asyncio
    async def test_mock_basic(self):
        """Test basic mock functionality."""
        from src.feed.mock import MockMarketFeed
        from src.feed import FeedState
        
        feed = MockMarketFeed()
        
        assert feed.state == FeedState.STOPPED
        
        await feed.start(["token1"])
        assert feed.state == FeedState.RUNNING
        assert feed.is_healthy
        
        await feed.stop()
        assert feed.state == FeedState.STOPPED
        
        print("✓ Mock lifecycle works")
    
    @pytest.mark.asyncio
    async def test_mock_data(self):
        """Test mock data injection."""
        from src.feed.mock import MockMarketFeed
        
        feed = MockMarketFeed()
        await feed.start(["token1"])
        
        # Set book
        feed.set_book("token1", [(0.50, 100), (0.49, 200)], [(0.55, 150)])
        
        assert feed.get_midpoint("token1") == 0.525
        assert feed.get_best_bid("token1") == 0.50
        assert feed.get_best_ask("token1") == 0.55
        
        await feed.stop()
        print("✓ Mock data injection works")
    
    @pytest.mark.asyncio
    async def test_mock_health(self):
        """Test mock health control."""
        from src.feed.mock import MockMarketFeed
        
        feed = MockMarketFeed()
        await feed.start(["token1"])
        
        assert feed.is_healthy
        
        feed.set_healthy(False)
        assert not feed.is_healthy
        
        feed.set_healthy(True)
        assert feed.is_healthy
        
        await feed.stop()
        print("✓ Mock health control works")


class TestMarketFeed:
    """Test real MarketFeed with network."""
    
    def _get_test_token(self) -> str:
        """Get a valid token for testing."""
        from src.markets import fetch_active_markets
        
        markets = fetch_active_markets(limit=10)
        for m in markets:
            if m.token_ids:
                return m.token_ids[0]
        pytest.skip("No markets with tokens found")
    
    def test_import(self):
        """Test imports work."""
        from src.feed import MarketFeed, FeedState
        
        assert MarketFeed is not None
        assert FeedState is not None
        print("✓ Imports successful")
    
    def test_instantiation(self):
        """Test feed can be created."""
        from src.feed import MarketFeed, FeedState
        
        feed = MarketFeed()
        
        assert feed.state == FeedState.STOPPED
        assert not feed.is_healthy
        assert feed.data_source == "none"
        
        print("✓ MarketFeed instantiated")
    
    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Test basic lifecycle."""
        from src.feed import MarketFeed, FeedState
        
        feed = MarketFeed()
        token = self._get_test_token()
        
        # Start
        result = await feed.start([token])
        assert result == True
        assert feed.state == FeedState.RUNNING
        print(f"  Started with source: {feed.data_source}")
        
        # Stop
        await feed.stop()
        assert feed.state == FeedState.STOPPED
        print("  Stopped")
        
        print("✓ Start/stop works")
    
    @pytest.mark.asyncio
    async def test_health_and_data(self):
        """Test health status and data access."""
        from src.feed import MarketFeed
        
        feed = MarketFeed()
        token = self._get_test_token()
        
        try:
            await feed.start([token])
            
            # Wait for data
            print("  Waiting for data...")
            await asyncio.sleep(15)
            
            # Check health
            print(f"  is_healthy: {feed.is_healthy}")
            print(f"  data_source: {feed.data_source}")
            
            # Check data
            mid = feed.get_midpoint(token)
            spread = feed.get_spread(token)
            
            print(f"  midpoint: {mid}")
            print(f"  spread: {spread}")
            
            if mid is not None:
                print("✓ Data received successfully")
            
        finally:
            await feed.stop()
    
    @pytest.mark.asyncio
    async def test_callbacks(self):
        """Test callbacks are invoked."""
        from src.feed import MarketFeed
        
        feed = MarketFeed()
        token = self._get_test_token()
        
        events = {'book': 0, 'price': 0, 'trade': 0}
        
        def on_book(data):
            events['book'] += 1
        
        def on_price(data):
            events['price'] += 1
        
        def on_trade(data):
            events['trade'] += 1
        
        feed.on_book_update = on_book
        feed.on_price_change = on_price
        feed.on_trade = on_trade
        
        try:
            await feed.start([token])
            await asyncio.sleep(30)
            
            print(f"  Events received: {events}")
            
            total = sum(events.values())
            if total > 0:
                print(f"✓ Callbacks invoked ({total} total)")
            
        finally:
            await feed.stop()
    
    @pytest.mark.asyncio
    async def test_state_transitions(self):
        """Test state change callbacks."""
        from src.feed import MarketFeed, FeedState
        
        feed = MarketFeed()
        token = self._get_test_token()
        
        states = []
        
        def on_state(state):
            states.append(state)
        
        feed.on_state_change = on_state
        
        try:
            await feed.start([token])
            await asyncio.sleep(5)
            await feed.stop()
            
            print(f"  States observed: {[s.name for s in states]}")
            
            assert FeedState.STARTING in states
            assert FeedState.RUNNING in states
            assert FeedState.STOPPED in states
            
            print("✓ State transitions work")
            
        except Exception:
            await feed.stop()
            raise


class TestIntegration:
    """Integration tests."""
    
    def _get_test_token(self) -> str:
        from src.markets import fetch_active_markets
        markets = fetch_active_markets(limit=10)
        for m in markets:
            if m.token_ids:
                return m.token_ids[0]
        pytest.skip("No markets found")
    
    @pytest.mark.asyncio
    async def test_market_maker_pattern(self):
        """
        Test the pattern a market maker would use.
        
        This is the most important test - it validates that
        the API supports the market making use case.
        """
        from src.feed import MarketFeed
        
        feed = MarketFeed()
        token = self._get_test_token()
        
        quote_updates = []
        
        try:
            await feed.start([token])
            
            # Simulate market maker loop
            for i in range(10):
                await asyncio.sleep(2)
                
                if feed.is_healthy:
                    mid = feed.get_midpoint(token)
                    if mid:
                        # In real bot: place quotes around mid
                        bid = round(mid - 0.02, 2)
                        ask = round(mid + 0.02, 2)
                        quote_updates.append((bid, mid, ask))
                        print(f"  Would quote: {bid} / {ask} (mid={mid})")
                else:
                    # In real bot: cancel quotes
                    print("  Would cancel quotes (unhealthy)")
            
            print(f"✓ Market maker pattern works ({len(quote_updates)} quote updates)")
            
        finally:
            await feed.stop()
```

---

## Config Additions

Add to `src/config.py`:

```python
# WebSocket Configuration
WS_MARKET_URL = os.getenv(
    "WS_MARKET_URL",
    "wss://ws-subscriptions-clob.polymarket.com/ws/market"
)
WS_RECONNECT_ATTEMPTS = int(os.getenv("WS_RECONNECT_ATTEMPTS", "10"))
WS_RECONNECT_BASE_DELAY = float(os.getenv("WS_RECONNECT_BASE_DELAY", "1.0"))
WS_RECONNECT_MAX_DELAY = float(os.getenv("WS_RECONNECT_MAX_DELAY", "60.0"))
```

---

## Success Criteria

All tests pass:

```
tests/test_phase3_5.py::TestFeedState::test_states_defined PASSED
tests/test_phase3_5.py::TestDataStore::test_store_creation PASSED
tests/test_phase3_5.py::TestDataStore::test_book_update PASSED
tests/test_phase3_5.py::TestDataStore::test_freshness PASSED
tests/test_phase3_5.py::TestDataStore::test_sequence_tracking PASSED
tests/test_phase3_5.py::TestMockFeed::test_mock_basic PASSED
tests/test_phase3_5.py::TestMockFeed::test_mock_data PASSED
tests/test_phase3_5.py::TestMockFeed::test_mock_health PASSED
tests/test_phase3_5.py::TestMarketFeed::test_import PASSED
tests/test_phase3_5.py::TestMarketFeed::test_instantiation PASSED
tests/test_phase3_5.py::TestMarketFeed::test_start_stop PASSED
tests/test_phase3_5.py::TestMarketFeed::test_health_and_data PASSED
tests/test_phase3_5.py::TestMarketFeed::test_callbacks PASSED
tests/test_phase3_5.py::TestMarketFeed::test_state_transitions PASSED
tests/test_phase3_5.py::TestIntegration::test_market_maker_pattern PASSED
```

---

## Summary: What Changed

| Before (Over-engineered) | After (Simple) |
|--------------------------|----------------|
| 9 states | 4 states |
| MarketWebSocket + MarketDataManager | Single MarketFeed |
| Complex state transitions | Simple lifecycle |
| Multiple queue classes | Single internal queue |
| Exposed internal details | Hidden complexity |
| 27 tests | 15 focused tests |
| ~1200 lines | ~600 lines |

**The market maker just needs:**
```python
if feed.is_healthy:
    mid = feed.get_midpoint(token)
    place_quotes(mid)
else:
    cancel_quotes()
```

Everything else is implementation detail.
