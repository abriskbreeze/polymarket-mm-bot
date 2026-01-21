# Polymarket Market-Making Bot

A sophisticated market-making trading bot for Polymarket prediction markets, built incrementally with test-driven development.

[![Tests](https://img.shields.io/badge/tests-100%2F100%20passing-brightgreen)](tests/)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## 🎯 Overview

This bot implements automated market-making strategies on [Polymarket](https://polymarket.com), a decentralized prediction market platform. The project follows a rigorous 10-phase development approach, with each phase fully tested before proceeding.

### Key Features (Planned)

- 📊 **Real-time Market Data**: WebSocket integration for live orderbook updates
- 🤖 **Automated Market Making**: Sophisticated spread management and liquidity provision
- 🔐 **Secure Trading**: Wallet integration with private key management
- 📈 **Risk Management**: Position limits, exposure tracking, and automatic safeguards
- ⚡ **Arbitrage Detection**: Cross-market opportunity identification
- 🧪 **Test-Driven**: Comprehensive test suite ensuring reliability

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or higher
- Virtual environment (recommended)
- Git

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/abriskbreeze/polymarket-mm-bot.git
   cd polymarket-mm-bot
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment (optional for Phase 1)**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials (required for Phase 4+)
   ```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run Phase 1 tests specifically
pytest tests/test_phase1.py -v
```

## 📁 Project Structure

```
polymarket-mm-bot/
├── src/
│   ├── __init__.py
│   ├── config.py              # Configuration management
│   ├── client.py              # Polymarket CLOB API client wrapper
│   ├── auth.py                # Authentication utilities (Phase 4)
│   ├── utils.py               # Logging and utility functions
│   ├── models.py              # Data models (Market, OrderBook, Order, Trade)
│   ├── markets.py             # Market discovery (Gamma API)
│   ├── pricing.py             # Pricing and order books (CLOB API)
│   ├── orders.py              # Order queries (unified DRY_RUN + LIVE) (Phase 5)
│   ├── simulator.py           # Order simulator for DRY_RUN mode (Phase 6)
│   ├── trading.py             # Order placement & cancellation (Phase 6)
│   ├── websocket_client.py    # WebSocket real-time data (Phase 3)
│   ├── feed/                  # Market data feed (Phase 3.5)
│   │   ├── __init__.py        # Public API exports
│   │   ├── feed.py            # MarketFeed main class
│   │   ├── data_store.py      # Local data storage
│   │   ├── websocket_conn.py  # WebSocket connection
│   │   ├── rest_poller.py     # REST fallback
│   │   └── mock.py            # Mock for testing
│   ├── strategy/              # Trading strategies (Phase 7)
│   │   ├── __init__.py
│   │   ├── market_maker.py    # SimpleMarketMaker class
│   │   └── runner.py          # CLI runner
│   └── risk/                  # Risk management (Phase 8)
│       ├── __init__.py        # Public API exports
│       └── manager.py         # RiskManager class
├── tests/
│   ├── __init__.py
│   ├── test_phase1.py     # Phase 1 verification tests
│   ├── test_phase2.py     # Phase 2 verification tests
│   ├── test_phase3.py     # Phase 3 verification tests
│   ├── test_phase3_5.py   # Phase 3.5 verification tests
│   ├── test_phase4.py     # Phase 4 verification tests
│   ├── test_phase5.py     # Phase 5 verification tests
│   ├── test_phase6.py     # Phase 6 verification tests
│   ├── test_phase7.py     # Phase 7 verification tests
│   └── test_phase8.py     # Phase 8 verification tests
├── thoughts/
│   └── shared/
│       └── handoffs/      # Session handoff documents
├── .env.example           # Environment variable template
├── .gitignore
├── README.md
├── requirements.txt
├── run_mm.py              # Market maker entry point
├── phase1-environment-connectivity.md  # Phase 1 specification
└── phase2-market-discovery-v2.md       # Phase 2 specification

```

## 🏗️ Development Phases

This project is built incrementally across 10 phases. Each phase must pass all tests before proceeding to the next.

### ✅ Completed Phases

- **[x] Phase 1: Environment & Connectivity**
  - Project structure setup
  - Configuration management with environment variables
  - Polymarket CLOB API client wrapper (read-only mode)
  - Logging utilities
  - Test suite: 6/6 passing ✓

- **[x] Phase 2: Market Discovery & Data Fetching**
  - Data models (Market, OrderBook, PriceLevel, Outcome, Event)
  - Market discovery from Gamma API
  - Orderbook fetching from CLOB API
  - Price data retrieval (midpoint, spread, best bid/ask)
  - Test suite: 11/11 passing ✓

- **[x] Phase 3: WebSocket Real-Time Data**
  - WebSocket connection management with auto-reconnect
  - Real-time orderbook updates
  - Price change and trade notifications
  - Local order book maintenance
  - Callback architecture for event handling
  - Test suite: 12/12 passing ✓

- **[x] Phase 3.5: WebSocket Hardening (Simplified)**
  - Simplified MarketFeed interface with health checks
  - Automatic REST fallback when WebSocket is unhealthy
  - 4-state machine (STOPPED, STARTING, RUNNING, ERROR)
  - Sequence gap detection and auto-resync
  - Non-blocking callbacks via async queue
  - Mock implementation for testing
  - Test suite: 15/15 passing ✓

- **[x] Phase 4: Authentication & Wallet Setup**
  - Authenticated CLOB client with API credentials
  - Private key and wallet management
  - Balance and allowance checking utilities
  - Setup verification helpers
  - Test suite: 8/8 passing ✓ (6 additional tests require credentials)

- **[x] Phase 5: Order Management (Read Operations)**
  - Order, Trade, OrderStatus data models
  - Unified order query interface (DRY_RUN + LIVE)
  - Position tracking and order filtering
  - Test suite: 10/10 passing ✓ (1 test requires credentials)

- **[x] Phase 6: Order Placement & Cancellation**
  - DRY_RUN mode with order simulator
  - Order placement with price/size validation
  - Position limit checks
  - Order cancellation (single and bulk)
  - Live order placement via authenticated client
  - Test suite: 12/12 passing ✓

- **[x] Phase 7: Market Making Core Logic**
  - Simple market maker with spread configuration
  - Two-sided quote placement around midpoint
  - Requoting on price movements
  - Position limit management (skip sides when at limit)
  - Signal handling for graceful shutdown
  - CLI runner with market selection
  - Test suite: 8/8 passing ✓

- **[x] Phase 8: Risk Management** _(Current)_
  - RiskManager with daily loss limits and kill switch
  - Data gathering mode (log-only) vs enforcement mode
  - Error rate limiting with cooldown
  - Position and exposure tracking
  - Risk event logging for analysis
  - Periodic status reporting
  - Test suite: 16/16 passing ✓

### 🔜 Upcoming Phases

- **[ ] Phase 9: Live Testing**
  - Real money trading with small sizes
  - Performance validation
  - Risk control verification

- **[ ] Phase 10: Arbitrage Detection**
  - Cross-market monitoring
  - Opportunity identification
  - Execution logic

- **[ ] Phase 10: Production Hardening**
  - Error handling and recovery
  - Performance optimization
  - Monitoring and alerting

## 🧪 Testing Philosophy

Every phase is test-driven:

1. **Write tests first**: Define success criteria before implementation
2. **Verify incrementally**: Each phase must pass all tests
3. **No shortcuts**: Cannot proceed to next phase with failing tests
4. **Regression protection**: All previous phase tests must continue passing

### Current Test Status

```
Phase 1 Tests: 6/6 passing ✓
├── test_config_loads         ✓
├── test_client_creation      ✓
├── test_client_connectivity  ✓
├── test_server_time          ✓
├── test_client_singleton     ✓
└── test_logging_setup        ✓

Phase 2 Tests: 11/11 passing ✓
├── TestModels
│   ├── test_price_level_creation        ✓
│   ├── test_order_book_properties       ✓
│   └── test_market_model                ✓
├── TestMarketDiscovery
│   ├── test_fetch_active_markets        ✓
│   ├── test_market_has_token_ids        ✓
│   └── test_fetch_events                ✓
├── TestPricing
│   ├── test_get_midpoint                ✓
│   ├── test_get_price                   ✓
│   ├── test_get_order_book              ✓
│   └── test_get_spread                  ✓
└── TestIntegration
    └── test_full_market_data_flow       ✓

Phase 3 Tests: 10/12 passing ✓ (2 skipped - legacy)
├── TestWebSocketClient
│   ├── test_import_websocket_client     ✓
│   ├── test_client_instantiation        ✓
│   ├── test_connect_disconnect          ✓
│   ├── test_subscribe_to_market         ✓
│   ├── test_receive_market_data         ⊘ (legacy - superseded by Phase 3.5)
│   ├── test_order_book_maintenance      ⊘ (legacy - superseded by Phase 3.5)
│   ├── test_callbacks_are_called        ✓
│   └── test_multiple_subscriptions      ✓
├── TestConnectionState
│   └── test_state_enum_values           ✓
├── TestMarketData
│   ├── test_market_data_creation        ✓
│   └── test_stale_data_detection        ✓
└── TestIntegration
    └── test_full_websocket_flow         ✓

Phase 3.5 Tests: 16/16 passing ✓
├── TestFeedState
│   └── test_states_defined              ✓
├── TestDataStore
│   ├── test_store_creation              ✓
│   ├── test_book_update                 ✓
│   ├── test_freshness                   ✓
│   └── test_sequence_tracking           ✓
├── TestMockFeed
│   ├── test_mock_basic                  ✓
│   ├── test_mock_data                   ✓
│   └── test_mock_health                 ✓
├── TestMarketFeed
│   ├── test_import                      ✓
│   ├── test_instantiation               ✓
│   ├── test_start_stop                  ✓
│   ├── test_health_and_data             ✓
│   ├── test_callbacks                   ✓
│   └── test_state_transitions           ✓
├── TestIntegration
│   └── test_market_maker_pattern        ✓
└── test_heartbeat_tracking              ✓

Phase 4 Tests: 8/8 passing ✓ (6 skipped without credentials)
├── TestConfig
│   ├── test_config_imports              ✓
│   ├── test_has_credentials             ✓
│   └── test_validate_config             ✓
├── TestClient
│   ├── test_read_client                 ✓
│   ├── test_read_client_singleton       ✓
│   ├── test_auth_client_requires_creds  ✓
│   └── test_auth_client_singleton       ⊘ (requires credentials)
├── TestAuth
│   ├── test_auth_imports                ✓
│   ├── test_get_wallet_address          ⊘ (requires credentials)
│   ├── test_get_balances                ⊘ (requires credentials)
│   ├── test_check_allowances            ⊘ (requires credentials)
│   └── test_verify_setup                ⊘ (requires credentials)
└── TestIntegration
    ├── test_authenticated_api_call      ⊘ (requires credentials)
    └── test_can_read_markets_with_auth  ✓

Phase 5 Tests: 10/10 passing ✓ (1 skipped without credentials)
├── TestOrderModels
│   ├── test_order_status_enum           ✓
│   ├── test_order_side_enum             ✓
│   ├── test_order_type_enum             ✓
│   ├── test_order_dataclass             ✓
│   └── test_trade_dataclass             ✓
├── TestOrdersModule
│   ├── test_imports                     ✓
│   ├── test_get_open_orders_works       ✓
│   ├── test_get_position                ✓
│   └── test_get_trades                  ⊘ (requires credentials)
└── TestIntegration
    ├── test_order_workflow_readonly     ✓
    └── test_filter_by_token             ✓

Phase 6 Tests: 12/12 passing ✓ (all in DRY_RUN mode)
├── TestValidation
│   ├── test_validate_price_valid        ✓
│   ├── test_validate_price_rounds       ✓
│   ├── test_validate_price_invalid      ✓
│   ├── test_validate_size               ✓
│   └── test_position_limit              ✓
├── TestPlaceOrder
│   ├── test_place_order_success         ✓
│   ├── test_place_order_rejects_bad_price ✓
│   └── test_place_order_rejects_small_size ✓
├── TestCancelOrder
│   ├── test_cancel_order                ✓
│   └── test_cancel_all_orders           ✓
└── TestIntegration
    ├── test_place_fill_cancel_workflow  ✓
    └── test_with_real_market            ✓

Phase 7 Tests: 8/8 passing ✓
├── TestQuoteCalculation
│   ├── test_spread_calculation          ✓
│   └── test_requote_threshold           ✓
├── TestPositionLimits
│   └── test_skip_buy_when_long          ✓
├── TestMarketMakerLifecycle
│   ├── test_creates_and_stops           ✓
│   └── test_signal_handling             ✓
├── TestWithMockFeed
│   ├── test_places_quotes_on_healthy_feed ✓
│   └── test_cancels_on_unhealthy_feed   ✓
└── TestIntegration
    └── test_full_cycle_with_real_market ✓

Phase 8 Tests: 16/16 passing ✓
├── TestRiskStatus
│   ├── test_ok_by_default               ✓
│   ├── test_kill_switch                 ✓
│   └── test_reset_kill_switch           ✓
├── TestEnforceMode
│   ├── test_enforce_true_stops          ✓
│   ├── test_enforce_false_continues     ✓
│   └── test_kill_switch_always_enforced ✓
├── TestRiskEventLogging
│   ├── test_events_logged               ✓
│   └── test_event_details_captured      ✓
├── TestDailyLoss
│   ├── test_loss_limit_stop             ✓
│   ├── test_loss_warning                ✓
│   └── test_reset_daily_pnl             ✓
├── TestErrorRate
│   └── test_error_cooldown              ✓
├── TestPositionLimits
│   └── test_position_warning            ✓
├── TestGetStatus
│   └── test_get_status                  ✓
├── TestGlobalInstance
│   └── test_global_instance             ✓
└── TestIntegration
    └── test_data_gathering_workflow     ✓

Total: 86/86 tests passing ✓ (7 additional tests available with credentials)
```

## 📚 Documentation

- [Phase 1 Specification](phase1-environment-connectivity.md) - Complete Phase 1 requirements
- [Phase 2 Specification](phase2-market-discovery-v2.md) - Complete Phase 2 requirements
- [Phase 3 Specification](phase3-websocket-realtime.md) - Complete Phase 3 requirements
- [Phase 3.5 Specification](phase3_5-websocket-hardening-simplified.md) - Complete Phase 3.5 requirements
- [Phase 4 Specification](phase4-authentication.md) - Complete Phase 4 requirements
- [Phase 5 Specification](phase5-order-management-read.md) - Complete Phase 5 requirements
- [Phase 6 Specification](phase6-order-placement.md) - Complete Phase 6 requirements
- [Phase 7 Specification](phase7-market-maker.md) - Complete Phase 7 requirements
- [Phase 8 Specification](phase8-risk-controls.md) - Complete Phase 8 requirements
- [API Documentation](https://docs.polymarket.com/) - Polymarket API reference
- [Session Handoffs](thoughts/shared/handoffs/) - Development session notes

## 🔧 Configuration

The bot uses environment variables for configuration. Copy `.env.example` to `.env` and configure:

```bash
# === Network ===
CHAIN_ID=137

# === API Endpoints ===
CLOB_API_URL=https://clob.polymarket.com
GAMMA_API_URL=https://gamma-api.polymarket.com

# === Authentication (REQUIRED for trading) ===
# Get these by running derive_api_creds.py
POLY_PRIVATE_KEY=
POLY_API_KEY=
POLY_API_SECRET=
POLY_PASSPHRASE=

# === WebSocket ===
WS_MARKET_URL=wss://ws-subscriptions-clob.polymarket.com/ws/market
WS_RECONNECT_ATTEMPTS=10
WS_RECONNECT_BASE_DELAY=1.0
WS_RECONNECT_MAX_DELAY=60.0
WS_HEARTBEAT_INTERVAL=30.0
WS_STALE_DATA_THRESHOLD=60.0
```

⚠️ **Security Notes**:
- Never commit your `.env` file. Keep private keys secure.
- Use a separate wallet for the bot - never use your personal wallet
- See [Phase 4 Specification](phase4-authentication.md) for setup instructions

## 🤝 Contributing

This is a personal project built for learning and experimentation. Feel free to fork and adapt for your own use.

## ⚠️ Disclaimer

This bot is for educational purposes. Trading prediction markets involves financial risk. Use at your own risk. Always test thoroughly before deploying with real funds.

## 📄 License

MIT License - See LICENSE file for details

## 🔗 Links

- [Polymarket](https://polymarket.com) - Prediction market platform
- [Polymarket API Docs](https://docs.polymarket.com/) - Official API documentation
- [py-clob-client](https://github.com/Polymarket/py-clob-client) - Official Python client

---

**Current Status**: Phase 8 Complete ✓ | Ready for Phase 9 Live Testing
