"""
Data models for Polymarket bot.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime
from enum import Enum
from decimal import Decimal


@dataclass
class PriceLevel:
    """Single price level in order book"""
    price: float
    size: float


@dataclass
class OrderBook:
    """Order book for a token"""
    token_id: str
    bids: List[PriceLevel]
    asks: List[PriceLevel]
    timestamp: Optional[str] = None

    @property
    def best_bid(self) -> Optional[float]:
        """Best (highest) bid price"""
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        """Best (lowest) ask price"""
        return self.asks[0].price if self.asks else None

    @property
    def spread(self) -> Optional[float]:
        """Bid-ask spread"""
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None

    @property
    def midpoint(self) -> Optional[float]:
        """Midpoint price"""
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return None


@dataclass
class Outcome:
    """Single outcome in a market"""
    name: str
    token_id: str
    price: Optional[float] = None


@dataclass
class Market:
    """Polymarket market"""
    condition_id: str
    question: str
    slug: str
    outcomes: List[Outcome]
    active: bool = True
    closed: bool = False
    volume: float = 0.0
    liquidity: float = 0.0
    end_date: Optional[str] = None
    description: Optional[str] = None

    @property
    def token_ids(self) -> List[str]:
        """Get all token IDs for this market"""
        return [o.token_id for o in self.outcomes]


@dataclass
class Event:
    """Polymarket event (can contain multiple markets)"""
    event_id: str
    title: str
    slug: str
    markets: List[Market] = field(default_factory=list)
    active: bool = True


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
    size: Decimal
    filled: Decimal
    status: OrderStatus
    is_simulated: bool = False

    # Optional fields
    created_at: Optional[str] = None
    expiration: Optional[str] = None
    order_type: OrderType = OrderType.GTC
    market_id: Optional[str] = None

    @property
    def remaining(self) -> Decimal:
        """Size remaining to be filled."""
        return self.size - self.filled

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
        if self.size == 0:
            return 0.0
        return float(self.filled / self.size) * 100


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
    is_simulated: bool = False

    # Optional
    timestamp: Optional[str] = None
    fee: Decimal = Decimal("0")
    market_id: Optional[str] = None

    @property
    def value(self) -> Decimal:
        """Total value of the trade."""
        return self.price * self.size
