# Task: Polymarket Trading Bot - Phase 5: Order Management (Read Operations)

## Context

Phase 5 adds order and trade visibility. Before placing orders (Phase 6), the bot needs to:
1. See existing open orders
2. Track order status changes
3. See trade history (fills)

This is **read-only** - no order placement yet.

---

## What We're Adding

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PHASE 5 COMPONENTS                                  │
└─────────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
  │  Order Models   │     │   orders.py     │     │  User WebSocket │
  │                 │     │                 │     │   (optional)    │
  │  • Order        │     │  • get_orders() │     │                 │
  │  • Trade        │     │  • get_order()  │     │  • Order fills  │
  │  • OrderStatus  │     │  • get_trades() │     │  • Status       │
  │                 │     │                 │     │    updates      │
  └─────────────────┘     └─────────────────┘     └─────────────────┘
```

---

## Implementation

### 1. Add to src/models.py

```python
# Add these to the existing models.py file

from enum import Enum
from dataclasses import dataclass
from typing import Optional
from decimal import Decimal


class OrderStatus(Enum):
    """Order status values from Polymarket API."""
    LIVE = "LIVE"           # Order is active on the book
    MATCHED = "MATCHED"     # Order fully filled
    CANCELLED = "CANCELLED" # Order was cancelled
    EXPIRED = "EXPIRED"     # GTD order expired


class OrderSide(Enum):
    """Order side."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """Order time-in-force types."""
    GTC = "GTC"  # Good Till Cancelled
    GTD = "GTD"  # Good Till Date
    FOK = "FOK"  # Fill or Kill
    FAK = "FAK"  # Fill and Kill (partial fills OK, rest cancelled)


@dataclass
class Order:
    """
    Represents an order on Polymarket.
    
    Matches the structure returned by the CLOB API.
    """
    id: str
    token_id: str
    side: OrderSide
    price: Decimal
    original_size: Decimal
    size_matched: Decimal
    status: OrderStatus
    created_at: str
    
    # Optional fields
    expiration: Optional[str] = None
    order_type: OrderType = OrderType.GTC
    market_id: Optional[str] = None
    
    @property
    def remaining_size(self) -> Decimal:
        """Size remaining to be filled."""
        return self.original_size - self.size_matched
    
    @property
    def is_live(self) -> bool:
        """Check if order is still active."""
        return self.status == OrderStatus.LIVE
    
    @property
    def is_filled(self) -> bool:
        """Check if order is fully filled."""
        return self.status == OrderStatus.MATCHED
    
    @property
    def fill_percent(self) -> float:
        """Percentage of order filled."""
        if self.original_size == 0:
            return 0.0
        return float(self.size_matched / self.original_size) * 100


@dataclass
class Trade:
    """
    Represents a trade (fill) on Polymarket.
    """
    id: str
    order_id: str
    token_id: str
    side: OrderSide
    price: Decimal
    size: Decimal
    timestamp: str
    
    # Optional
    fee: Decimal = Decimal("0")
    market_id: Optional[str] = None
    
    @property
    def value(self) -> Decimal:
        """Total value of the trade."""
        return self.price * self.size
```

### 2. Create src/orders.py

```python
"""
Order management - read operations.

Functions for retrieving orders and trades from Polymarket.
"""

from typing import List, Optional, Dict, Any
from decimal import Decimal

from src.client import get_auth_client
from src.models import Order, Trade, OrderStatus, OrderSide, OrderType
from src.utils import setup_logging

logger = setup_logging()


def _parse_order(data: Dict[str, Any]) -> Order:
    """Parse order data from API response."""
    return Order(
        id=data.get('id', ''),
        token_id=data.get('asset_id', ''),
        side=OrderSide(data.get('side', 'BUY')),
        price=Decimal(str(data.get('price', 0))),
        original_size=Decimal(str(data.get('original_size', 0))),
        size_matched=Decimal(str(data.get('size_matched', 0))),
        status=OrderStatus(data.get('status', 'LIVE')),
        created_at=data.get('created_at', ''),
        expiration=data.get('expiration'),
        order_type=OrderType(data.get('type', 'GTC')),
        market_id=data.get('market', data.get('condition_id')),
    )


def _parse_trade(data: Dict[str, Any]) -> Trade:
    """Parse trade data from API response."""
    return Trade(
        id=data.get('id', ''),
        order_id=data.get('order_id', ''),
        token_id=data.get('asset_id', ''),
        side=OrderSide(data.get('side', 'BUY')),
        price=Decimal(str(data.get('price', 0))),
        size=Decimal(str(data.get('size', 0))),
        timestamp=data.get('created_at', data.get('timestamp', '')),
        fee=Decimal(str(data.get('fee', 0))),
        market_id=data.get('market', data.get('condition_id')),
    )


def get_orders(
    token_id: Optional[str] = None,
    market_id: Optional[str] = None,
    status: Optional[OrderStatus] = None
) -> List[Order]:
    """
    Get orders for the authenticated user.
    
    Args:
        token_id: Filter by specific token (optional)
        market_id: Filter by market/condition ID (optional)
        status: Filter by order status (optional)
    
    Returns:
        List of Order objects
    """
    client = get_auth_client()
    
    try:
        # Build params
        params = {}
        if token_id:
            params['asset_id'] = token_id
        if market_id:
            params['market'] = market_id
        
        # Get orders from API
        response = client.get_orders(**params) if params else client.get_orders()
        
        if not response:
            return []
        
        # Parse orders
        orders = [_parse_order(o) for o in response]
        
        # Filter by status if specified
        if status:
            orders = [o for o in orders if o.status == status]
        
        logger.debug(f"Retrieved {len(orders)} orders")
        return orders
        
    except Exception as e:
        logger.error(f"Error getting orders: {e}")
        return []


def get_open_orders(token_id: Optional[str] = None) -> List[Order]:
    """
    Get only open (LIVE) orders.
    
    Convenience function for the common case of checking active orders.
    
    Args:
        token_id: Filter by specific token (optional)
    
    Returns:
        List of live Order objects
    """
    return get_orders(token_id=token_id, status=OrderStatus.LIVE)


def get_order(order_id: str) -> Optional[Order]:
    """
    Get a specific order by ID.
    
    Args:
        order_id: The order ID
    
    Returns:
        Order object or None if not found
    """
    client = get_auth_client()
    
    try:
        response = client.get_order(order_id)
        
        if not response:
            return None
        
        return _parse_order(response)
        
    except Exception as e:
        logger.error(f"Error getting order {order_id}: {e}")
        return None


def get_trades(
    token_id: Optional[str] = None,
    market_id: Optional[str] = None,
    limit: int = 100
) -> List[Trade]:
    """
    Get trade history (fills) for the authenticated user.
    
    Args:
        token_id: Filter by specific token (optional)
        market_id: Filter by market/condition ID (optional)
        limit: Maximum number of trades to return
    
    Returns:
        List of Trade objects, most recent first
    """
    client = get_auth_client()
    
    try:
        # Build params
        params = {'limit': limit}
        if token_id:
            params['asset_id'] = token_id
        if market_id:
            params['market'] = market_id
        
        # Get trades from API
        response = client.get_trades(**params)
        
        if not response:
            return []
        
        # Parse trades
        trades = [_parse_trade(t) for t in response]
        
        logger.debug(f"Retrieved {len(trades)} trades")
        return trades
        
    except Exception as e:
        logger.error(f"Error getting trades: {e}")
        return []


def get_order_summary() -> Dict[str, Any]:
    """
    Get a summary of current order state.
    
    Useful for quick status checks.
    
    Returns:
        Dict with order counts and stats
    """
    orders = get_orders()
    
    live = [o for o in orders if o.status == OrderStatus.LIVE]
    matched = [o for o in orders if o.status == OrderStatus.MATCHED]
    cancelled = [o for o in orders if o.status == OrderStatus.CANCELLED]
    
    # Calculate total values
    live_buy_value = sum(o.remaining_size * o.price for o in live if o.side == OrderSide.BUY)
    live_sell_value = sum(o.remaining_size * o.price for o in live if o.side == OrderSide.SELL)
    
    return {
        'total_orders': len(orders),
        'live_orders': len(live),
        'matched_orders': len(matched),
        'cancelled_orders': len(cancelled),
        'live_buy_value': float(live_buy_value),
        'live_sell_value': float(live_sell_value),
        'tokens_with_orders': len(set(o.token_id for o in live)),
    }
```

### 3. Create tests/test_phase5.py

```python
"""
Phase 5 Verification Tests

Run with: pytest tests/test_phase5.py -v

Note: Tests that require authentication will skip if credentials not configured.
"""

import pytest
from decimal import Decimal


class TestOrderModels:
    """Test order-related models."""
    
    def test_order_status_enum(self):
        """Test OrderStatus enum."""
        from src.models import OrderStatus
        
        assert OrderStatus.LIVE.value == "LIVE"
        assert OrderStatus.MATCHED.value == "MATCHED"
        assert OrderStatus.CANCELLED.value == "CANCELLED"
        assert OrderStatus.EXPIRED.value == "EXPIRED"
        
        print("✓ OrderStatus enum defined")
    
    def test_order_side_enum(self):
        """Test OrderSide enum."""
        from src.models import OrderSide
        
        assert OrderSide.BUY.value == "BUY"
        assert OrderSide.SELL.value == "SELL"
        
        print("✓ OrderSide enum defined")
    
    def test_order_type_enum(self):
        """Test OrderType enum."""
        from src.models import OrderType
        
        assert OrderType.GTC.value == "GTC"
        assert OrderType.GTD.value == "GTD"
        assert OrderType.FOK.value == "FOK"
        assert OrderType.FAK.value == "FAK"
        
        print("✓ OrderType enum defined")
    
    def test_order_dataclass(self):
        """Test Order dataclass."""
        from src.models import Order, OrderStatus, OrderSide
        
        order = Order(
            id="order123",
            token_id="token456",
            side=OrderSide.BUY,
            price=Decimal("0.55"),
            original_size=Decimal("100"),
            size_matched=Decimal("40"),
            status=OrderStatus.LIVE,
            created_at="2024-01-01T00:00:00Z"
        )
        
        assert order.id == "order123"
        assert order.remaining_size == Decimal("60")
        assert order.is_live == True
        assert order.is_filled == False
        assert order.fill_percent == 40.0
        
        print("✓ Order dataclass works")
    
    def test_trade_dataclass(self):
        """Test Trade dataclass."""
        from src.models import Trade, OrderSide
        
        trade = Trade(
            id="trade789",
            order_id="order123",
            token_id="token456",
            side=OrderSide.BUY,
            price=Decimal("0.55"),
            size=Decimal("50"),
            timestamp="2024-01-01T00:00:00Z"
        )
        
        assert trade.id == "trade789"
        assert trade.value == Decimal("27.50")
        
        print("✓ Trade dataclass works")


class TestOrdersModule:
    """Test orders.py functions."""
    
    def test_imports(self):
        """Test orders module imports."""
        from src.orders import (
            get_orders,
            get_open_orders,
            get_order,
            get_trades,
            get_order_summary,
        )
        
        print("✓ Orders module imports work")
    
    def test_get_orders_requires_auth(self):
        """Test that get_orders requires authentication."""
        from src.orders import get_orders
        from src.config import has_credentials
        
        if not has_credentials():
            # Should return empty list, not crash
            orders = get_orders()
            assert orders == [] or isinstance(orders, list)
            print("✓ get_orders handles missing auth gracefully")
        else:
            orders = get_orders()
            assert isinstance(orders, list)
            print(f"✓ get_orders returned {len(orders)} orders")
    
    def test_get_open_orders(self):
        """Test get_open_orders function."""
        from src.orders import get_open_orders
        from src.config import has_credentials
        
        if not has_credentials():
            pytest.skip("Credentials not configured")
        
        orders = get_open_orders()
        
        assert isinstance(orders, list)
        # All returned orders should be LIVE
        from src.models import OrderStatus
        for order in orders:
            assert order.status == OrderStatus.LIVE
        
        print(f"✓ get_open_orders returned {len(orders)} live orders")
    
    def test_get_trades(self):
        """Test get_trades function."""
        from src.orders import get_trades
        from src.config import has_credentials
        
        if not has_credentials():
            pytest.skip("Credentials not configured")
        
        trades = get_trades(limit=10)
        
        assert isinstance(trades, list)
        print(f"✓ get_trades returned {len(trades)} trades")
    
    def test_get_order_summary(self):
        """Test get_order_summary function."""
        from src.orders import get_order_summary
        from src.config import has_credentials
        
        if not has_credentials():
            pytest.skip("Credentials not configured")
        
        summary = get_order_summary()
        
        assert 'total_orders' in summary
        assert 'live_orders' in summary
        assert 'live_buy_value' in summary
        assert 'live_sell_value' in summary
        
        print(f"✓ Order summary: {summary}")


class TestIntegration:
    """Integration tests."""
    
    def test_order_workflow_readonly(self):
        """Test reading orders and trades together."""
        from src.config import has_credentials
        from src.orders import get_open_orders, get_trades, get_order_summary
        
        if not has_credentials():
            pytest.skip("Credentials not configured")
        
        # Get current state
        summary = get_order_summary()
        open_orders = get_open_orders()
        recent_trades = get_trades(limit=5)
        
        print(f"  Summary: {summary['live_orders']} open orders")
        print(f"  Open orders: {len(open_orders)}")
        print(f"  Recent trades: {len(recent_trades)}")
        
        # Verify consistency
        assert summary['live_orders'] == len(open_orders)
        
        print("✓ Order workflow works")
    
    def test_filter_by_token(self):
        """Test filtering orders by token."""
        from src.config import has_credentials
        from src.orders import get_orders, get_open_orders
        from src.markets import fetch_active_markets
        
        if not has_credentials():
            pytest.skip("Credentials not configured")
        
        # Get a token to filter by
        markets = fetch_active_markets(limit=5)
        if not markets or not markets[0].token_ids:
            pytest.skip("No markets found")
        
        token_id = markets[0].token_ids[0]
        
        # Filter by token
        orders = get_orders(token_id=token_id)
        open_orders = get_open_orders(token_id=token_id)
        
        # All returned orders should be for this token
        for order in orders:
            assert order.token_id == token_id
        
        print(f"✓ Token filter works ({len(orders)} orders for token)")
```

---

## File Structure After Phase 5

```
polymarket-bot/
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── client.py
│   ├── auth.py
│   ├── utils.py
│   ├── models.py          # Updated with Order, Trade, enums
│   ├── markets.py
│   ├── pricing.py
│   ├── orders.py          # NEW
│   └── feed/
│       └── ...
│
├── tests/
│   ├── test_phase1.py
│   ├── test_phase2.py
│   ├── test_phase3.py
│   ├── test_phase3_5.py
│   ├── test_phase4.py
│   └── test_phase5.py     # NEW
```

---

## Verification

```bash
pytest tests/test_phase5.py -v
```

**Without open orders** (all pass, some show 0 orders):
```
test_order_status_enum PASSED
test_order_side_enum PASSED
test_order_type_enum PASSED
test_order_dataclass PASSED
test_trade_dataclass PASSED
test_imports PASSED
test_get_orders_requires_auth PASSED
test_get_open_orders PASSED
test_get_trades PASSED
test_get_order_summary PASSED
test_order_workflow_readonly PASSED
test_filter_by_token PASSED
```

---

## Success Criteria

Phase 5 is complete when:

1. ✅ `OrderStatus`, `OrderSide`, `OrderType` enums work
2. ✅ `Order` and `Trade` dataclasses work
3. ✅ `get_orders()` returns list of orders
4. ✅ `get_open_orders()` filters to LIVE only
5. ✅ `get_trades()` returns trade history
6. ✅ All tests pass

---

## What's NOT in Phase 5

- Order placement (Phase 6)
- Order cancellation (Phase 6)
- User WebSocket channel (deferred - REST polling sufficient for now)

Keeping it simple - we'll add real-time order updates if needed later.

---

## Next: Phase 6

Phase 6 adds order **write** operations:
- `place_order()` - Create and submit orders
- `cancel_order()` - Cancel single order
- `cancel_all_orders()` - Cancel all open orders
- Safety checks (max size, price validation)

⚠️ **Phase 6 will use real money** - we'll start with tiny $1-5 orders.
