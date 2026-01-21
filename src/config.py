"""
Configuration management.

Loads settings from environment variables.
"""

import os
from decimal import Decimal
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
WS_HEARTBEAT_INTERVAL = float(os.getenv("WS_HEARTBEAT_INTERVAL", "30.0"))
WS_STALE_DATA_THRESHOLD = float(os.getenv("WS_STALE_DATA_THRESHOLD", "60.0"))

# === Contract Addresses (Polygon) ===
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"

# === Trading ===
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
MAX_POSITION_PER_MARKET = Decimal(os.getenv("MAX_POSITION_PER_MARKET", "100"))
MAX_ORDER_SIZE = Decimal(os.getenv("MAX_ORDER_SIZE", "50"))
MIN_ORDER_SIZE = Decimal(os.getenv("MIN_ORDER_SIZE", "5"))

# === Market Making ===
MM_SPREAD = Decimal(os.getenv("MM_SPREAD", "0.04"))        # 4 cents each side
MM_SIZE = Decimal(os.getenv("MM_SIZE", "10"))              # Order size
MM_REQUOTE_THRESHOLD = Decimal(os.getenv("MM_REQUOTE_THRESHOLD", "0.02"))  # Requote if mid moves 2c
MM_POSITION_LIMIT = Decimal(os.getenv("MM_POSITION_LIMIT", "50"))  # Max position before skipping side
MM_LOOP_INTERVAL = float(os.getenv("MM_LOOP_INTERVAL", "1.0"))     # Seconds between loops

# === Risk Management ===
RISK_MAX_DAILY_LOSS = Decimal(os.getenv("RISK_MAX_DAILY_LOSS", "50"))  # Stop if lose $50
RISK_MAX_POSITION = Decimal(os.getenv("RISK_MAX_POSITION", "100"))     # Max position per token
RISK_MAX_TOTAL_EXPOSURE = Decimal(os.getenv("RISK_MAX_TOTAL_EXPOSURE", "500"))  # Total across all
RISK_ERROR_COOLDOWN = int(os.getenv("RISK_ERROR_COOLDOWN", "60"))      # Seconds to pause after errors
RISK_MAX_ERRORS_PER_MINUTE = int(os.getenv("RISK_MAX_ERRORS_PER_MINUTE", "5"))  # Error rate limit

# Enforce risk limits? Default: OFF in dry-run (gather data), ON in live (protect money)
_default_enforce = "false" if DRY_RUN else "true"
RISK_ENFORCE = os.getenv("RISK_ENFORCE", _default_enforce).lower() == "true"

# === Simulation ===
SIMULATED_FEE_RATE = Decimal(os.getenv("SIMULATED_FEE_RATE", "0.001"))  # 0.1% per trade

# === Rate Limiting ===
RATE_LIMIT_ORDERS_PER_SECOND = float(os.getenv("RATE_LIMIT_ORDERS_PER_SECOND", "5"))
RATE_LIMIT_DATA_PER_SECOND = float(os.getenv("RATE_LIMIT_DATA_PER_SECOND", "10"))


def has_credentials() -> bool:
    """Check if all required credentials are configured."""
    return all([
        POLY_PRIVATE_KEY,
        POLY_API_KEY,
        POLY_API_SECRET,
        POLY_PASSPHRASE
    ])


def get_mode_string() -> str:
    """Get human-readable mode string."""
    return "DRY RUN (paper trading)" if DRY_RUN else "LIVE"


def validate_config():
    """Validate configuration. Raises ValueError if invalid."""
    errors = []

    if CHAIN_ID not in (137, 80001):  # Polygon mainnet or Mumbai testnet
        errors.append(f"Invalid CHAIN_ID: {CHAIN_ID}")

    if not CLOB_API_URL:
        errors.append("CLOB_API_URL is required")

    if errors:
        raise ValueError("Configuration errors: " + "; ".join(errors))
