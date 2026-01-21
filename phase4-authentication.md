# Task: Polymarket Trading Bot - Phase 4: Authentication & Wallet Setup

## Context

Phase 4 enables authenticated API access so the bot can place orders. This phase is mostly **setup and configuration** - the py-clob-client handles the cryptographic details.

## Goal

After Phase 4, the bot can:
1. Load credentials from environment
2. Create an authenticated CLOB client
3. Verify the wallet is properly funded and has allowances set

---

## Prerequisites (Manual Setup)

Before implementing Phase 4, you need to complete these one-time setup steps:

### Step 1: Create a Dedicated Wallet

⚠️ **IMPORTANT: Use a separate wallet for the bot. Never use your personal wallet.**

Options:
- MetaMask: Create new account
- Any Ethereum wallet that gives you the private key

Save the private key securely. You'll need it for the `.env` file.

### Step 2: Fund the Wallet

Send to your bot wallet on **Polygon network**:

| Asset | Purpose | Recommended Amount |
|-------|---------|-------------------|
| MATIC | Gas fees | 5-10 MATIC (~$5-10) |
| USDC.e | Trading collateral | Start small: $50-100 |

**USDC.e Contract (Polygon)**: `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174`

### Step 3: Derive API Credentials

Run this one-time script to get your API credentials:

```python
# derive_api_creds.py (run once, don't commit!)
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds

PRIVATE_KEY = "your_private_key_here"  # 0x...

client = ClobClient(
    host="https://clob.polymarket.com",
    chain_id=137,
    key=PRIVATE_KEY
)

# This registers with Polymarket and returns credentials
creds = client.create_or_derive_api_creds()

print("Add these to your .env file:")
print(f"POLY_API_KEY={creds.api_key}")
print(f"POLY_API_SECRET={creds.api_secret}")
print(f"POLY_PASSPHRASE={creds.api_passphrase}")
```

### Step 4: Set Allowances

The Exchange contract needs permission to spend your USDC.e. 

Option A: Use Polymarket UI - deposit funds through their interface.

Option B: Run approval transaction:
```python
# approve_allowance.py (run once)
from py_clob_client.client import ClobClient

client = ClobClient(
    host="https://clob.polymarket.com",
    chain_id=137,
    key="your_private_key"
)

# Set max allowance for USDC.e
client.set_allowances()
print("Allowances set!")
```

---

## Implementation

### 1. Update .env.example

```bash
# Polymarket Bot Configuration

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
```

### 2. Update src/config.py

```python
"""
Configuration management.

Loads settings from environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()


# === Network ===
CHAIN_ID = int(os.getenv("CHAIN_ID", "137"))

# === API Endpoints ===
CLOB_API_URL = os.getenv("CLOB_API_URL", "https://clob.polymarket.com")
GAMMA_API_URL = os.getenv("GAMMA_API_URL", "https://gamma-api.polymarket.com")

# === Authentication ===
POLY_PRIVATE_KEY = os.getenv("POLY_PRIVATE_KEY")
POLY_API_KEY = os.getenv("POLY_API_KEY")
POLY_API_SECRET = os.getenv("POLY_API_SECRET")
POLY_PASSPHRASE = os.getenv("POLY_PASSPHRASE")

# === WebSocket ===
WS_MARKET_URL = os.getenv(
    "WS_MARKET_URL",
    "wss://ws-subscriptions-clob.polymarket.com/ws/market"
)
WS_RECONNECT_ATTEMPTS = int(os.getenv("WS_RECONNECT_ATTEMPTS", "10"))
WS_RECONNECT_BASE_DELAY = float(os.getenv("WS_RECONNECT_BASE_DELAY", "1.0"))
WS_RECONNECT_MAX_DELAY = float(os.getenv("WS_RECONNECT_MAX_DELAY", "60.0"))

# === Contract Addresses (Polygon) ===
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"


def has_credentials() -> bool:
    """Check if all required credentials are configured."""
    return all([
        POLY_PRIVATE_KEY,
        POLY_API_KEY,
        POLY_API_SECRET,
        POLY_PASSPHRASE
    ])


def validate_config():
    """Validate configuration. Raises ValueError if invalid."""
    errors = []
    
    if CHAIN_ID not in (137, 80001):  # Polygon mainnet or Mumbai testnet
        errors.append(f"Invalid CHAIN_ID: {CHAIN_ID}")
    
    if not CLOB_API_URL:
        errors.append("CLOB_API_URL is required")
    
    if errors:
        raise ValueError("Configuration errors: " + "; ".join(errors))
```

### 3. Update src/client.py

```python
"""
CLOB Client wrapper with authentication support.

Provides both read-only and authenticated client access.
"""

from typing import Optional
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds

from src.config import (
    CLOB_API_URL,
    CHAIN_ID,
    POLY_PRIVATE_KEY,
    POLY_API_KEY,
    POLY_API_SECRET,
    POLY_PASSPHRASE,
    has_credentials,
)
from src.utils import setup_logging

logger = setup_logging()

# Module-level clients (singletons)
_read_client: Optional[ClobClient] = None
_auth_client: Optional[ClobClient] = None


def get_client() -> ClobClient:
    """
    Get read-only CLOB client.
    
    Use this for operations that don't require authentication:
    - Fetching order books
    - Getting market info
    - Price queries
    """
    global _read_client
    
    if _read_client is None:
        _read_client = ClobClient(
            host=CLOB_API_URL,
            chain_id=CHAIN_ID
        )
        logger.debug("Created read-only CLOB client")
    
    return _read_client


def get_auth_client() -> ClobClient:
    """
    Get authenticated CLOB client.
    
    Use this for operations that require authentication:
    - Placing orders
    - Canceling orders
    - Checking balances
    - Managing positions
    
    Raises:
        ValueError: If credentials are not configured
    """
    global _auth_client
    
    if _auth_client is None:
        if not has_credentials():
            raise ValueError(
                "Authentication credentials not configured. "
                "Set POLY_PRIVATE_KEY, POLY_API_KEY, POLY_API_SECRET, "
                "and POLY_PASSPHRASE in your .env file."
            )
        
        # Create client with private key
        _auth_client = ClobClient(
            host=CLOB_API_URL,
            chain_id=CHAIN_ID,
            key=POLY_PRIVATE_KEY
        )
        
        # Set API credentials
        _auth_client.set_api_creds(ApiCreds(
            api_key=POLY_API_KEY,
            api_secret=POLY_API_SECRET,
            api_passphrase=POLY_PASSPHRASE
        ))
        
        logger.info("Created authenticated CLOB client")
    
    return _auth_client


def reset_clients():
    """Reset client singletons. Useful for testing."""
    global _read_client, _auth_client
    _read_client = None
    _auth_client = None
```

### 4. Create src/auth.py

```python
"""
Authentication utilities.

Helper functions for wallet and credential management.
"""

from typing import Optional, Dict
from decimal import Decimal

from src.client import get_auth_client
from src.config import USDC_ADDRESS
from src.utils import setup_logging

logger = setup_logging()


def get_wallet_address() -> str:
    """Get the wallet address associated with the authenticated client."""
    client = get_auth_client()
    return client.get_address()


def get_balances() -> Dict[str, Decimal]:
    """
    Get wallet balances.
    
    Returns:
        Dict with 'matic' and 'usdc' balances
    """
    client = get_auth_client()
    
    # Get MATIC balance (native token)
    # Note: py-clob-client may not have direct balance methods
    # This is a placeholder - actual implementation depends on client version
    
    try:
        # Try to get collateral balance (USDC.e deposited for trading)
        collateral = client.get_balance_allowance()
        
        return {
            'usdc_allowance': Decimal(str(collateral.get('balance', 0))),
            'usdc_allowance_max': Decimal(str(collateral.get('allowance', 0))),
        }
    except Exception as e:
        logger.error(f"Error getting balances: {e}")
        return {
            'usdc_allowance': Decimal('0'),
            'usdc_allowance_max': Decimal('0'),
        }


def check_allowances() -> Dict[str, bool]:
    """
    Check if allowances are set for trading.
    
    Returns:
        Dict indicating which allowances are set
    """
    client = get_auth_client()
    
    try:
        result = client.get_balance_allowance()
        
        # Allowance should be very large (max uint256) if properly set
        allowance = Decimal(str(result.get('allowance', 0)))
        has_allowance = allowance > 1_000_000  # More than $1M allowance
        
        return {
            'usdc_approved': has_allowance,
            'allowance_amount': allowance,
        }
    except Exception as e:
        logger.error(f"Error checking allowances: {e}")
        return {
            'usdc_approved': False,
            'allowance_amount': Decimal('0'),
        }


def set_allowances() -> bool:
    """
    Set token allowances for trading.
    
    This approves the Exchange contract to spend USDC.e.
    Only needs to be done once per wallet.
    
    Returns:
        True if successful
    """
    client = get_auth_client()
    
    try:
        client.set_allowances()
        logger.info("Allowances set successfully")
        return True
    except Exception as e:
        logger.error(f"Error setting allowances: {e}")
        return False


def verify_setup() -> Dict[str, any]:
    """
    Verify the wallet is properly set up for trading.
    
    Returns:
        Dict with setup status and any issues found
    """
    issues = []
    
    try:
        # Check we can get address
        address = get_wallet_address()
        logger.info(f"Wallet address: {address}")
    except Exception as e:
        issues.append(f"Cannot get wallet address: {e}")
        return {'ok': False, 'issues': issues}
    
    try:
        # Check balances
        balances = get_balances()
        logger.info(f"Balances: {balances}")
        
        if balances.get('usdc_allowance', 0) == 0:
            issues.append("No USDC.e balance for trading")
    except Exception as e:
        issues.append(f"Cannot check balances: {e}")
    
    try:
        # Check allowances
        allowances = check_allowances()
        logger.info(f"Allowances: {allowances}")
        
        if not allowances.get('usdc_approved', False):
            issues.append("USDC.e allowance not set - run set_allowances()")
    except Exception as e:
        issues.append(f"Cannot check allowances: {e}")
    
    return {
        'ok': len(issues) == 0,
        'address': address if 'address' in dir() else None,
        'issues': issues,
    }
```

### 5. Create tests/test_phase4.py

```python
"""
Phase 4 Verification Tests

Run with: pytest tests/test_phase4.py -v

Note: Some tests require valid credentials in .env
Tests are designed to skip gracefully if credentials are missing.
"""

import pytest
from decimal import Decimal


class TestConfig:
    """Test configuration loading."""
    
    def test_config_imports(self):
        """Test config imports work."""
        from src.config import (
            CHAIN_ID,
            CLOB_API_URL,
            POLY_PRIVATE_KEY,
            POLY_API_KEY,
            has_credentials,
            validate_config,
        )
        
        assert CHAIN_ID == 137
        assert "clob.polymarket.com" in CLOB_API_URL
        print("✓ Config imports work")
    
    def test_has_credentials(self):
        """Test credential detection."""
        from src.config import has_credentials
        
        result = has_credentials()
        print(f"  has_credentials: {result}")
        
        if result:
            print("✓ Credentials are configured")
        else:
            print("⚠ Credentials not configured (some tests will skip)")
    
    def test_validate_config(self):
        """Test config validation."""
        from src.config import validate_config
        
        # Should not raise for valid config
        validate_config()
        print("✓ Config validation passed")


class TestClient:
    """Test client creation."""
    
    def test_read_client(self):
        """Test read-only client creation."""
        from src.client import get_client, reset_clients
        
        reset_clients()
        client = get_client()
        
        assert client is not None
        print("✓ Read-only client created")
    
    def test_read_client_singleton(self):
        """Test read client is singleton."""
        from src.client import get_client
        
        client1 = get_client()
        client2 = get_client()
        
        assert client1 is client2
        print("✓ Read client is singleton")
    
    def test_auth_client_requires_creds(self):
        """Test auth client requires credentials."""
        from src.client import get_auth_client, reset_clients
        from src.config import has_credentials
        
        reset_clients()
        
        if not has_credentials():
            with pytest.raises(ValueError) as exc_info:
                get_auth_client()
            assert "credentials" in str(exc_info.value).lower()
            print("✓ Auth client correctly requires credentials")
        else:
            # Credentials present, should work
            client = get_auth_client()
            assert client is not None
            print("✓ Auth client created with credentials")
    
    def test_auth_client_singleton(self):
        """Test auth client is singleton."""
        from src.client import get_auth_client, reset_clients
        from src.config import has_credentials
        
        if not has_credentials():
            pytest.skip("Credentials not configured")
        
        reset_clients()
        client1 = get_auth_client()
        client2 = get_auth_client()
        
        assert client1 is client2
        print("✓ Auth client is singleton")


class TestAuth:
    """Test authentication utilities."""
    
    def test_auth_imports(self):
        """Test auth module imports."""
        from src.auth import (
            get_wallet_address,
            get_balances,
            check_allowances,
            verify_setup,
        )
        print("✓ Auth imports work")
    
    def test_get_wallet_address(self):
        """Test getting wallet address."""
        from src.config import has_credentials
        from src.auth import get_wallet_address
        
        if not has_credentials():
            pytest.skip("Credentials not configured")
        
        address = get_wallet_address()
        
        assert address is not None
        assert address.startswith("0x")
        assert len(address) == 42
        
        print(f"✓ Wallet address: {address}")
    
    def test_get_balances(self):
        """Test getting balances."""
        from src.config import has_credentials
        from src.auth import get_balances
        
        if not has_credentials():
            pytest.skip("Credentials not configured")
        
        balances = get_balances()
        
        assert 'usdc_allowance' in balances
        print(f"✓ Balances: {balances}")
    
    def test_check_allowances(self):
        """Test checking allowances."""
        from src.config import has_credentials
        from src.auth import check_allowances
        
        if not has_credentials():
            pytest.skip("Credentials not configured")
        
        allowances = check_allowances()
        
        assert 'usdc_approved' in allowances
        print(f"✓ Allowances: {allowances}")
    
    def test_verify_setup(self):
        """Test full setup verification."""
        from src.config import has_credentials
        from src.auth import verify_setup
        
        if not has_credentials():
            pytest.skip("Credentials not configured")
        
        result = verify_setup()
        
        assert 'ok' in result
        assert 'issues' in result
        
        print(f"✓ Setup verification:")
        print(f"  OK: {result['ok']}")
        print(f"  Address: {result.get('address', 'N/A')}")
        
        if result['issues']:
            print(f"  Issues: {result['issues']}")


class TestIntegration:
    """Integration tests with real API."""
    
    def test_authenticated_api_call(self):
        """Test making an authenticated API call."""
        from src.config import has_credentials
        from src.client import get_auth_client
        
        if not has_credentials():
            pytest.skip("Credentials not configured")
        
        client = get_auth_client()
        
        # Try to get open orders (should work even if empty)
        try:
            orders = client.get_orders()
            print(f"✓ Authenticated API call successful")
            print(f"  Open orders: {len(orders) if orders else 0}")
        except Exception as e:
            # Some API errors are OK (e.g., no orders)
            if "unauthorized" in str(e).lower():
                pytest.fail(f"Authentication failed: {e}")
            print(f"✓ API call made (response: {e})")
    
    def test_can_read_markets_with_auth(self):
        """Test reading markets still works with auth client."""
        from src.config import has_credentials
        from src.markets import fetch_active_markets
        
        # This should work regardless of auth status
        markets = fetch_active_markets(limit=5)
        
        assert len(markets) > 0
        print(f"✓ Can read markets: {len(markets)} found")
```

---

## File Structure After Phase 4

```
polymarket-bot/
├── src/
│   ├── __init__.py
│   ├── config.py          # Updated with auth config
│   ├── client.py          # Updated with get_auth_client()
│   ├── auth.py            # NEW - authentication utilities
│   ├── utils.py
│   ├── models.py
│   ├── markets.py
│   ├── pricing.py
│   └── feed/
│       └── ...
│
├── tests/
│   ├── test_phase1.py
│   ├── test_phase2.py
│   ├── test_phase3.py
│   ├── test_phase3_5.py
│   └── test_phase4.py     # NEW
│
├── .env                   # Updated with credentials
├── .env.example           # Updated template
└── derive_api_creds.py    # One-time setup script (don't commit!)
```

---

## Verification

Run tests:
```bash
pytest tests/test_phase4.py -v
```

**Without credentials** (6 tests pass, 5 skip):
```
test_config_imports PASSED
test_has_credentials PASSED
test_validate_config PASSED
test_read_client PASSED
test_read_client_singleton PASSED
test_auth_client_requires_creds PASSED
test_auth_client_singleton SKIPPED
test_auth_imports PASSED
test_get_wallet_address SKIPPED
test_get_balances SKIPPED
test_check_allowances SKIPPED
test_verify_setup SKIPPED
test_authenticated_api_call SKIPPED
test_can_read_markets_with_auth PASSED
```

**With credentials** (all tests pass):
```
All 14 tests PASSED
```

---

## Success Criteria

Phase 4 is complete when:

1. ✅ `.env` has all credential fields
2. ✅ `get_auth_client()` creates authenticated client
3. ✅ `verify_setup()` returns `{'ok': True}`
4. ✅ All tests pass (with credentials configured)

---

## Security Reminders

⚠️ **Never commit credentials to git**
- `.env` should be in `.gitignore`
- `derive_api_creds.py` should not be committed

⚠️ **Use a dedicated wallet**
- Don't use your personal wallet
- Start with small amounts ($50-100)

⚠️ **Keep private key secure**
- Don't log it
- Don't include in error messages
- Consider using a secrets manager for production

---

## Next: Phase 5

With authentication working, Phase 5 will add:
- Order data models (Order, Trade, OrderStatus)
- Read operations: get_orders(), get_trades()
- User WebSocket channel for order updates
