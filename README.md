# Polymarket Market-Making Bot

A sophisticated market-making trading bot for Polymarket prediction markets, built incrementally with test-driven development.

[![Tests](https://img.shields.io/badge/tests-6%2F6%20passing-brightgreen)](tests/test_phase1.py)
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
│   ├── config.py          # Configuration management
│   ├── client.py          # Polymarket CLOB API client wrapper
│   └── utils.py           # Logging and utility functions
├── tests/
│   ├── __init__.py
│   └── test_phase1.py     # Phase 1 verification tests
├── thoughts/
│   └── shared/
│       └── handoffs/      # Session handoff documents
├── .env.example           # Environment variable template
├── .gitignore
├── README.md
├── requirements.txt
└── phase1-environment-connectivity.md  # Phase 1 specification

```

## 🏗️ Development Phases

This project is built incrementally across 10 phases. Each phase must pass all tests before proceeding to the next.

### ✅ Completed Phases

- **[x] Phase 1: Environment & Connectivity** _(Current)_
  - Project structure setup
  - Configuration management with environment variables
  - Polymarket CLOB API client wrapper (read-only mode)
  - Logging utilities
  - Test suite: 6/6 passing ✓

### 🔜 Upcoming Phases

- **[ ] Phase 2: Market Discovery & Data Fetching**
  - Market listing and filtering
  - Orderbook fetching and parsing
  - Price data retrieval

- **[ ] Phase 3: WebSocket Real-Time Data**
  - WebSocket connection management
  - Real-time orderbook updates
  - Event stream processing

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
```

## 📚 Documentation

- [Phase 1 Specification](phase1-environment-connectivity.md) - Complete Phase 1 requirements
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

**Current Status**: Phase 1 Complete ✓ | Ready for Phase 2 Development
