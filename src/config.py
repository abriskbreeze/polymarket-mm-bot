"""
Configuration management for Polymarket Trading Bot
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API URLs
CLOB_API_URL = os.getenv("CLOB_API_URL", "https://clob.polymarket.com")
GAMMA_API_URL = os.getenv("GAMMA_API_URL", "https://gamma-api.polymarket.com")

# Blockchain configuration
CHAIN_ID = 137  # Polygon

# Trading credentials (optional for Phase 1, required for Phase 4+)
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
FUNDER_ADDRESS = os.getenv("FUNDER_ADDRESS")


# WebSocket Configuration
WS_MARKET_URL = os.getenv(
    "WS_MARKET_URL",
    "wss://ws-subscriptions-clob.polymarket.com/ws/market"
)

# Reconnection settings
WS_RECONNECT_ATTEMPTS = int(os.getenv("WS_RECONNECT_ATTEMPTS", "10"))
WS_RECONNECT_BASE_DELAY = float(os.getenv("WS_RECONNECT_BASE_DELAY", "1.0"))
WS_RECONNECT_MAX_DELAY = float(os.getenv("WS_RECONNECT_MAX_DELAY", "60.0"))
WS_HEARTBEAT_INTERVAL = float(os.getenv("WS_HEARTBEAT_INTERVAL", "30.0"))
WS_STALE_DATA_THRESHOLD = float(os.getenv("WS_STALE_DATA_THRESHOLD", "60.0"))


def has_trading_credentials():
    """
    Check if trading credentials are configured

    Returns:
        bool: True if both PRIVATE_KEY and FUNDER_ADDRESS are set
    """
    return bool(PRIVATE_KEY and FUNDER_ADDRESS)
