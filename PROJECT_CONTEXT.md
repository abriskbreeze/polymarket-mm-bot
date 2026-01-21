# Polymarket Trading Bot - Project Context

## Project Overview

Building a market-making bot for Polymarket prediction markets. The bot will:
1. Provide two-sided liquidity (bid/ask quotes)
2. Capture spread + earn liquidity rewards
3. Auto-manage risk and inventory
4. Optionally detect arbitrage opportunities

**Strategy**: Spread-capturing market maker with liquidity mining rewards

**Revenue Model**: Spread Capture + Liquidity Rewards - Adverse Selection

---

## Key Polymarket API Information

### API Endpoints

| API | Base URL | Purpose |
|-----|----------|---------|
| Gamma API | `https://gamma-api.polymarket.com` | Market metadata, events, search |
| CLOB API | `https://clob.polymarket.com` | Order books, pricing, trading |
| Data API | `https://data-api.polymarket.com` | Positions, trades, activity |
| WebSocket | `wss://ws-subscriptions-clob.polymarket.com/ws/market` | Real-time updates |

### Rate Limits

| Endpoint | Limit |
|----------|-------|
| CLOB POST /order | 240/s burst, 40/s sustained |
| CLOB DELETE /order | 240/s burst, 40/s sustained |
| CLOB /book | 200 req/10s |
| Gamma /markets | 125 req/10s |
| Data API | 200 req/10s |

### Order Types

| Type | Use Case |
|------|----------|
| GTC (Good Till Cancelled) | Default for passive quoting |
| GTD (Good Till Date) | Auto-expire before events |
| FOK (Fill or Kill) | All or nothing rebalancing |
| FAK (Fill and Kill) | Partial fills acceptable |

### Fee Structure
- **0% maker fees**
- **0% taker fees**
- Keep full spread!

### Liquidity Rewards
- Formula rewards two-sided depth, spread vs mid, participation
- Max spread and min size cutoff per market
- Daily payouts at ~midnight UTC
- Minimum $1 payout threshold

---

## Development Plan - 10 Phases

### Phase 1: Environment & Connectivity ✅ COMPLETED
- Project structure setup
- Dependencies: py-clob-client, python-dotenv, websockets, pandas, pytest
- Config management with environment variables
- Basic CLOB client wrapper
- **6 tests passing**

### Phase 2: Market Discovery & Data Fetching ✅ COMPLETED
- Data models: PriceLevel, OrderBook, Market, Outcome, Event
- Gamma API integration for market discovery
- CLOB pricing functions
- **11 tests passing**

### Phase 3: WebSocket Real-Time Data ✅ COMPLETED (Original)
- Basic WebSocket client
- Market channel subscriptions
- Callbacks for price/book/trade updates
- Simple reconnection logic
- **12 tests passing**

### Phase 3.5: WebSocket Hardening (Simplified) ⏳ CURRENT
- Simple 4-state machine: STOPPED → STARTING → RUNNING → ERROR
- Single `MarketFeed` class with clean API
- Internal: async queue, sequence tracking, REST fallback (hidden)
- `is_healthy` property for market maker to check
- Mock feed for offline testing
- **15 focused tests**

### Phase 4: Authentication & Wallet Setup (Next)
- Wallet creation (separate from personal wallet)
- Fund with MATIC (gas) and USDC.e (trading)
- Secure credential management
- API credentials: create_or_derive_api_creds(), set_api_creds()
- Allowance management for Exchange contract
- **Estimated: 1-2 hours**

### Phase 5: Order Management Read Operations
- orders.py: get_order, get_open_orders, get_trades
- Order data models (Order, Trade, OrderStatus enum)
- User WebSocket channel for order/trade events
- Local order cache and status tracking
- **Estimated: 2-3 hours**

### Phase 6: Order Placement & Cancellation
⚠️ Start with tiny sizes ($1-5)
- build_limit_order, build_market_order
- create_and_post_order, post_orders (batch)
- cancel_order, cancel_orders, cancel_all
- Safety checks: max size, price sanity, rate limits
- Tick size validation
- **Estimated: 3-4 hours**

### Phase 7: Market Making Core Logic
- strategy/market_maker.py: MarketMaker class
- Quote calculation (bid/ask from mid, spread)
- Two-sided quote management
- Inventory awareness and skewing
- Update on price movement (threshold-based)
- Graceful shutdown (cancel all on exit)
- **Estimated: 4-6 hours**

### Phase 8: Risk Management
- risk/manager.py: RiskManager class
- Position limits (per-market, total exposure)
- Kill switches (manual, auto on error/loss/connectivity)
- Pre-trade validation
- Market event detection (approaching resolution, volume spikes)
- P&L tracking and alerts
- **Estimated: 3-4 hours**

### Phase 9: Arbitrage Detection (Optional)
- strategy/arbitrage.py: ArbitrageScanner
- YES/NO arbitrage (sum != 1.00)
- Cross-market arbitrage (related markets)
- Atomic execution (batch orders)
- Opportunity logging and hit rate tracking
- **Estimated: 3-4 hours**

### Phase 10: Production Hardening
- Structured logging (JSON, rotation)
- systemd service or Docker container
- Graceful shutdown (SIGTERM handler)
- State persistence and recovery
- Operational runbooks
- Performance optimization
- Monitoring dashboard
- **Estimated: 4-6 hours**

**Total Estimated Time: 30-40 hours**

---

## Current File Structure

```
polymarket-bot/
├── .env                    # Environment variables (gitignored)
├── .env.example            # Template for env vars
├── requirements.txt        # Python dependencies
├── pytest.ini              # Pytest configuration
│
├── src/
│   ├── __init__.py
│   ├── config.py           # Configuration from env vars
│   ├── client.py           # CLOB client wrapper (singleton)
│   ├── utils.py            # Logging, timestamp helpers
│   ├── models.py           # Data models (PriceLevel, OrderBook, Market, etc.)
│   ├── markets.py          # Gamma API - market discovery
│   ├── pricing.py          # CLOB API - order books, pricing
│   │
│   └── feed/               # NEW in Phase 3.5 (simplified)
│       ├── __init__.py     # Exports: MarketFeed, FeedState
│       ├── feed.py         # Main MarketFeed class (public API)
│       ├── websocket_conn.py   # WebSocket connection (internal)
│       ├── rest_poller.py  # REST fallback (internal)
│       ├── data_store.py   # Local data storage (internal)
│       └── mock.py         # Mock for testing
│
├── tests/
│   ├── __init__.py
│   ├── test_phase1.py      # 6 tests
│   ├── test_phase2.py      # 11 tests
│   ├── test_phase3.py      # 12 tests (original WebSocket)
│   └── test_phase3_5.py    # 15 tests (simplified feed)
│
└── venv/                   # Virtual environment
```

---

## Key Configuration Values

```python
# config.py current values

# CLOB API
CLOB_API_URL = "https://clob.polymarket.com"
CLOB_API_KEY = os.getenv("CLOB_API_KEY")  # Optional for read-only

# Gamma API  
GAMMA_API_URL = "https://gamma-api.polymarket.com"

# Chain
CHAIN_ID = 137  # Polygon mainnet

# WebSocket
WS_MARKET_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
WS_RECONNECT_ATTEMPTS = 10
WS_RECONNECT_BASE_DELAY = 1.0
WS_RECONNECT_MAX_DELAY = 60.0
WS_HEARTBEAT_INTERVAL = 30.0
WS_STALE_DATA_THRESHOLD = 60.0
```

---

## Data Models

### PriceLevel
```python
@dataclass
class PriceLevel:
    price: float
    size: float
```

### OrderBook
```python
@dataclass
class OrderBook:
    token_id: str
    bids: List[PriceLevel]
    asks: List[PriceLevel]
    timestamp: Optional[str] = None
    
    @property
    def best_bid(self) -> Optional[float]
    @property
    def best_ask(self) -> Optional[float]
    @property
    def midpoint(self) -> Optional[float]
    @property
    def spread(self) -> Optional[float]
```

### Market
```python
@dataclass
class Market:
    id: str
    question: str
    condition_id: str
    slug: str
    status: str  # "active", "resolved", etc.
    outcomes: List[Outcome]
    token_ids: List[str]
    end_date: Optional[str] = None
    volume: float = 0.0
    liquidity: float = 0.0
```

### TokenData (Phase 3.5 - internal)
```python
@dataclass
class TokenData:
    token_id: str
    order_book: Optional[OrderBook] = None
    last_price: Optional[float] = None
    last_trade_price: Optional[float] = None
    last_trade_side: Optional[str] = None
    last_trade_size: Optional[float] = None
    last_update: float = 0.0
```

Note: This is internal to the `DataStore`. Users access data via `MarketFeed` methods like `get_midpoint(token)`.

---

## Feed States (Phase 3.5 - Simplified)

```
STOPPED   → Not running, call start() to begin
STARTING  → Connecting and subscribing (handles retries internally)
RUNNING   → Receiving data, check is_healthy for data quality
ERROR     → Max retries exceeded, call reset() or stop()
```

**Key insight:** The market maker doesn't care about connection details. It only needs:
- `is_healthy` → Can I trust this data?
- `get_midpoint(token)` → What's the current price?

---

## WebSocket Message Types

| Event Type | Description | Priority |
|------------|-------------|----------|
| `price_change` | Best bid/ask changed | NORMAL |
| `book` | Full order book update | HIGH |
| `last_trade_price` | Trade executed | NORMAL |
| `tick_size_change` | Tick size changed | HIGH |

---

## Key Design Decisions

1. **Singleton CLOB Client** - Single instance shared across modules
2. **Simple 4-State Feed** - STOPPED/STARTING/RUNNING/ERROR (not 9 states!)
3. **Hidden Complexity** - Retry logic, failover, queuing all internal
4. **is_healthy Property** - Single check for market maker to trust data
5. **REST Fallback** - Automatic, transparent to caller
6. **Mock Feed** - Fast offline testing with data injection

---

## MarketFeed API (Phase 3.5)

```python
# The only interface the market maker needs:

feed = MarketFeed()
await feed.start(["token1", "token2"])

# In market making loop:
if feed.is_healthy:
    mid = feed.get_midpoint("token1")
    place_quotes(mid - spread/2, mid + spread/2)
else:
    cancel_all_quotes()  # Never quote on bad data!

await feed.stop()
```

**Properties:**
- `state` → FeedState (STOPPED, STARTING, RUNNING, ERROR)
- `is_healthy` → bool (safe to trade on this data?)
- `data_source` → str ("websocket", "rest", "none")

**Methods:**
- `start(tokens)` → Begin receiving data
- `stop()` → Clean shutdown
- `reset()` → Recover from ERROR
- `get_midpoint(token)` → Current mid price
- `get_order_book(token)` → Full order book
- `get_spread(token)` → Bid-ask spread
- `get_best_bid(token)` / `get_best_ask(token)`

**Callbacks:**
- `on_book_update` → Order book changed
- `on_price_change` → Price changed
- `on_trade` → Trade occurred
- `on_state_change` → Feed state changed

---

## Phase Documentation Files

All phase specs are stored in `/mnt/user-data/outputs/`:

| File | Description |
|------|-------------|
| `phase1-environment-connectivity.md` | Phase 1 spec |
| `phase2-market-discovery-v2.md` | Phase 2 spec with diagrams |
| `phase3-websocket-realtime.md` | Phase 3 original spec (superseded) |
| `architecture-review-pre-phase4.md` | Issues identified |
| `phase3_5-websocket-hardening.md` | Phase 3.5 original (over-engineered) |
| `phase3_5-websocket-hardening-simplified.md` | Phase 3.5 simplified (USE THIS) |
| `PROJECT_CONTEXT.md` | This file - project overview |

---

## Test Commands

```bash
# Activate virtual environment
cd polymarket-bot
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Run all tests
pytest -v

# Run specific phase
pytest tests/test_phase1.py -v
pytest tests/test_phase2.py -v
pytest tests/test_phase3.py -v
pytest tests/test_phase3_5.py -v --timeout=180

# Run with coverage
pytest --cov=src tests/
```

---

## Dependencies (requirements.txt)

```
py-clob-client>=0.1.0
python-dotenv>=1.0.0
websockets>=12.0
pandas>=2.0.0
pytest>=7.0.0
pytest-asyncio>=0.21.0
requests>=2.28.0
```

---

## Next Steps

1. **Complete Phase 3.5** - Run all 27 tests, ensure passing
2. **Phase 4** - Authentication & wallet setup
3. **Phase 5** - Order management (read operations)
4. **Phase 6** - Order placement (start with tiny $1-5 sizes!)

---

## Important Warnings

⚠️ **Phase 6+**: Always start with TINY order sizes ($1-5)
⚠️ **Wallet**: Create SEPARATE wallet for bot, never use personal wallet
⚠️ **Keys**: Never log private keys or API secrets
⚠️ **Resolution**: Cancel all orders before market resolution (use GTD orders)
⚠️ **Testing**: Use mock WebSocket for unit tests, real connection for integration

---

## Contact Points

- Polymarket CLOB Docs: https://docs.polymarket.com/
- py-clob-client: https://github.com/Polymarket/py-clob-client
- Polygon (MATIC): Chain ID 137

---

*Last Updated: Phase 3.5 simplified design*
*Total Tests: 6 + 11 + 12 + 15 = 44 tests across all phases*
