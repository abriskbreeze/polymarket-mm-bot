"""
Polymarket CLOB API client wrapper
"""

from py_clob_client.client import ClobClient
from src.config import CLOB_API_URL

# Singleton instance
_client_instance = None


def get_client():
    """
    Get or create a Polymarket CLOB client instance

    Uses singleton pattern to reuse the same client connection.
    Creates client in read-only mode (no authentication).

    Returns:
        ClobClient: Configured client instance
    """
    global _client_instance

    if _client_instance is None:
        # Initialize client in read-only mode (no private key needed)
        _client_instance = ClobClient(host=CLOB_API_URL)

    return _client_instance
