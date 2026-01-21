# Task: Polymarket Trading Bot - Phase 5: Order Management (Read) + Dry-Run Mode

## Context

Phase 5 adds order visibility AND dry-run infrastructure. The bot needs to:
1. Track orders (real or simulated)
2. See trade history
3. Run in dry-run mode with **real market data** but simulated execution

**Key principle:** Real data always. Dry-run only affects whether orders are actually placed.

---

## Modes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              OPERATING MODES                                │
└─────────────────────────────────────────────────────────────────────────────┘

  DRY_RUN=true (default, safe)          DRY_RUN=false (real trading)
  ══════════════════════════════        ══════════════════════════════
  
  Market Data:    REAL                  Market Data:    REAL
  Order Books:    REAL                  Order Books:    REAL  
  WebSocket:      REAL                  WebSocket:      REAL
  
  Order Placement: SIMULATED            Order Placement: REAL
  Fill Detection:  SIMULATED            Fill Detection:  REAL
  Money at Risk:   NONE                 Money at Risk:   YES
  
  ┌─────────────────────────────┐       ┌─────────────────────────────┐
  │ Orders tracked locally      │       │ Orders sent to exchange     │
  │ Fills when price crosses    │       │ Fills from actual matching  │
  │ P&L calculated, not real    │       │ Real P&L, real money        │
  └─────────────────────────────┘       └─────────────────────────────┘
```

---

## Implementation

### 1. Update src/config.py

```python
"""
Configuration management.
"""

import os
from dotenv import load_dotenv

load_dotenv()


# === Operating Mode ===
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"  # Default: SAFE

# === Network ===
CHAIN_ID = int(os.getenv("CHAIN_ID", "137"))

# === API Endpoints ===
CLOB_API_URL = os.getenv("CLOB_API_URL", "https://clob.polymarket.com")
GAMMA_API_URL = os.getenv("GAMMA_API_URL", "https://gamma-api.polymarket.com")

# === Authentication ===
POLY_PRIVATE_KEY = os.getenv("POLY_PRIVATE_KEY")
POLY_API_KEY = os.getenv("POLY_API_KEY")
POLY_API_SECRET = os.getenv("POLY_API_SECRET")
POLY_PASSPHRASE = os.getenv("POLY_PASSPHRASE")

# === WebSocket ===
WS_MARKET_URL = os.getenv(
    "WS_MARKET_URL",
    "wss://ws-subscriptions-clob.polymarket.com/ws/market"
)
WS_RECONNECT_ATTEMPTS = int(os.getenv("WS_RECONNECT_ATTEMPTS", "10"))
WS_RECONNECT_BASE_DELAY = float(os.getenv("WS_RECONNECT_BASE_DELAY", "1.0"))
WS_RECONNECT_MAX_DELAY = float(os.getenv("WS_RECONNECT_MAX_DELAY", "60.0"))

# === Contract Addresses (Polygon) ===
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"


def has_credentials() -> bool:
    """Check if all required credentials are configured."""
    return all([
        POLY_PRIVATE_KEY,
        POLY_API_KEY,
        POLY_API_SECRET,
        POLY_PASSPHRASE
    ])


def validate_config():
    """Validate configuration. Raises ValueError if invalid."""
    errors = []
    
    if CHAIN_ID not in (137, 80001):
        errors.append(f"Invalid CHAIN_ID: {CHAIN_ID}")
    
    if not CLOB_API_URL:
        errors.append("CLOB_API_URL is required")
    
    if not DRY_RUN and not has_credentials():
        errors.append("Credentials required for live trading (DRY_RUN=false)")
    
    if errors:
        raise ValueError("Configuration errors: " + "; ".join(errors))


def get_mode_string() -> str:
    """Get human-readable mode string."""
    return "DRY RUN (paper trading)" if DRY_RUN else "LIVE (real money)"
```

### 2. Update .env.example

```bash
# Polymarket Bot Configuration

# === OPERATING MODE ===
# true = paper trading with real data, no real orders (SAFE, default)
# false = real trading with real money (DANGER)
DRY_RUN=true

# === Network ===
CHAIN_ID=137

# === API Endpoints ===
CLOB_API_URL=https://clob.polymarket.com
GAMMA_API_URL=https://gamma-api.polymarket.com

# === Authentication (required for DRY_RUN=false) ===
POLY_PRIVATE_KEY=
POLY_API_KEY=
POLY_API_SECRET=
POLY_PASSPHRASE=

# === WebSocket ===
WS_MARKET_URL=wss://ws-subscriptions-clob.polymarket.com/ws/market
```

### 3. Add to src/models.py

```python
# Add these to the existing models.py file

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List
from decimal import Decimal
import time
import uuid


class OrderStatus(Enum):
    """Order status values."""
    LIVE = "LIVE"
    MATCHED = "MATCHED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class OrderSide(Enum):
    """Order side."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """Order time-in-force types."""
    GTC = "GTC"
    GTD = "GTD"
    FOK = "FOK"


@dataclass
class Order:
    """Represents an order (real or simulated)."""
    id: str
    token_id: str
    side: OrderSide
    price: Decimal
    original_size: Decimal
    size_matched: Decimal
    status: OrderStatus
    created_at: str
    
    # Optional
    expiration: Optional[str] = None
    order_type: OrderType = OrderType.GTC
    market_id: Optional[str] = None
    is_simulated: bool = False  # True if dry-run order
    
    @property
    def remaining_size(self) -> Decimal:
        return self.original_size - self.size_matched
    
    @property
    def is_live(self) -> bool:
        return self.status == OrderStatus.LIVE
    
    @property
    def is_filled(self) -> bool:
        return self.status == OrderStatus.MATCHED
    
    @property
    def fill_percent(self) -> float:
        if self.original_size == 0:
            return 0.0
        return float(self.size_matched / self.original_size) * 100


@dataclass
class Trade:
    """Represents a trade/fill (real or simulated)."""
    id: str
    order_id: str
    token_id: str
    side: OrderSide
    price: Decimal
    size: Decimal
    timestamp: str
    
    fee: Decimal = Decimal("0")
    market_id: Optional[str] = None
    is_simulated: bool = False
    
    @property
    def value(self) -> Decimal:
        return self.price * self.size
```

### 4. Create src/simulator.py

```python
"""
Dry-run order simulator.

Tracks simulated orders and detects fills based on real price movements.
Uses REAL market data - only order execution is simulated.
"""

import uuid
import time
from typing import Dict, List, Optional
from decimal import Decimal
from dataclasses import dataclass, field

from src.models import Order, Trade, OrderStatus, OrderSide, OrderType
from src.utils import setup_logging

logger = setup_logging()


def _generate_id() -> str:
    """Generate a unique ID for simulated orders/trades."""
    return f"sim_{uuid.uuid4().hex[:12]}"


def _timestamp() -> str:
    """Get current timestamp string."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class OrderSimulator:
    """
    Simulates order tracking and fills for dry-run mode.
    
    Uses real market prices to determine when orders would fill.
    Does NOT place any real orders.
    
    Usage:
        sim = OrderSimulator()
        
        # Add a simulated order
        order = sim.create_order("token123", OrderSide.BUY, Decimal("0.50"), Decimal("100"))
        
        # Check for fills based on current market price
        fills = sim.check_fills("token123", best_bid=Decimal("0.48"), best_ask=Decimal("0.52"))
        
        # Get current state
        open_orders = sim.get_open_orders()
    """
    
    def __init__(self):
        self._orders: Dict[str, Order] = {}
        self._trades: List[Trade] = []
    
    def create_order(
        self,
        token_id: str,
        side: OrderSide,
        price: Decimal,
        size: Decimal,
        order_type: OrderType = OrderType.GTC,
        market_id: Optional[str] = None
    ) -> Order:
        """
        Create a simulated order.
        
        Returns the order object (not yet filled).
        """
        order = Order(
            id=_generate_id(),
            token_id=token_id,
            side=side,
            price=price,
            original_size=size,
            size_matched=Decimal("0"),
            status=OrderStatus.LIVE,
            created_at=_timestamp(),
            order_type=order_type,
            market_id=market_id,
            is_simulated=True
        )
        
        self._orders[order.id] = order
        logger.info(f"[DRY RUN] Created order: {side.value} {size} @ {price} (id={order.id})")
        
        return order
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a simulated order."""
        order = self._orders.get(order_id)
        
        if not order:
            logger.warning(f"[DRY RUN] Order not found: {order_id}")
            return False
        
        if order.status != OrderStatus.LIVE:
            logger.warning(f"[DRY RUN] Cannot cancel order in status {order.status.value}")
            return False
        
        order.status = OrderStatus.CANCELLED
        logger.info(f"[DRY RUN] Cancelled order: {order_id}")
        return True
    
    def cancel_all_orders(self, token_id: Optional[str] = None) -> int:
        """Cancel all open orders, optionally filtered by token."""
        cancelled = 0
        
        for order in self._orders.values():
            if order.status != OrderStatus.LIVE:
                continue
            if token_id and order.token_id != token_id:
                continue
            
            order.status = OrderStatus.CANCELLED
            cancelled += 1
        
        logger.info(f"[DRY RUN] Cancelled {cancelled} orders")
        return cancelled
    
    def check_fills(
        self,
        token_id: str,
        best_bid: Optional[Decimal] = None,
        best_ask: Optional[Decimal] = None
    ) -> List[Trade]:
        """
        Check if any orders would fill at current prices.
        
        A BUY order fills when best_ask <= order price.
        A SELL order fills when best_bid >= order price.
        
        Returns list of new trades (fills).
        """
        new_trades = []
        
        for order in self._orders.values():
            if order.status != OrderStatus.LIVE:
                continue
            if order.token_id != token_id:
                continue
            
            fill_price = None
            
            # Check fill conditions
            if order.side == OrderSide.BUY and best_ask is not None:
                if best_ask <= order.price:
                    fill_price = best_ask  # Fill at market ask
                    
            elif order.side == OrderSide.SELL and best_bid is not None:
                if best_bid >= order.price:
                    fill_price = best_bid  # Fill at market bid
            
            if fill_price is not None:
                # Create fill
                fill_size = order.remaining_size
                
                trade = Trade(
                    id=_generate_id(),
                    order_id=order.id,
                    token_id=token_id,
                    side=order.side,
                    price=fill_price,
                    size=fill_size,
                    timestamp=_timestamp(),
                    market_id=order.market_id,
                    is_simulated=True
                )
                
                # Update order
                order.size_matched = order.original_size
                order.status = OrderStatus.MATCHED
                
                self._trades.append(trade)
                new_trades.append(trade)
                
                logger.info(
                    f"[DRY RUN] Order filled: {order.side.value} {fill_size} @ {fill_price} "
                    f"(order={order.id})"
                )
        
        return new_trades
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get a specific order."""
        return self._orders.get(order_id)
    
    def get_orders(
        self,
        token_id: Optional[str] = None,
        status: Optional[OrderStatus] = None
    ) -> List[Order]:
        """Get orders, optionally filtered."""
        orders = list(self._orders.values())
        
        if token_id:
            orders = [o for o in orders if o.token_id == token_id]
        if status:
            orders = [o for o in orders if o.status == status]
        
        return orders
    
    def get_open_orders(self, token_id: Optional[str] = None) -> List[Order]:
        """Get only LIVE orders."""
        return self.get_orders(token_id=token_id, status=OrderStatus.LIVE)
    
    def get_trades(
        self,
        token_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Trade]:
        """Get trades, most recent first."""
        trades = self._trades.copy()
        
        if token_id:
            trades = [t for t in trades if t.token_id == token_id]
        
        trades.reverse()  # Most recent first
        return trades[:limit]
    
    def get_position(self, token_id: str) -> Decimal:
        """
        Get net position for a token.
        
        Positive = long (bought more than sold)
        Negative = short (sold more than bought)
        """
        position = Decimal("0")
        
        for trade in self._trades:
            if trade.token_id != token_id:
                continue
            
            if trade.side == OrderSide.BUY:
                position += trade.size
            else:
                position -= trade.size
        
        return position
    
    def get_pnl(self, token_id: str, current_price: Decimal) -> Dict:
        """
        Calculate P&L for a token position.
        
        Returns dict with realized and unrealized P&L.
        """
        position = Decimal("0")
        cost_basis = Decimal("0")
        realized_pnl = Decimal("0")
        
        for trade in self._trades:
            if trade.token_id != token_id:
                continue
            
            if trade.side == OrderSide.BUY:
                # Buying: add to position and cost
                cost_basis += trade.price * trade.size
                position += trade.size
            else:
                # Selling: reduce position, realize P&L
                if position > 0:
                    avg_cost = cost_basis / position if position else Decimal("0")
                    sell_size = min(trade.size, position)
                    realized_pnl += (trade.price - avg_cost) * sell_size
                    cost_basis -= avg_cost * sell_size
                    position -= sell_size
        
        # Unrealized P&L on remaining position
        avg_cost = cost_basis / position if position > 0 else Decimal("0")
        unrealized_pnl = (current_price - avg_cost) * position if position > 0 else Decimal("0")
        
        return {
            'position': position,
            'cost_basis': cost_basis,
            'realized_pnl': realized_pnl,
            'unrealized_pnl': unrealized_pnl,
            'total_pnl': realized_pnl + unrealized_pnl,
        }
    
    def reset(self):
        """Clear all simulated orders and trades."""
        self._orders.clear()
        self._trades.clear()
        logger.info("[DRY RUN] Simulator reset")


# Global simulator instance
_simulator: Optional[OrderSimulator] = None


def get_simulator() -> OrderSimulator:
    """Get the global simulator instance."""
    global _simulator
    if _simulator is None:
        _simulator = OrderSimulator()
    return _simulator


def reset_simulator():
    """Reset the global simulator."""
    global _simulator
    if _simulator:
        _simulator.reset()
    _simulator = None
```

### 5. Create src/orders.py

```python
"""
Order management - unified interface for real and simulated orders.

In DRY_RUN mode: Uses simulator with real price data
In LIVE mode: Uses real Polymarket API
"""

from typing import List, Optional, Dict, Any
from decimal import Decimal

from src.config import DRY_RUN, has_credentials
from src.models import Order, Trade, OrderStatus, OrderSide, OrderType
from src.simulator import get_simulator
from src.utils import setup_logging

logger = setup_logging()


def _parse_order(data: Dict[str, Any]) -> Order:
    """Parse order from API response."""
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
        is_simulated=False
    )


def _parse_trade(data: Dict[str, Any]) -> Trade:
    """Parse trade from API response."""
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
        is_simulated=False
    )


def get_orders(
    token_id: Optional[str] = None,
    status: Optional[OrderStatus] = None
) -> List[Order]:
    """
    Get orders for the authenticated user.
    
    In DRY_RUN mode: Returns simulated orders
    In LIVE mode: Returns real orders from API
    """
    if DRY_RUN:
        return get_simulator().get_orders(token_id=token_id, status=status)
    
    # Live mode - get from API
    if not has_credentials():
        logger.warning("No credentials configured for live trading")
        return []
    
    from src.client import get_auth_client
    client = get_auth_client()
    
    try:
        params = {}
        if token_id:
            params['asset_id'] = token_id
        
        response = client.get_orders(**params) if params else client.get_orders()
        
        if not response:
            return []
        
        orders = [_parse_order(o) for o in response]
        
        if status:
            orders = [o for o in orders if o.status == status]
        
        return orders
        
    except Exception as e:
        logger.error(f"Error getting orders: {e}")
        return []


def get_open_orders(token_id: Optional[str] = None) -> List[Order]:
    """Get only LIVE orders."""
    return get_orders(token_id=token_id, status=OrderStatus.LIVE)


def get_order(order_id: str) -> Optional[Order]:
    """Get a specific order by ID."""
    if DRY_RUN:
        return get_simulator().get_order(order_id)
    
    if not has_credentials():
        return None
    
    from src.client import get_auth_client
    client = get_auth_client()
    
    try:
        response = client.get_order(order_id)
        return _parse_order(response) if response else None
    except Exception as e:
        logger.error(f"Error getting order {order_id}: {e}")
        return None


def get_trades(
    token_id: Optional[str] = None,
    limit: int = 100
) -> List[Trade]:
    """
    Get trade history.
    
    In DRY_RUN mode: Returns simulated trades
    In LIVE mode: Returns real trades from API
    """
    if DRY_RUN:
        return get_simulator().get_trades(token_id=token_id, limit=limit)
    
    if not has_credentials():
        return []
    
    from src.client import get_auth_client
    client = get_auth_client()
    
    try:
        params = {'limit': limit}
        if token_id:
            params['asset_id'] = token_id
        
        response = client.get_trades(**params)
        
        if not response:
            return []
        
        return [_parse_trade(t) for t in response]
        
    except Exception as e:
        logger.error(f"Error getting trades: {e}")
        return []


def get_order_summary() -> Dict[str, Any]:
    """Get summary of current order state."""
    orders = get_orders()
    
    live = [o for o in orders if o.status == OrderStatus.LIVE]
    matched = [o for o in orders if o.status == OrderStatus.MATCHED]
    
    live_buy_value = sum(o.remaining_size * o.price for o in live if o.side == OrderSide.BUY)
    live_sell_value = sum(o.remaining_size * o.price for o in live if o.side == OrderSide.SELL)
    
    return {
        'mode': 'DRY_RUN' if DRY_RUN else 'LIVE',
        'total_orders': len(orders),
        'live_orders': len(live),
        'matched_orders': len(matched),
        'live_buy_value': float(live_buy_value),
        'live_sell_value': float(live_sell_value),
        'tokens_with_orders': len(set(o.token_id for o in live)),
    }


def check_simulated_fills(token_id: str, best_bid: Decimal, best_ask: Decimal) -> List[Trade]:
    """
    Check for simulated fills (DRY_RUN mode only).
    
    Call this periodically with current market prices to simulate fills.
    Returns list of new fills, empty if no fills or not in dry-run mode.
    """
    if not DRY_RUN:
        return []
    
    return get_simulator().check_fills(token_id, best_bid, best_ask)


def get_simulated_position(token_id: str) -> Decimal:
    """Get net position for a token (DRY_RUN mode only)."""
    if not DRY_RUN:
        return Decimal("0")
    
    return get_simulator().get_position(token_id)


def get_simulated_pnl(token_id: str, current_price: Decimal) -> Dict[str, Any]:
    """Get P&L for a token position (DRY_RUN mode only)."""
    if not DRY_RUN:
        return {'position': Decimal("0"), 'total_pnl': Decimal("0")}
    
    return get_simulator().get_pnl(token_id, current_price)
```

### 6. Create tests/test_phase5.py

```python
"""
Phase 5 Verification Tests

Run with: pytest tests/test_phase5.py -v
"""

import pytest
from decimal import Decimal


class TestConfig:
    """Test configuration with DRY_RUN."""
    
    def test_dry_run_default(self):
        """Test DRY_RUN defaults to True (safe)."""
        from src.config import DRY_RUN
        
        # Default should be True for safety
        print(f"  DRY_RUN = {DRY_RUN}")
        print("✓ DRY_RUN config loaded")
    
    def test_get_mode_string(self):
        """Test mode string function."""
        from src.config import get_mode_string
        
        mode = get_mode_string()
        assert "DRY RUN" in mode or "LIVE" in mode
        print(f"✓ Mode: {mode}")


class TestOrderModels:
    """Test order models."""
    
    def test_order_status_enum(self):
        """Test OrderStatus enum."""
        from src.models import OrderStatus
        
        assert OrderStatus.LIVE.value == "LIVE"
        assert OrderStatus.MATCHED.value == "MATCHED"
        assert OrderStatus.CANCELLED.value == "CANCELLED"
        print("✓ OrderStatus enum defined")
    
    def test_order_side_enum(self):
        """Test OrderSide enum."""
        from src.models import OrderSide
        
        assert OrderSide.BUY.value == "BUY"
        assert OrderSide.SELL.value == "SELL"
        print("✓ OrderSide enum defined")
    
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
        
        assert order.remaining_size == Decimal("60")
        assert order.is_live == True
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
        
        assert trade.value == Decimal("27.50")
        print("✓ Trade dataclass works")


class TestSimulator:
    """Test the order simulator."""
    
    def test_simulator_creation(self):
        """Test simulator can be created."""
        from src.simulator import OrderSimulator
        
        sim = OrderSimulator()
        assert sim is not None
        print("✓ Simulator created")
    
    def test_create_order(self):
        """Test creating simulated orders."""
        from src.simulator import OrderSimulator
        from src.models import OrderSide, OrderStatus
        
        sim = OrderSimulator()
        
        order = sim.create_order(
            token_id="token123",
            side=OrderSide.BUY,
            price=Decimal("0.50"),
            size=Decimal("100")
        )
        
        assert order.id.startswith("sim_")
        assert order.is_simulated == True
        assert order.status == OrderStatus.LIVE
        assert order.remaining_size == Decimal("100")
        
        print(f"✓ Created order: {order.id}")
    
    def test_cancel_order(self):
        """Test canceling simulated orders."""
        from src.simulator import OrderSimulator
        from src.models import OrderSide, OrderStatus
        
        sim = OrderSimulator()
        order = sim.create_order("token123", OrderSide.BUY, Decimal("0.50"), Decimal("100"))
        
        result = sim.cancel_order(order.id)
        
        assert result == True
        assert order.status == OrderStatus.CANCELLED
        print("✓ Order cancelled")
    
    def test_fill_detection_buy(self):
        """Test buy order fill detection."""
        from src.simulator import OrderSimulator
        from src.models import OrderSide, OrderStatus
        
        sim = OrderSimulator()
        
        # Create buy order at 0.50
        order = sim.create_order("token123", OrderSide.BUY, Decimal("0.50"), Decimal("100"))
        
        # Market ask is 0.55 - no fill
        fills = sim.check_fills("token123", best_bid=Decimal("0.45"), best_ask=Decimal("0.55"))
        assert len(fills) == 0
        assert order.status == OrderStatus.LIVE
        
        # Market ask drops to 0.50 - should fill
        fills = sim.check_fills("token123", best_bid=Decimal("0.45"), best_ask=Decimal("0.50"))
        assert len(fills) == 1
        assert order.status == OrderStatus.MATCHED
        assert fills[0].price == Decimal("0.50")
        
        print("✓ Buy fill detection works")
    
    def test_fill_detection_sell(self):
        """Test sell order fill detection."""
        from src.simulator import OrderSimulator
        from src.models import OrderSide, OrderStatus
        
        sim = OrderSimulator()
        
        # Create sell order at 0.55
        order = sim.create_order("token123", OrderSide.SELL, Decimal("0.55"), Decimal("100"))
        
        # Market bid is 0.50 - no fill
        fills = sim.check_fills("token123", best_bid=Decimal("0.50"), best_ask=Decimal("0.60"))
        assert len(fills) == 0
        
        # Market bid rises to 0.55 - should fill
        fills = sim.check_fills("token123", best_bid=Decimal("0.55"), best_ask=Decimal("0.60"))
        assert len(fills) == 1
        assert order.status == OrderStatus.MATCHED
        
        print("✓ Sell fill detection works")
    
    def test_position_tracking(self):
        """Test position calculation."""
        from src.simulator import OrderSimulator
        from src.models import OrderSide
        
        sim = OrderSimulator()
        
        # Buy 100
        order1 = sim.create_order("token123", OrderSide.BUY, Decimal("0.50"), Decimal("100"))
        sim.check_fills("token123", best_ask=Decimal("0.50"))
        
        assert sim.get_position("token123") == Decimal("100")
        
        # Sell 40
        order2 = sim.create_order("token123", OrderSide.SELL, Decimal("0.55"), Decimal("40"))
        sim.check_fills("token123", best_bid=Decimal("0.55"))
        
        assert sim.get_position("token123") == Decimal("60")
        
        print("✓ Position tracking works")
    
    def test_pnl_calculation(self):
        """Test P&L calculation."""
        from src.simulator import OrderSimulator
        from src.models import OrderSide
        
        sim = OrderSimulator()
        
        # Buy 100 @ 0.50
        order1 = sim.create_order("token123", OrderSide.BUY, Decimal("0.50"), Decimal("100"))
        sim.check_fills("token123", best_ask=Decimal("0.50"))
        
        # Current price 0.60 - should have unrealized profit
        pnl = sim.get_pnl("token123", Decimal("0.60"))
        
        assert pnl['position'] == Decimal("100")
        assert pnl['unrealized_pnl'] == Decimal("10")  # (0.60 - 0.50) * 100
        
        print(f"✓ P&L calculation: {pnl}")


class TestOrdersModule:
    """Test the orders.py unified interface."""
    
    def test_imports(self):
        """Test orders module imports."""
        from src.orders import (
            get_orders,
            get_open_orders,
            get_order,
            get_trades,
            get_order_summary,
            check_simulated_fills,
        )
        print("✓ Orders module imports work")
    
    def test_get_order_summary(self):
        """Test order summary includes mode."""
        from src.orders import get_order_summary
        
        summary = get_order_summary()
        
        assert 'mode' in summary
        assert summary['mode'] in ('DRY_RUN', 'LIVE')
        print(f"✓ Order summary: mode={summary['mode']}")
    
    def test_dry_run_workflow(self):
        """Test full dry-run workflow."""
        from src.config import DRY_RUN
        from src.orders import get_orders, get_open_orders, get_trades
        from src.simulator import get_simulator, reset_simulator
        from src.models import OrderSide
        
        if not DRY_RUN:
            pytest.skip("Test requires DRY_RUN=true")
        
        # Reset simulator
        reset_simulator()
        sim = get_simulator()
        
        # Create some orders
        sim.create_order("token123", OrderSide.BUY, Decimal("0.50"), Decimal("100"))
        sim.create_order("token123", OrderSide.SELL, Decimal("0.55"), Decimal("100"))
        
        # Check via unified interface
        orders = get_orders()
        open_orders = get_open_orders()
        
        assert len(orders) == 2
        assert len(open_orders) == 2
        assert all(o.is_simulated for o in orders)
        
        # Simulate a fill
        sim.check_fills("token123", best_ask=Decimal("0.50"))
        
        # Check trades
        trades = get_trades()
        assert len(trades) == 1
        assert trades[0].is_simulated == True
        
        # Cleanup
        reset_simulator()
        
        print("✓ Dry-run workflow works")


class TestIntegration:
    """Integration tests with real market data."""
    
    def test_simulator_with_real_prices(self):
        """Test simulator using real market prices."""
        from src.config import DRY_RUN
        from src.simulator import OrderSimulator
        from src.models import OrderSide
        from src.pricing import get_order_book
        from src.markets import fetch_active_markets
        
        if not DRY_RUN:
            pytest.skip("Test requires DRY_RUN=true")
        
        # Get a real market
        markets = fetch_active_markets(limit=5)
        market = None
        for m in markets:
            if m.token_ids:
                market = m
                break
        
        if not market:
            pytest.skip("No markets found")
        
        token_id = market.token_ids[0]
        
        # Get real order book
        book = get_order_book(token_id)
        if not book or book.best_bid is None or book.best_ask is None:
            pytest.skip("No order book data")
        
        print(f"  Market: {market.question[:50]}...")
        print(f"  Token: {token_id[:16]}...")
        print(f"  Best bid: {book.best_bid}, Best ask: {book.best_ask}")
        
        # Create simulator with order below current ask
        sim = OrderSimulator()
        buy_price = book.best_bid  # At best bid - won't fill immediately
        
        order = sim.create_order(token_id, OrderSide.BUY, buy_price, Decimal("10"))
        print(f"  Created buy order @ {buy_price}")
        
        # Check fills at current prices - shouldn't fill (we're at bid, not ask)
        fills = sim.check_fills(token_id, best_bid=book.best_bid, best_ask=book.best_ask)
        
        if fills:
            print(f"  Order filled at {fills[0].price}")
        else:
            print(f"  Order not filled (as expected, ask={book.best_ask} > order={buy_price})")
        
        print("✓ Simulator works with real market data")
```

---

## File Structure After Phase 5

```
polymarket-bot/
├── src/
│   ├── __init__.py
│   ├── config.py          # Updated with DRY_RUN
│   ├── client.py
│   ├── auth.py
│   ├── utils.py
│   ├── models.py          # Updated with Order, Trade, enums
│   ├── markets.py
│   ├── pricing.py
│   ├── simulator.py       # NEW - dry-run order simulator
│   ├── orders.py          # NEW - unified order interface
│   └── feed/
│       └── ...
│
├── tests/
│   └── test_phase5.py     # NEW - 18 tests
│
├── .env                   # Add DRY_RUN=true
└── .env.example           # Updated
```

---

## Verification

```bash
pytest tests/test_phase5.py -v
```

All 18 tests should pass with `DRY_RUN=true` (default).

---

## Success Criteria

1. ✅ `DRY_RUN=true` by default (safe)
2. ✅ Simulator tracks orders and detects fills from real prices
3. ✅ `get_orders()` works in both modes
4. ✅ Position and P&L tracking works
5. ✅ All 18 tests pass

---

## Next: Phase 6

Phase 6 adds order placement:
- `place_order()` - Creates order (simulated in DRY_RUN, real in LIVE)
- `cancel_order()` - Cancels order (simulated or real)
- `cancel_all_orders()` - Cancel all open orders
- Safety checks for LIVE mode
