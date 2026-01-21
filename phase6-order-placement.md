# Phase 6: Order Placement + Code Simplification

## Overview

Phase 6 does two things:
1. **Simplify** - Remove over-engineered code from Phase 5
2. **Add** - Order placement with critical validations

---

## Part 1: Simplification (Remove/Modify)

### Check what to remove from src/simulator.py

If your current simulator has these, **remove them**:
- `get_pnl()` method
- `cost_basis` tracking
- `realized_pnl` / `unrealized_pnl` calculations

**Keep only:**
- `create_order()`
- `cancel_order()` 
- `cancel_all()`
- `check_fills()`
- `get_order()`
- `get_open_orders()`
- `get_trades()`
- `get_position()` (simple net position only)
- `reset()`

### Check src/models.py Order fields

If you used `original_size` and `size_matched`, rename to `size` and `filled`:

```python
# Change from:
original_size: Decimal
size_matched: Decimal

# To:
size: Decimal
filled: Decimal

# And property from:
@property
def remaining_size(self) -> Decimal:
    return self.original_size - self.size_matched

# To:
@property
def remaining(self) -> Decimal:
    return self.size - self.filled
```

### Remove from src/orders.py (if present)

Remove these functions if they exist (we'll add simpler versions or move to trading.py):
- `check_simulated_fills()` - move call to simulator directly
- `get_simulated_position()` - just use `get_position()`
- `get_simulated_pnl()` - defer P&L to later

---

## Part 2: Add Configuration

### Update src/config.py

Add these lines:

```python
# === Trading Limits ===
MAX_POSITION_PER_MARKET = Decimal(os.getenv("MAX_POSITION_PER_MARKET", "100"))
MAX_ORDER_SIZE = Decimal(os.getenv("MAX_ORDER_SIZE", "50"))
MIN_ORDER_SIZE = Decimal(os.getenv("MIN_ORDER_SIZE", "5"))
```

Add import at top:
```python
from decimal import Decimal
```

---

## Part 3: Create src/trading.py

New file for order placement:

```python
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
from src.orders import get_position, get_open_orders
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
```

---

## Part 4: Simplify src/orders.py

Keep only query functions:

```python
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
```

---

## Part 5: Tests

### Create tests/test_phase6.py

```python
"""
Phase 6 Tests - Order placement with validation.

Run: pytest tests/test_phase6.py -v
"""

import pytest
from decimal import Decimal


class TestValidation:
    """Test order validation."""
    
    def test_validate_price_valid(self):
        from src.trading import validate_price
        
        assert validate_price(Decimal("0.50"), "t") == Decimal("0.50")
        assert validate_price(Decimal("0.01"), "t") == Decimal("0.01")
        assert validate_price(Decimal("0.99"), "t") == Decimal("0.99")
        print("✓ Valid prices accepted")
    
    def test_validate_price_rounds(self):
        from src.trading import validate_price
        
        # Rounds down to tick
        assert validate_price(Decimal("0.555"), "t") == Decimal("0.55")
        assert validate_price(Decimal("0.509"), "t") == Decimal("0.50")
        print("✓ Prices rounded to tick")
    
    def test_validate_price_invalid(self):
        from src.trading import validate_price, OrderError
        
        with pytest.raises(OrderError):
            validate_price(Decimal("0"), "t")
        with pytest.raises(OrderError):
            validate_price(Decimal("1"), "t")
        with pytest.raises(OrderError):
            validate_price(Decimal("1.5"), "t")
        with pytest.raises(OrderError):
            validate_price(Decimal("-0.5"), "t")
        print("✓ Invalid prices rejected")
    
    def test_validate_size(self):
        from src.trading import validate_size, OrderError
        from src.config import MIN_ORDER_SIZE, MAX_ORDER_SIZE
        
        # Valid
        validate_size(Decimal("10"))
        validate_size(MIN_ORDER_SIZE)
        validate_size(MAX_ORDER_SIZE)
        
        # Too small
        with pytest.raises(OrderError):
            validate_size(Decimal("1"))
        
        # Too large
        with pytest.raises(OrderError):
            validate_size(MAX_ORDER_SIZE + 1)
        
        print("✓ Size validation works")
    
    def test_position_limit(self):
        from src.trading import check_position_limit, OrderError
        from src.models import OrderSide
        from src.config import MAX_POSITION_PER_MARKET
        from src.simulator import reset_simulator
        
        reset_simulator()
        
        # Within limit
        check_position_limit("t", OrderSide.BUY, Decimal("50"))
        
        # Exceeds limit
        with pytest.raises(OrderError):
            check_position_limit("t", OrderSide.BUY, MAX_POSITION_PER_MARKET + 1)
        
        print("✓ Position limit works")


class TestPlaceOrder:
    """Test order placement."""
    
    def test_place_order_success(self):
        from src.config import DRY_RUN
        from src.trading import place_order
        from src.models import OrderSide
        from src.simulator import reset_simulator
        
        if not DRY_RUN:
            pytest.skip("Requires DRY_RUN=true")
        
        reset_simulator()
        
        order = place_order("token1", OrderSide.BUY, Decimal("0.50"), Decimal("10"))
        
        assert order.is_simulated
        assert order.is_live
        assert order.side == OrderSide.BUY
        assert order.price == Decimal("0.50")
        assert order.size == Decimal("10")
        
        print("✓ Order placed successfully")
    
    def test_place_order_rejects_bad_price(self):
        from src.trading import place_order, OrderError
        from src.models import OrderSide
        from src.simulator import reset_simulator
        
        reset_simulator()
        
        with pytest.raises(OrderError):
            place_order("t", OrderSide.BUY, Decimal("1.5"), Decimal("10"))
        
        print("✓ Bad price rejected")
    
    def test_place_order_rejects_small_size(self):
        from src.trading import place_order, OrderError
        from src.models import OrderSide
        from src.simulator import reset_simulator
        
        reset_simulator()
        
        with pytest.raises(OrderError):
            place_order("t", OrderSide.BUY, Decimal("0.50"), Decimal("1"))
        
        print("✓ Small size rejected")


class TestCancelOrder:
    """Test order cancellation."""
    
    def test_cancel_order(self):
        from src.config import DRY_RUN
        from src.trading import place_order, cancel_order
        from src.models import OrderSide, OrderStatus
        from src.simulator import reset_simulator
        
        if not DRY_RUN:
            pytest.skip("Requires DRY_RUN=true")
        
        reset_simulator()
        
        order = place_order("t", OrderSide.BUY, Decimal("0.50"), Decimal("10"))
        result = cancel_order(order.id)
        
        assert result == True
        assert order.status == OrderStatus.CANCELLED
        
        print("✓ Cancel order works")
    
    def test_cancel_all_orders(self):
        from src.config import DRY_RUN
        from src.trading import place_order, cancel_all_orders
        from src.orders import get_open_orders
        from src.models import OrderSide
        from src.simulator import reset_simulator
        
        if not DRY_RUN:
            pytest.skip("Requires DRY_RUN=true")
        
        reset_simulator()
        
        place_order("t1", OrderSide.BUY, Decimal("0.50"), Decimal("10"))
        place_order("t1", OrderSide.SELL, Decimal("0.55"), Decimal("10"))
        place_order("t2", OrderSide.BUY, Decimal("0.30"), Decimal("10"))
        
        assert len(get_open_orders()) == 3
        
        # Cancel only t1
        cancelled = cancel_all_orders("t1")
        assert cancelled == 2
        assert len(get_open_orders()) == 1
        
        # Cancel all
        cancel_all_orders()
        assert len(get_open_orders()) == 0
        
        print("✓ Cancel all works")


class TestIntegration:
    """Full workflow test."""
    
    def test_place_fill_cancel_workflow(self):
        from src.config import DRY_RUN
        from src.trading import place_order, cancel_all_orders
        from src.orders import get_open_orders, get_position
        from src.models import OrderSide
        from src.simulator import get_simulator, reset_simulator
        
        if not DRY_RUN:
            pytest.skip("Requires DRY_RUN=true")
        
        reset_simulator()
        sim = get_simulator()
        
        # Place buy
        buy = place_order("t1", OrderSide.BUY, Decimal("0.50"), Decimal("20"))
        assert get_position("t1") == Decimal("0")
        
        # Fill it
        sim.check_fills("t1", Decimal("0.45"), Decimal("0.50"))
        assert get_position("t1") == Decimal("20")
        assert not buy.is_live
        
        # Place sell
        sell = place_order("t1", OrderSide.SELL, Decimal("0.55"), Decimal("10"))
        sim.check_fills("t1", Decimal("0.55"), Decimal("0.60"))
        assert get_position("t1") == Decimal("10")
        
        # Cleanup
        cancel_all_orders()
        
        print("✓ Full workflow works")
    
    def test_with_real_market(self):
        from src.config import DRY_RUN
        from src.trading import place_order, cancel_all_orders
        from src.models import OrderSide
        from src.markets import fetch_active_markets
        from src.pricing import get_order_book
        from src.simulator import reset_simulator
        
        if not DRY_RUN:
            pytest.skip("Requires DRY_RUN=true")
        
        reset_simulator()
        
        # Get real market
        markets = fetch_active_markets(limit=5)
        token_id = None
        for m in markets:
            if m.token_ids:
                token_id = m.token_ids[0]
                break
        
        if not token_id:
            pytest.skip("No markets")
        
        book = get_order_book(token_id)
        if not book or not book.best_bid:
            pytest.skip("No book")
        
        print(f"  Token: {token_id[:20]}...")
        print(f"  Bid: {book.best_bid}, Ask: {book.best_ask}")
        
        order = place_order(
            token_id, 
            OrderSide.BUY, 
            Decimal(str(book.best_bid)), 
            Decimal("10")
        )
        
        assert order.is_live
        cancel_all_orders()
        
        print("✓ Real market test works")
```

---

## Summary of Changes

| Action | File | What |
|--------|------|------|
| MODIFY | `src/config.py` | Add trading limits |
| CREATE | `src/trading.py` | Order placement, cancellation |
| SIMPLIFY | `src/orders.py` | Keep only queries |
| SIMPLIFY | `src/simulator.py` | Remove complex P&L if present |
| MODIFY | `src/models.py` | Use `size`/`filled` field names |
| CREATE | `tests/test_phase6.py` | 12 tests |

---

## Verification

```bash
pytest tests/test_phase6.py -v
```

All 12 tests should pass with `DRY_RUN=true`.

---

## Next: Phase 7

Simple market maker loop!
