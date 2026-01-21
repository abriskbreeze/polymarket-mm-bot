"""
Order queries - unified interface for real and simulated orders.
"""

from typing import List, Optional
from decimal import Decimal

from src.config import DRY_RUN, has_credentials
from src.models import Order, Trade, OrderSide, OrderStatus
from src.simulator import get_simulator
from src.utils import setup_logging

logger = setup_logging()


def get_open_orders(token_id: Optional[str] = None) -> List[Order]:
    """Get open orders."""
    if DRY_RUN:
        return get_simulator().get_open_orders(token_id)

    if not has_credentials():
        return []

    from src.client import get_auth_client

    try:
        response = get_auth_client().get_orders()
        orders = []

        for r in (response or []):
            if r.get('status') != 'LIVE':
                continue
            order = Order(
                id=r['id'],
                token_id=r['asset_id'],
                side=OrderSide(r['side']),
                price=Decimal(str(r['price'])),
                size=Decimal(str(r.get('original_size', r.get('size', 0)))),
                filled=Decimal(str(r.get('size_matched', 0))),
                status=OrderStatus.LIVE,
                is_simulated=False
            )
            if token_id is None or order.token_id == token_id:
                orders.append(order)
        return orders

    except Exception as e:
        logger.error(f"Error getting orders: {e}")
        return []


def get_trades(token_id: Optional[str] = None, limit: int = 50) -> List[Trade]:
    """Get recent trades."""
    if DRY_RUN:
        return get_simulator().get_trades(token_id)

    if not has_credentials():
        return []

    from src.client import get_auth_client

    try:
        response = get_auth_client().get_trades()
        trades = []

        for r in (response or [])[:limit]:
            trade = Trade(
                id=r['id'],
                order_id=r.get('order_id', ''),
                token_id=r['asset_id'],
                side=OrderSide(r['side']),
                price=Decimal(str(r['price'])),
                size=Decimal(str(r['size'])),
                is_simulated=False
            )
            if token_id is None or trade.token_id == token_id:
                trades.append(trade)
        return trades

    except Exception as e:
        logger.error(f"Error getting trades: {e}")
        return []


def get_position(token_id: str) -> Decimal:
    """Get net position for a token (positive = long)."""
    if DRY_RUN:
        return get_simulator().get_position(token_id)

    trades = get_trades(token_id)
    position = Decimal("0")
    for t in trades:
        if t.side == OrderSide.BUY:
            position += t.size
        else:
            position -= t.size
    return position
