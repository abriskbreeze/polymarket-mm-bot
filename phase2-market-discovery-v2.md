# Task: Polymarket Trading Bot - Phase 2: Market Discovery & Data Fetching

## Context

This is Phase 2 of a 10-phase iterative build of a Polymarket market-making bot. Phase 1 (Environment & Connectivity) has been completed and verified.

## Objective

Implement market discovery and data fetching from both the Gamma API (market metadata) and CLOB API (pricing/order books).

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         POLYMARKET BOT - PHASE 2                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐                  │
│   │   models.py │     │  markets.py │     │  pricing.py │                  │
│   │             │     │             │     │             │                  │
│   │ - Market    │     │ - fetch_    │     │ - get_      │                  │
│   │ - OrderBook │     │   active_   │     │   midpoint  │                  │
│   │ - PriceLevel│     │   markets() │     │ - get_price │                  │
│   │ - Outcome   │     │ - search_   │     │ - get_order │                  │
│   │ - Event     │     │   markets() │     │   _book()   │                  │
│   └─────────────┘     └──────┬──────┘     └──────┬──────┘                  │
│                              │                   │                          │
│                              ▼                   ▼                          │
│                    ┌─────────────────────────────────────┐                  │
│                    │            client.py                │                  │
│                    │         get_client()                │                  │
│                    └─────────────────┬───────────────────┘                  │
│                                      │                                      │
└──────────────────────────────────────┼──────────────────────────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────┐
                    │         POLYMARKET APIs             │
                    ├──────────────────┬──────────────────┤
                    │   Gamma API      │    CLOB API      │
                    │   (metadata)     │    (pricing)     │
                    │                  │                  │
                    │ • Markets list   │ • Order books    │
                    │ • Events         │ • Midpoints      │
                    │ • Search         │ • Best prices    │
                    │ • Token IDs      │ • Spreads        │
                    └──────────────────┴──────────────────┘
```

---

## Data Flow Diagram

```
┌────────────────────────────────────────────────────────────────────────────┐
│                            DATA FLOW - PHASE 2                             │
└────────────────────────────────────────────────────────────────────────────┘

  MARKET DISCOVERY FLOW:
  ══════════════════════

  ┌──────────┐    HTTP GET     ┌─────────────────┐    JSON      ┌──────────┐
  │          │ ───────────────▶│                 │ ────────────▶│          │
  │ Bot      │   /markets      │  Gamma API      │  [markets]   │ markets  │
  │          │   ?active=true  │  gamma-api.     │              │ .py      │
  │          │                 │  polymarket.com │              │          │
  └──────────┘                 └─────────────────┘              └────┬─────┘
                                                                     │
                                                                     ▼
                                                              ┌──────────────┐
                                                              │ _parse_      │
                                                              │ market()     │
                                                              └──────┬───────┘
                                                                     │
                                                                     ▼
                                                              ┌──────────────┐
                                                              │ List[Market] │
                                                              │ with token   │
                                                              │ IDs          │
                                                              └──────────────┘


  PRICING FLOW:
  ═════════════

  ┌──────────┐   get_order_book()   ┌─────────────────┐         ┌──────────┐
  │          │ ────────────────────▶│                 │────────▶│          │
  │ Bot      │      token_id        │  CLOB API       │  JSON   │ pricing  │
  │          │                      │  clob.          │         │ .py      │
  │          │◀─────────────────────│  polymarket.com │         │          │
  └──────────┘     OrderBook        └─────────────────┘         └────┬─────┘
                                                                     │
                                                                     ▼
                                                              ┌──────────────┐
                                                              │ _parse_      │
                                                              │ order_book() │
                                                              └──────┬───────┘
                                                                     │
                                                                     ▼
                                                              ┌──────────────┐
                                                              │ OrderBook    │
                                                              │ .bids        │
                                                              │ .asks        │
                                                              │ .spread      │
                                                              │ .midpoint    │
                                                              └──────────────┘
```

---

## Data Model Relationships

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA MODELS                                       │
└─────────────────────────────────────────────────────────────────────────────┘

  ┌───────────────────┐
  │      Event        │
  ├───────────────────┤
  │ event_id: str     │
  │ title: str        │
  │ slug: str         │
  │ active: bool      │        1
  │ markets: List ────┼────────────────┐
  └───────────────────┘                │
                                       │ *
                               ┌───────▼───────────┐
                               │      Market       │
                               ├───────────────────┤
                               │ condition_id: str │
                               │ question: str     │
                               │ slug: str         │
                               │ active: bool      │
                               │ closed: bool      │
                               │ volume: float     │       1
                               │ outcomes: List ───┼───────────────┐
                               └───────────────────┘               │
                                                                   │ *
                                                           ┌───────▼───────────┐
                                                           │     Outcome       │
                                                           ├───────────────────┤
                                                           │ name: str         │
                                                           │ token_id: str  ───┼───┐
                                                           │ price: float?     │   │
                                                           └───────────────────┘   │
                                                                                   │
                   ┌───────────────────────────────────────────────────────────────┘
                   │
                   │  token_id links to
                   ▼
  ┌───────────────────┐
  │    OrderBook      │
  ├───────────────────┤
  │ token_id: str     │        1
  │ bids: List ───────┼────────────────┐
  │ asks: List ───────┼────────────┐   │
  │ timestamp: str?   │            │   │
  ├───────────────────┤            │   │
  │ » best_bid        │            │   │ *
  │ » best_ask        │    ┌───────▼───▼───────┐
  │ » spread          │    │   PriceLevel      │
  │ » midpoint        │    ├───────────────────┤
  └───────────────────┘    │ price: float      │
                           │ size: float       │
                           └───────────────────┘
```

---

## Module Dependency Graph

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        MODULE DEPENDENCIES                                  │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────┐
                              │  config.py  │
                              │             │
                              │ CLOB_API_URL│
                              │ GAMMA_API_  │
                              │ URL         │
                              └──────┬──────┘
                                     │
                     ┌───────────────┼───────────────┐
                     │               │               │
                     ▼               ▼               ▼
              ┌──────────┐    ┌──────────┐    ┌──────────┐
              │ client.py│    │markets.py│    │ utils.py │
              │          │    │          │    │          │
              │get_client│    │fetch_    │    │setup_    │
              │    ()    │    │active_   │    │logging() │
              └────┬─────┘    │markets() │    └────┬─────┘
                   │          └────┬─────┘         │
                   │               │               │
                   │               ▼               │
                   │          ┌──────────┐         │
                   │          │models.py │         │
                   │          │          │◀────────┘
                   │          │ Market   │
                   │          │ OrderBook│
                   │          │ etc.     │
                   │          └────┬─────┘
                   │               │
                   │               │
                   ▼               ▼
              ┌─────────────────────────┐
              │       pricing.py        │
              │                         │
              │ get_midpoint()          │
              │ get_order_book()        │
              │ get_spread()            │
              └─────────────────────────┘

  Legend:
  ───────
  ───▶  imports / depends on
```

---

## API Request/Response Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    API REQUEST/RESPONSE EXAMPLES                            │
└─────────────────────────────────────────────────────────────────────────────┘


  GAMMA API - Fetch Markets:
  ══════════════════════════

  REQUEST:
  ┌─────────────────────────────────────────────────────────────────┐
  │ GET https://gamma-api.polymarket.com/markets                    │
  │     ?active=true                                                │
  │     &closed=false                                               │
  │     &limit=10                                                   │
  │     &order=volume                                               │
  └─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
  RESPONSE:
  ┌─────────────────────────────────────────────────────────────────┐
  │ [                                                               │
  │   {                                                             │
  │     "conditionId": "0x1234...",                                 │
  │     "question": "Will X happen?",                               │
  │     "slug": "will-x-happen",                                    │
  │     "outcomes": ["Yes", "No"],                                  │
  │     "clobTokenIds": ["12345...", "67890..."],  ◀── Token IDs    │
  │     "volume": 1500000,                                          │
  │     "liquidity": 50000,                                         │
  │     "active": true                                              │
  │   },                                                            │
  │   ...                                                           │
  │ ]                                                               │
  └─────────────────────────────────────────────────────────────────┘


  CLOB API - Get Order Book:
  ══════════════════════════

  REQUEST:
  ┌─────────────────────────────────────────────────────────────────┐
  │ GET https://clob.polymarket.com/book                            │
  │     ?token_id=12345...                                          │
  └─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
  RESPONSE:
  ┌─────────────────────────────────────────────────────────────────┐
  │ {                                                               │
  │   "bids": [                    ◀── Buy orders (sorted high→low) │
  │     {"price": "0.55", "size": "1000"},                          │
  │     {"price": "0.54", "size": "500"},                           │
  │     {"price": "0.53", "size": "2000"}                           │
  │   ],                                                            │
  │   "asks": [                    ◀── Sell orders (sorted low→high)│
  │     {"price": "0.57", "size": "800"},                           │
  │     {"price": "0.58", "size": "1200"},                          │
  │     {"price": "0.60", "size": "300"}                            │
  │   ],                                                            │
  │   "timestamp": "1234567890"                                     │
  │ }                                                               │
  │                                                                 │
  │ Calculated:                                                     │
  │   best_bid  = 0.55                                              │
  │   best_ask  = 0.57                                              │
  │   spread    = 0.02  (0.57 - 0.55)                               │
  │   midpoint  = 0.56  ((0.55 + 0.57) / 2)                         │
  └─────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

- Phase 1 completed and all tests passing
- Working `get_client()` function from `src/client.py`

## Requirements

### 1. Update Project Structure

Add these new files:

```
/polymarket-bot
├── /src
│   ├── __init__.py
│   ├── config.py          # (existing)
│   ├── client.py          # (existing)
│   ├── utils.py           # (existing)
│   ├── models.py          # NEW - Data models
│   ├── markets.py         # NEW - Market discovery
│   └── pricing.py         # NEW - Pricing and order books
├── /tests
│   ├── __init__.py
│   ├── test_phase1.py     # (existing)
│   └── test_phase2.py     # NEW - Phase 2 tests
└── ...
```

### 2. models.py - Data Models

Create data models using Python dataclasses:

```python
"""
Data models for Polymarket bot.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class PriceLevel:
    """Single price level in order book"""
    price: float
    size: float


@dataclass
class OrderBook:
    """Order book for a token"""
    token_id: str
    bids: List[PriceLevel]
    asks: List[PriceLevel]
    timestamp: Optional[str] = None
    
    @property
    def best_bid(self) -> Optional[float]:
        """Best (highest) bid price"""
        return self.bids[0].price if self.bids else None
    
    @property
    def best_ask(self) -> Optional[float]:
        """Best (lowest) ask price"""
        return self.asks[0].price if self.asks else None
    
    @property
    def spread(self) -> Optional[float]:
        """Bid-ask spread"""
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None
    
    @property
    def midpoint(self) -> Optional[float]:
        """Midpoint price"""
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return None


@dataclass
class Outcome:
    """Single outcome in a market"""
    name: str
    token_id: str
    price: Optional[float] = None


@dataclass
class Market:
    """Polymarket market"""
    condition_id: str
    question: str
    slug: str
    outcomes: List[Outcome]
    active: bool = True
    closed: bool = False
    volume: float = 0.0
    liquidity: float = 0.0
    end_date: Optional[str] = None
    description: Optional[str] = None
    
    @property
    def token_ids(self) -> List[str]:
        """Get all token IDs for this market"""
        return [o.token_id for o in self.outcomes]


@dataclass 
class Event:
    """Polymarket event (can contain multiple markets)"""
    event_id: str
    title: str
    slug: str
    markets: List[Market] = field(default_factory=list)
    active: bool = True
```

### 3. markets.py - Market Discovery

Create module for fetching market data from Gamma API:

```python
"""
Market discovery using Polymarket Gamma API.
"""

import requests
from typing import List, Optional, Dict, Any
from src.config import GAMMA_API_URL
from src.models import Market, Event, Outcome
from src.utils import setup_logging

logger = setup_logging()


def fetch_active_markets(
    limit: int = 100,
    offset: int = 0,
    order: str = "volume",
    ascending: bool = False
) -> List[Market]:
    """
    Fetch active markets from Gamma API.
    
    Args:
        limit: Maximum number of markets to return (max 100)
        offset: Pagination offset
        order: Sort field (volume, liquidity, etc.)
        ascending: Sort direction
        
    Returns:
        List of Market objects
    """
    url = f"{GAMMA_API_URL}/markets"
    params = {
        "limit": min(limit, 100),
        "offset": offset,
        "active": "true",
        "closed": "false",
        "order": order,
        "ascending": str(ascending).lower()
    }
    
    response = requests.get(url, params=params)
    response.raise_for_status()
    
    markets_data = response.json()
    return [_parse_market(m) for m in markets_data]


def fetch_market_by_id(condition_id: str) -> Optional[Market]:
    """
    Fetch a single market by condition ID.
    
    Args:
        condition_id: The market's condition ID
        
    Returns:
        Market object or None if not found
    """
    url = f"{GAMMA_API_URL}/markets/{condition_id}"
    
    response = requests.get(url)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    
    return _parse_market(response.json())


def fetch_market_by_slug(slug: str) -> Optional[Market]:
    """
    Fetch a single market by slug.
    
    Args:
        slug: The market's URL slug
        
    Returns:
        Market object or None if not found
    """
    url = f"{GAMMA_API_URL}/markets"
    params = {"slug": slug}
    
    response = requests.get(url, params=params)
    response.raise_for_status()
    
    markets = response.json()
    if not markets:
        return None
    
    return _parse_market(markets[0])


def fetch_events(
    limit: int = 50,
    active: bool = True,
    closed: bool = False
) -> List[Event]:
    """
    Fetch events from Gamma API.
    
    Args:
        limit: Maximum number of events
        active: Filter for active events
        closed: Filter for closed events
        
    Returns:
        List of Event objects
    """
    url = f"{GAMMA_API_URL}/events"
    params = {
        "limit": limit,
        "active": str(active).lower(),
        "closed": str(closed).lower()
    }
    
    response = requests.get(url, params=params)
    response.raise_for_status()
    
    events_data = response.json()
    return [_parse_event(e) for e in events_data]


def search_markets(query: str, limit: int = 20) -> List[Market]:
    """
    Search markets by text query.
    
    Args:
        query: Search string
        limit: Maximum results
        
    Returns:
        List of matching Market objects
    """
    url = f"{GAMMA_API_URL}/search"
    params = {
        "q": query,
        "limit": limit
    }
    
    response = requests.get(url, params=params)
    response.raise_for_status()
    
    # Search endpoint returns markets directly
    results = response.json()
    markets = results.get("markets", results) if isinstance(results, dict) else results
    
    return [_parse_market(m) for m in markets if m]


def _parse_market(data: Dict[str, Any]) -> Market:
    """Parse raw API response into Market object"""
    
    # Parse outcomes - handle different API response formats
    outcomes = []
    
    # Try to get token IDs from clobTokenIds field
    clob_token_ids = data.get("clobTokenIds", [])
    outcome_names = data.get("outcomes", [])
    
    if clob_token_ids and outcome_names:
        # Standard format with clobTokenIds
        for i, token_id in enumerate(clob_token_ids):
            name = outcome_names[i] if i < len(outcome_names) else f"Outcome {i}"
            outcomes.append(Outcome(
                name=name,
                token_id=token_id
            ))
    elif "tokens" in data:
        # Alternative format with tokens array
        for token in data["tokens"]:
            outcomes.append(Outcome(
                name=token.get("outcome", "Unknown"),
                token_id=token.get("token_id", "")
            ))
    
    return Market(
        condition_id=data.get("conditionId", data.get("condition_id", "")),
        question=data.get("question", ""),
        slug=data.get("slug", ""),
        outcomes=outcomes,
        active=data.get("active", True),
        closed=data.get("closed", False),
        volume=float(data.get("volume", 0) or 0),
        liquidity=float(data.get("liquidity", 0) or 0),
        end_date=data.get("endDate"),
        description=data.get("description")
    )


def _parse_event(data: Dict[str, Any]) -> Event:
    """Parse raw API response into Event object"""
    
    markets = []
    if "markets" in data:
        markets = [_parse_market(m) for m in data["markets"]]
    
    return Event(
        event_id=data.get("id", ""),
        title=data.get("title", ""),
        slug=data.get("slug", ""),
        markets=markets,
        active=data.get("active", True)
    )
```

### 4. pricing.py - Pricing and Order Books

Create module for fetching pricing data from CLOB API:

```python
"""
Pricing and order book data from Polymarket CLOB API.
"""

from typing import List, Optional, Dict, Any
from src.client import get_client
from src.models import OrderBook, PriceLevel
from src.utils import setup_logging

logger = setup_logging()


def get_midpoint(token_id: str) -> Optional[float]:
    """
    Get current midpoint price for a token.
    
    Args:
        token_id: The token ID
        
    Returns:
        Midpoint price or None if unavailable
    """
    client = get_client()
    
    try:
        result = client.get_midpoint(token_id)
        if result is not None:
            return float(result)
        return None
    except Exception as e:
        logger.error(f"Error fetching midpoint for {token_id}: {e}")
        return None


def get_price(token_id: str, side: str = "BUY") -> Optional[float]:
    """
    Get current best price for a token.
    
    Args:
        token_id: The token ID
        side: "BUY" or "SELL"
        
    Returns:
        Best price for the given side or None
    """
    client = get_client()
    
    try:
        result = client.get_price(token_id, side=side)
        if result is not None:
            return float(result)
        return None
    except Exception as e:
        logger.error(f"Error fetching price for {token_id}: {e}")
        return None


def get_order_book(token_id: str) -> Optional[OrderBook]:
    """
    Get full order book for a token.
    
    Args:
        token_id: The token ID
        
    Returns:
        OrderBook object or None if unavailable
    """
    client = get_client()
    
    try:
        result = client.get_order_book(token_id)
        return _parse_order_book(token_id, result)
    except Exception as e:
        logger.error(f"Error fetching order book for {token_id}: {e}")
        return None


def get_order_books(token_ids: List[str]) -> Dict[str, OrderBook]:
    """
    Get order books for multiple tokens in one call.
    
    Args:
        token_ids: List of token IDs
        
    Returns:
        Dictionary mapping token_id to OrderBook
    """
    client = get_client()
    
    try:
        # Build params for batch request
        from py_clob_client.clob_types import BookParams
        params = [BookParams(token_id=tid) for tid in token_ids]
        
        results = client.get_order_books(params)
        
        books = {}
        for i, result in enumerate(results):
            if result:
                token_id = token_ids[i]
                books[token_id] = _parse_order_book(token_id, result)
        
        return books
    except Exception as e:
        logger.error(f"Error fetching order books: {e}")
        return {}


def get_spread(token_id: str) -> Optional[float]:
    """
    Get current bid-ask spread for a token.
    
    Args:
        token_id: The token ID
        
    Returns:
        Spread (ask - bid) or None if unavailable
    """
    book = get_order_book(token_id)
    if book:
        return book.spread
    return None


def get_spread_percentage(token_id: str) -> Optional[float]:
    """
    Get current bid-ask spread as percentage of midpoint.
    
    Args:
        token_id: The token ID
        
    Returns:
        Spread percentage or None if unavailable
    """
    book = get_order_book(token_id)
    if book and book.spread and book.midpoint and book.midpoint > 0:
        return (book.spread / book.midpoint) * 100
    return None


def _parse_order_book(token_id: str, data: Dict[str, Any]) -> OrderBook:
    """Parse raw order book response into OrderBook object"""
    
    bids = []
    asks = []
    
    # Parse bids (buy orders)
    raw_bids = data.get("bids", [])
    for bid in raw_bids:
        if isinstance(bid, dict):
            bids.append(PriceLevel(
                price=float(bid.get("price", 0)),
                size=float(bid.get("size", 0))
            ))
        elif isinstance(bid, (list, tuple)) and len(bid) >= 2:
            bids.append(PriceLevel(price=float(bid[0]), size=float(bid[1])))
    
    # Parse asks (sell orders)
    raw_asks = data.get("asks", [])
    for ask in raw_asks:
        if isinstance(ask, dict):
            asks.append(PriceLevel(
                price=float(ask.get("price", 0)),
                size=float(ask.get("size", 0))
            ))
        elif isinstance(ask, (list, tuple)) and len(ask) >= 2:
            asks.append(PriceLevel(price=float(ask[0]), size=float(ask[1])))
    
    # Sort: bids descending (highest first), asks ascending (lowest first)
    bids.sort(key=lambda x: x.price, reverse=True)
    asks.sort(key=lambda x: x.price)
    
    return OrderBook(
        token_id=token_id,
        bids=bids,
        asks=asks,
        timestamp=data.get("timestamp")
    )
```

### 5. tests/test_phase2.py - Verification Tests

```python
"""
Phase 2 Verification Tests
Run with: pytest tests/test_phase2.py -v

Phase 2 is ONLY complete when all tests pass.
"""

import pytest


class TestModels:
    """Test data models"""
    
    def test_price_level_creation(self):
        """Verify PriceLevel model works"""
        from src.models import PriceLevel
        
        level = PriceLevel(price=0.55, size=100.0)
        assert level.price == 0.55
        assert level.size == 100.0
        print("✓ PriceLevel model works")
    
    def test_order_book_properties(self):
        """Verify OrderBook computed properties"""
        from src.models import OrderBook, PriceLevel
        
        book = OrderBook(
            token_id="test_token",
            bids=[PriceLevel(0.50, 100), PriceLevel(0.49, 200)],
            asks=[PriceLevel(0.52, 150), PriceLevel(0.53, 250)]
        )
        
        assert book.best_bid == 0.50
        assert book.best_ask == 0.52
        assert book.spread == 0.02
        assert book.midpoint == 0.51
        print(f"✓ OrderBook properties: bid={book.best_bid}, ask={book.best_ask}, spread={book.spread}")
    
    def test_market_model(self):
        """Verify Market model works"""
        from src.models import Market, Outcome
        
        market = Market(
            condition_id="0x123",
            question="Test question?",
            slug="test-question",
            outcomes=[
                Outcome(name="Yes", token_id="token1"),
                Outcome(name="No", token_id="token2")
            ]
        )
        
        assert len(market.token_ids) == 2
        assert "token1" in market.token_ids
        print(f"✓ Market model works: {len(market.outcomes)} outcomes")


class TestMarketDiscovery:
    """Test market discovery from Gamma API"""
    
    def test_fetch_active_markets(self):
        """Verify we can fetch active markets"""
        from src.markets import fetch_active_markets
        
        markets = fetch_active_markets(limit=5)
        
        assert len(markets) > 0, "Should return at least one market"
        assert markets[0].condition_id, "Market should have condition_id"
        assert markets[0].question, "Market should have question"
        
        print(f"✓ Fetched {len(markets)} active markets")
        print(f"  First market: {markets[0].question[:50]}...")
    
    def test_market_has_token_ids(self):
        """Verify markets have token IDs for trading"""
        from src.markets import fetch_active_markets
        
        markets = fetch_active_markets(limit=5)
        
        # Find a market with token IDs
        market_with_tokens = None
        for m in markets:
            if m.token_ids:
                market_with_tokens = m
                break
        
        assert market_with_tokens is not None, "Should find at least one market with tokens"
        assert len(market_with_tokens.token_ids) > 0, "Market should have token IDs"
        
        print(f"✓ Market has {len(market_with_tokens.token_ids)} token(s)")
        print(f"  Token ID: {market_with_tokens.token_ids[0][:20]}...")
    
    def test_fetch_events(self):
        """Verify we can fetch events"""
        from src.markets import fetch_events
        
        events = fetch_events(limit=3)
        
        assert len(events) > 0, "Should return at least one event"
        assert events[0].title, "Event should have title"
        
        print(f"✓ Fetched {len(events)} events")
        print(f"  First event: {events[0].title[:50]}...")


class TestPricing:
    """Test pricing and order book fetching"""
    
    def _get_test_token_id(self):
        """Helper to get a valid token ID for testing"""
        from src.markets import fetch_active_markets
        
        markets = fetch_active_markets(limit=10)
        for m in markets:
            if m.token_ids:
                return m.token_ids[0]
        pytest.skip("No markets with token IDs found")
    
    def test_get_midpoint(self):
        """Verify we can get midpoint price"""
        from src.pricing import get_midpoint
        
        token_id = self._get_test_token_id()
        mid = get_midpoint(token_id)
        
        # Midpoint might be None for illiquid markets, but function should work
        assert mid is None or (0 <= mid <= 1), "Midpoint should be between 0 and 1"
        
        print(f"✓ Midpoint: {mid}")
    
    def test_get_price(self):
        """Verify we can get best price"""
        from src.pricing import get_price
        
        token_id = self._get_test_token_id()
        
        buy_price = get_price(token_id, "BUY")
        sell_price = get_price(token_id, "SELL")
        
        print(f"✓ Prices - Buy: {buy_price}, Sell: {sell_price}")
    
    def test_get_order_book(self):
        """Verify we can get full order book"""
        from src.pricing import get_order_book
        
        token_id = self._get_test_token_id()
        book = get_order_book(token_id)
        
        assert book is not None, "Should return order book"
        assert book.token_id == token_id, "Token ID should match"
        
        print(f"✓ Order book: {len(book.bids)} bids, {len(book.asks)} asks")
        if book.best_bid and book.best_ask:
            print(f"  Best bid: {book.best_bid}, Best ask: {book.best_ask}")
            print(f"  Spread: {book.spread:.4f}")
    
    def test_get_spread(self):
        """Verify spread calculation"""
        from src.pricing import get_spread, get_spread_percentage
        
        token_id = self._get_test_token_id()
        
        spread = get_spread(token_id)
        spread_pct = get_spread_percentage(token_id)
        
        print(f"✓ Spread: {spread}, Spread %: {spread_pct}")


class TestIntegration:
    """Integration tests combining market discovery and pricing"""
    
    def test_full_market_data_flow(self):
        """Test complete flow: discover market, get prices"""
        from src.markets import fetch_active_markets
        from src.pricing import get_order_book
        
        # 1. Fetch markets
        markets = fetch_active_markets(limit=3)
        assert len(markets) > 0
        
        # 2. Find a market with tokens
        test_market = None
        for m in markets:
            if m.token_ids:
                test_market = m
                break
        
        assert test_market is not None, "Need a market with tokens"
        
        # 3. Get order book for first token
        token_id = test_market.token_ids[0]
        book = get_order_book(token_id)
        
        assert book is not None
        
        print(f"✓ Full flow successful:")
        print(f"  Market: {test_market.question[:40]}...")
        print(f"  Token: {token_id[:20]}...")
        print(f"  Book: {len(book.bids)} bids, {len(book.asks)} asks")
        if book.midpoint:
            print(f"  Midpoint: {book.midpoint:.4f}")
```

---

## Verification Gate

After creating all files, run:

```bash
cd polymarket-bot
source venv/bin/activate  # On Windows: venv\Scripts\activate
pytest tests/test_phase2.py -v
```

## Success Criteria

**Phase 2 is ONLY complete when ALL tests pass:**

```
tests/test_phase2.py::TestModels::test_price_level_creation PASSED
tests/test_phase2.py::TestModels::test_order_book_properties PASSED
tests/test_phase2.py::TestModels::test_market_model PASSED
tests/test_phase2.py::TestMarketDiscovery::test_fetch_active_markets PASSED
tests/test_phase2.py::TestMarketDiscovery::test_market_has_token_ids PASSED
tests/test_phase2.py::TestMarketDiscovery::test_fetch_events PASSED
tests/test_phase2.py::TestPricing::test_get_midpoint PASSED
tests/test_phase2.py::TestPricing::test_get_price PASSED
tests/test_phase2.py::TestPricing::test_get_order_book PASSED
tests/test_phase2.py::TestPricing::test_get_spread PASSED
tests/test_phase2.py::TestIntegration::test_full_market_data_flow PASSED
```

---

## Troubleshooting

If you get import errors:
- Ensure `__init__.py` exists in `/src` directory
- Ensure all new modules are saved correctly

If API calls fail:
- Check internet connectivity
- Verify API URLs are correct in config.py
- Some endpoints may rate limit - wait and retry

If markets have no token IDs:
- The Gamma API format may vary - check the raw response
- Try fetching more markets (increase limit)
