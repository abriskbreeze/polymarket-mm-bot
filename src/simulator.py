"""
Simple order simulator for DRY_RUN mode.

Maintains orders, tracks fills, and calculates positions.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from decimal import Decimal
import uuid

from src.models import Order, Trade, OrderSide, OrderStatus
from src.utils import setup_logging

logger = setup_logging()


class OrderSimulator:
    """Simulates order execution for testing."""

    def __init__(self):
        self.orders: Dict[str, Order] = {}
        self.trades: List[Trade] = []
        self._positions: Dict[str, Decimal] = {}

    def create_order(
        self,
        token_id: str,
        side: OrderSide,
        price: Decimal,
        size: Decimal
    ) -> Order:
        """Create a simulated order."""
        order = Order(
            id=f"sim_{uuid.uuid4().hex[:12]}",
            token_id=token_id,
            side=side,
            price=price,
            size=size,
            filled=Decimal("0"),
            status=OrderStatus.LIVE,
            is_simulated=True,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        self.orders[order.id] = order
        logger.debug(f"[SIM] Created: {side.value} {size} @ {price}")
        return order

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order by ID."""
        order = self.orders.get(order_id)
        if not order or not order.is_live:
            return False

        order.status = OrderStatus.CANCELLED
        logger.debug(f"[SIM] Cancelled: {order_id}")
        return True

    def cancel_all(self, token_id: Optional[str] = None) -> int:
        """Cancel all open orders, optionally filtered by token."""
        cancelled = 0

        for order in list(self.orders.values()):
            if not order.is_live:
                continue
            if token_id and order.token_id != token_id:
                continue

            order.status = OrderStatus.CANCELLED
            cancelled += 1

        if cancelled:
            logger.debug(f"[SIM] Cancelled {cancelled} orders")
        return cancelled

    def _update_position(self, token_id: str, side: OrderSide, size: Decimal):
        """Update cached position after a fill."""
        if token_id not in self._positions:
            self._positions[token_id] = Decimal("0")

        if side == OrderSide.BUY:
            self._positions[token_id] += size
        else:
            self._positions[token_id] -= size

    def check_fills(self, token_id: str, bid: Decimal, ask: Decimal) -> int:
        """
        Check if any orders should fill based on market prices.

        Args:
            token_id: Token to check
            bid: Current best bid
            ask: Current best ask

        Returns:
            Number of orders filled
        """
        filled_count = 0

        for order in list(self.orders.values()):
            if not order.is_live or order.token_id != token_id:
                continue

            should_fill = False

            if order.side == OrderSide.BUY and order.price >= ask:
                # Buy order at/above ask - would cross
                should_fill = True
            elif order.side == OrderSide.SELL and order.price <= bid:
                # Sell order at/below bid - would cross
                should_fill = True

            if should_fill:
                # Create trade
                from src.config import SIMULATED_FEE_RATE
                fee = order.price * order.size * SIMULATED_FEE_RATE

                trade = Trade(
                    id=f"trade_{uuid.uuid4().hex[:12]}",
                    order_id=order.id,
                    token_id=order.token_id,
                    side=order.side,
                    price=order.price,
                    size=order.size,
                    fee=fee,
                    is_simulated=True
                )
                self.trades.append(trade)
                self._update_position(token_id, order.side, order.size)

                # Update order
                order.filled = order.size
                order.status = OrderStatus.MATCHED
                filled_count += 1

                logger.debug(f"[SIM] Filled: {order.side.value} {order.size} @ {order.price}")

        return filled_count

    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID."""
        return self.orders.get(order_id)

    def get_open_orders(self, token_id: Optional[str] = None) -> List[Order]:
        """Get all open orders."""
        orders = [o for o in self.orders.values() if o.is_live]

        if token_id:
            orders = [o for o in orders if o.token_id == token_id]

        return orders

    def get_trades(self, token_id: Optional[str] = None) -> List[Trade]:
        """Get all trades."""
        trades = self.trades

        if token_id:
            trades = [t for t in trades if t.token_id == token_id]

        return trades

    def get_position(self, token_id: str) -> Decimal:
        """Get net position for a token (cached)."""
        return self._positions.get(token_id, Decimal("0"))

    def reset(self):
        """Reset all orders and trades."""
        self.orders.clear()
        self.trades.clear()
        self._positions.clear()
        logger.debug("[SIM] Reset")


# Global simulator instance
_simulator: Optional[OrderSimulator] = None


def get_simulator() -> OrderSimulator:
    """Get or create the global simulator instance."""
    global _simulator
    if _simulator is None:
        _simulator = OrderSimulator()
    return _simulator


def reset_simulator():
    """Reset the global simulator."""
    get_simulator().reset()
