"""
Data models for Polymarket bot.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


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
