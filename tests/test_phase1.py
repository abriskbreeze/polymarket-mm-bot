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
