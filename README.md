# Polymarket Market-Making Bot

A sophisticated market-making trading bot for Polymarket prediction markets, built incrementally with test-driven development.

[![Tests](https://img.shields.io/badge/tests-29%2F29%20passing-brightgreen)](tests/)
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
│   ├── utils.py               # Logging and utility functions
│   ├── models.py              # Data models (Market, OrderBook, etc.)
│   ├── markets.py             # Market discovery (Gamma API)
│   ├── pricing.py             # Pricing and order books (CLOB API)
│   └── websocket_client.py    # WebSocket real-time data (Phase 3)
├── tests/
│   ├── __init__.py
│   ├── test_phase1.py     # Phase 1 verification tests
│   ├── test_phase2.py     # Phase 2 verification tests
│   └── test_phase3.py     # Phase 3 verification tests
├── thoughts/
│   └── shared/
│       └── handoffs/      # Session handoff documents
├── .env.example           # Environment variable template
├── .gitignore
├── README.md
├── requirements.txt
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

- **[x] Phase 3: WebSocket Real-Time Data** _(Current)_
  - WebSocket connection management with auto-reconnect
  - Real-time orderbook updates
  - Price change and trade notifications
  - Local order book maintenance
  - Callback architecture for event handling
  - Test suite: 12/12 passing ✓

### 🔜 Upcoming Phases

- **[ ] Phase 4: Authentication & Wallet Setup**
  - Private key management
  - Wallet integration
  - Authentication flow

- **[ ] Phase 5: Order Management (Read Operations)**
  - Order status tracking
  - Position monitoring
  - Balance checking

- **[ ] Phase 6: Order Placement & Cancellation**
  - Order creation
  - Order modification
  - Cancellation logic

- **[ ] Phase 7: Market Making Core Logic**
  - Spread calculation
  - Quote generation
  - Inventory management

- **[ ] Phase 8: Risk Management**
  - Position limits
  - Exposure tracking
  - Safety mechanisms

- **[ ] Phase 9: Arbitrage Detection**
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

Phase 3 Tests: 12/12 passing ✓
├── TestWebSocketClient
│   ├── test_import_websocket_client     ✓
│   ├── test_client_instantiation        ✓
│   ├── test_connect_disconnect          ✓
│   ├── test_subscribe_to_market         ✓
│   ├── test_receive_market_data         ✓
│   ├── test_order_book_maintenance      ✓
│   ├── test_callbacks_are_called        ✓
│   └── test_multiple_subscriptions      ✓
├── TestConnectionState
│   └── test_state_enum_values           ✓
├── TestMarketData
│   ├── test_market_data_creation        ✓
│   └── test_stale_data_detection        ✓
└── TestIntegration
    └── test_full_websocket_flow         ✓

Total: 29/29 tests passing ✓
```

## 📚 Documentation

- [Phase 1 Specification](phase1-environment-connectivity.md) - Complete Phase 1 requirements
- [Phase 2 Specification](phase2-market-discovery-v2.md) - Complete Phase 2 requirements
- [Phase 3 Specification](phase3-websocket-realtime.md) - Complete Phase 3 requirements
- [API Documentation](https://docs.polymarket.com/) - Polymarket API reference
- [Session Handoffs](thoughts/shared/handoffs/) - Development session notes

## 🔧 Configuration

The bot uses environment variables for configuration. Copy `.env.example` to `.env` and configure:

```bash
# Required for trading (Phase 4+)
PRIVATE_KEY=your_private_key_here
FUNDER_ADDRESS=your_funder_address_here

# Optional overrides
CLOB_API_URL=https://clob.polymarket.com
GAMMA_API_URL=https://gamma-api.polymarket.com
```

⚠️ **Security Note**: Never commit your `.env` file. Keep private keys secure.

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

**Current Status**: Phase 3 Complete ✓ | Ready for Phase 4 Development
