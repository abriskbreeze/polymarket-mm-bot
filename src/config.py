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


def has_trading_credentials():
    """
    Check if trading credentials are configured

    Returns:
        bool: True if both PRIVATE_KEY and FUNDER_ADDRESS are set
    """
    return bool(PRIVATE_KEY and FUNDER_ADDRESS)
