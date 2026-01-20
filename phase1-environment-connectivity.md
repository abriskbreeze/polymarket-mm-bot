# Task: Polymarket Trading Bot - Phase 1: Environment & Connectivity

## Context

I'm building a market-making trading bot for Polymarket. This is Phase 1 of a 10-phase iterative build. Each phase must be verified working before proceeding to the next.

## Objective

Establish the development environment and verify basic API connectivity to Polymarket's CLOB API.

## Requirements

### 1. Create Project Structure

```
/polymarket-bot
├── /src
│   ├── __init__.py
│   ├── config.py
│   ├── client.py
│   └── utils.py
├── /tests
│   ├── __init__.py
│   └── test_phase1.py
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

### 2. requirements.txt

Include these dependencies:

```
py-clob-client
python-dotenv
websockets
pandas
pytest
requests
```

### 3. config.py

Create configuration module that:

- Loads environment variables from .env file using `python-dotenv`
- Defines constants:
  - `CLOB_API_URL = "https://clob.polymarket.com"`
  - `GAMMA_API_URL = "https://gamma-api.polymarket.com"`
  - `CHAIN_ID = 137` (Polygon)
- Has placeholders for (loaded from env, optional for now):
  - `PRIVATE_KEY`
  - `FUNDER_ADDRESS`
- Provides a function to check if trading credentials are configured

### 4. client.py

Create a client module that:

- Imports `ClobClient` from `py_clob_client.client`
- Initializes `ClobClient` in **read-only mode** (no private key or authentication needed yet)
- Provides a `get_client()` function that returns a configured client instance
- Uses singleton pattern to reuse client connection
- The read-only client only needs the host URL: `ClobClient(host="https://clob.polymarket.com")`

### 5. utils.py

Create utility module with:

- `setup_logging()` function that configures Python logging with:
  - Timestamp, level, and message format
  - Console handler
  - Returns configured logger
- `format_timestamp(ts)` helper function for formatting timestamps

### 6. .env.example

```
# Polymarket Bot Configuration
# Copy this to .env and fill in values

# Required for trading (Phase 4+)
PRIVATE_KEY=
FUNDER_ADDRESS=

# Optional overrides
CLOB_API_URL=https://clob.polymarket.com
GAMMA_API_URL=https://gamma-api.polymarket.com
```

### 7. .gitignore

```
# Environment
.env
.env.local

# Python
*.pyc
__pycache__/
*.py[cod]
*$py.class
.pytest_cache/
*.egg-info/
dist/
build/

# Virtual environments
venv/
env/
.venv/

# IDE
.idea/
.vscode/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Logs
*.log
logs/
```

### 8. README.md

```markdown
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
```

### 9. tests/test_phase1.py

```python
"""
Phase 1 Verification Test
Run with: pytest tests/test_phase1.py -v

Phase 1 is ONLY complete when all tests pass.
"""

import pytest


def test_config_loads():
    """Verify configuration loads correctly"""
    from src.config import CLOB_API_URL, GAMMA_API_URL, CHAIN_ID
    
    assert CLOB_API_URL == "https://clob.polymarket.com"
    assert GAMMA_API_URL == "https://gamma-api.polymarket.com"
    assert CHAIN_ID == 137
    print(f"✓ Config loaded: CLOB_API_URL={CLOB_API_URL}, CHAIN_ID={CHAIN_ID}")


def test_client_creation():
    """Verify client can be instantiated"""
    from src.client import get_client
    
    client = get_client()
    assert client is not None, "Client should not be None"
    print("✓ Client created successfully")


def test_client_connectivity():
    """Verify we can connect to Polymarket CLOB API"""
    from src.client import get_client
    
    client = get_client()
    
    # Test 1: Basic connectivity - get_ok() returns "OK" string
    result = client.get_ok()
    assert result == "OK", f"Expected 'OK', got {result}"
    print(f"✓ API connectivity verified: {result}")


def test_server_time():
    """Verify we can get server time"""
    from src.client import get_client
    
    client = get_client()
    
    # get_server_time() returns the server timestamp
    server_time = client.get_server_time()
    assert server_time is not None, "Server time should not be None"
    print(f"✓ Server time: {server_time}")


def test_client_singleton():
    """Verify client uses singleton pattern"""
    from src.client import get_client
    
    client1 = get_client()
    client2 = get_client()
    assert client1 is client2, "get_client() should return same instance"
    print("✓ Singleton pattern verified")


def test_logging_setup():
    """Verify logging utility works"""
    from src.utils import setup_logging
    
    logger = setup_logging()
    assert logger is not None, "Logger should not be None"
    logger.info("Test log message")
    print("✓ Logging setup verified")
```

## Verification Gate

After creating all files, run these commands:

```bash
cd polymarket-bot
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
pytest tests/test_phase1.py -v
```

## Success Criteria

**Phase 1 is ONLY complete when ALL of these tests pass:**

```
tests/test_phase1.py::test_config_loads PASSED
tests/test_phase1.py::test_client_creation PASSED
tests/test_phase1.py::test_client_connectivity PASSED
tests/test_phase1.py::test_server_time PASSED
tests/test_phase1.py::test_client_singleton PASSED
tests/test_phase1.py::test_logging_setup PASSED
```

## Expected Final Output

```
========================= test session starts ==========================
collected 6 items

tests/test_phase1.py::test_config_loads PASSED
tests/test_phase1.py::test_client_creation PASSED
tests/test_phase1.py::test_client_connectivity PASSED
tests/test_phase1.py::test_server_time PASSED
tests/test_phase1.py::test_client_singleton PASSED
tests/test_phase1.py::test_logging_setup PASSED

========================== 6 passed in X.XXs ===========================
```

## Important Notes

- Do NOT attempt any authenticated operations yet (no trading)
- Do NOT proceed to Phase 2 until ALL tests pass
- If tests fail, debug and fix before moving on
- The read-only client does not require any API keys or private keys
- If you encounter import errors, ensure `__init__.py` files are created in both `/src` and `/tests` directories
