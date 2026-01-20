# Polymarket Trading Bot

A market-making bot for Polymarket prediction markets.

## Setup

1. Clone the repository
2. Create virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and configure (optional for Phase 1)

## Running Tests

```bash
pytest tests/ -v
```

## Project Structure

- `/src` - Main source code
- `/tests` - Test files
- `config.py` - Configuration management
- `client.py` - Polymarket API client wrapper

## Development Phases

- [x] Phase 1: Environment & Connectivity
- [ ] Phase 2: Market Discovery & Data Fetching
- [ ] Phase 3: WebSocket Real-Time Data
- [ ] Phase 4: Authentication & Wallet Setup
- [ ] Phase 5: Order Management (Read Operations)
- [ ] Phase 6: Order Placement & Cancellation
- [ ] Phase 7: Market Making Core Logic
- [ ] Phase 8: Risk Management
- [ ] Phase 9: Arbitrage Detection
- [ ] Phase 10: Production Hardening
