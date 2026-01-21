"""
Order placement and management.

Handles both DRY_RUN (simulated) and LIVE (real) modes.
"""

from typing import Optional
from decimal import Decimal, ROUND_DOWN

from src.config import (
    DRY_RUN,
    MAX_POSITION_PER_MARKET,
    MAX_ORDER_SIZE,
    MIN_ORDER_SIZE,
    has_credentials
)
from src.models import Order, OrderSide, OrderStatus
from src.simulator import get_simulator
from src.utils import setup_logging

logger = setup_logging()


class OrderError(Exception):
    """Order placement error."""
    pass


def get_tick_size(token_id: str) -> Decimal:
    """
    Get tick size for a token.
    Most Polymarket markets use 0.01.
    """
    # Default tick size - could fetch from API later
    return Decimal("0.01")


def round_to_tick(price: Decimal, tick_size: Decimal) -> Decimal:
    """Round price down to nearest tick."""
    return (price / tick_size).quantize(Decimal("1"), rounding=ROUND_DOWN) * tick_size


def validate_price(price: Decimal, token_id: str) -> Decimal:
    """
    Validate and round price to tick size.

    Returns rounded price or raises OrderError.
    """
    if price <= Decimal("0") or price >= Decimal("1"):
        raise OrderError(f"Price must be between 0 and 1, got {price}")

    tick = get_tick_size(token_id)
    rounded = round_to_tick(price, tick)

    # Ensure still in valid range after rounding
    if rounded <= Decimal("0"):
        rounded = tick
    if rounded >= Decimal("1"):
        rounded = Decimal("1") - tick

    return rounded


def validate_size(size: Decimal) -> None:
    """Validate order size. Raises OrderError if invalid."""
    if size < MIN_ORDER_SIZE:
        raise OrderError(f"Size {size} below minimum {MIN_ORDER_SIZE}")

    if size > MAX_ORDER_SIZE:
        raise OrderError(f"Size {size} exceeds maximum {MAX_ORDER_SIZE}")


def check_position_limit(token_id: str, side: OrderSide, size: Decimal) -> None:
    """Check if order would exceed position limit. Raises OrderError if exceeded."""
    from src.orders import get_position

    current = get_position(token_id)

    if side == OrderSide.BUY:
        new_position = current + size
    else:
        new_position = current - size

    if abs(new_position) > MAX_POSITION_PER_MARKET:
        raise OrderError(
            f"Would exceed position limit. "
            f"Current: {current}, After: {new_position}, Limit: ±{MAX_POSITION_PER_MARKET}"
        )


def place_order(
    token_id: str,
    side: OrderSide,
    price: Decimal,
    size: Decimal
) -> Order:
    """
    Place an order.

    In DRY_RUN mode: Creates simulated order
    In LIVE mode: Places real order on exchange

    Args:
        token_id: The token to trade
        side: BUY or SELL
        price: Limit price (0 < price < 1)
        size: Order size in contracts

    Returns:
        Order object

    Raises:
        OrderError: If validation fails or order rejected
    """
    # Validate
    price = validate_price(price, token_id)
    validate_size(size)
    check_position_limit(token_id, side, size)

    if DRY_RUN:
        return get_simulator().create_order(token_id, side, price, size)

    # === LIVE MODE ===
    if not has_credentials():
        raise OrderError("No credentials configured for live trading")

    from src.client import get_auth_client
    client = get_auth_client()

    try:
        logger.info(f"[LIVE] Placing: {side.value} {size} @ {price}")

        # Build and post order using py-clob-client
        order_args = {
            "token_id": token_id,
            "price": float(price),
            "size": float(size),
            "side": side.value,
        }

        signed_order = client.create_order(order_args)
        response = client.post_order(signed_order)

        if not response:
            raise OrderError("Order rejected: empty response")

        order_id = response.get("id") or response.get("orderID")
        if not order_id:
            raise OrderError(f"Order rejected: {response}")

        logger.info(f"[LIVE] Order placed: {order_id}")

        return Order(
            id=order_id,
            token_id=token_id,
            side=side,
            price=price,
            size=size,
            filled=Decimal("0"),
            status=OrderStatus.LIVE,
            is_simulated=False
        )

    except OrderError:
        raise
    except Exception as e:
        raise OrderError(f"Order failed: {e}")


def cancel_order(order_id: str) -> bool:
    """
    Cancel an order by ID.

    Returns True if cancelled, False otherwise.
    """
    if DRY_RUN:
        return get_simulator().cancel_order(order_id)

    if not has_credentials():
        logger.warning("No credentials for live trading")
        return False

    from src.client import get_auth_client

    try:
        logger.info(f"[LIVE] Cancelling: {order_id}")
        get_auth_client().cancel(order_id)
        return True
    except Exception as e:
        logger.error(f"Cancel failed for {order_id}: {e}")
        return False


def cancel_all_orders(token_id: Optional[str] = None) -> int:
    """
    Cancel all open orders, optionally filtered by token.

    Returns count of cancelled orders.
    """
    if DRY_RUN:
        return get_simulator().cancel_all(token_id)

    if not has_credentials():
        return 0

    from src.client import get_auth_client
    from src.orders import get_open_orders

    client = get_auth_client()

    orders = get_open_orders(token_id)
    cancelled = 0

    for order in orders:
        try:
            client.cancel(order.id)
            cancelled += 1
        except Exception as e:
            logger.warning(f"Failed to cancel {order.id}: {e}")

    if cancelled:
        logger.info(f"[LIVE] Cancelled {cancelled} orders")

    return cancelled
