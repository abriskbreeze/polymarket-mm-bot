"""
Authentication utilities.

Helper functions for wallet and credential management.
"""

from typing import Optional, Dict, Any
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


def check_allowances() -> Dict[str, Any]:
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


def verify_setup() -> Dict[str, Any]:
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
