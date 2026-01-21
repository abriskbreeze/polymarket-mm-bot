"""
Local storage for market data.
"""

import time
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from src.models import OrderBook, PriceLevel


@dataclass
class TokenData:
    """Data for a single token."""
    token_id: str
    order_book: Optional[OrderBook] = None
    last_price: Optional[float] = None
    last_trade_price: Optional[float] = None
    last_trade_side: Optional[str] = None
    last_trade_size: Optional[float] = None
    last_update: float = 0.0

    def update_timestamp(self):
        self.last_update = time.time()

    def seconds_since_update(self) -> float:
        if self.last_update == 0:
            return float('inf')
        return time.time() - self.last_update


class DataStore:
    """
    Thread-safe storage for market data.

    Updated by WebSocket messages or REST polls.
    Read by the market maker for current prices.
    """

    def __init__(self, stale_threshold: float = 30.0):
        self._data: Dict[str, TokenData] = {}
        self._stale_threshold = stale_threshold
        self._sequence: Dict[str, int] = {}  # For gap detection
        self._gap_count: Dict[str, int] = {}

    # === Data Access ===

    def get(self, token_id: str) -> Optional[TokenData]:
        return self._data.get(token_id)

    def get_midpoint(self, token_id: str) -> Optional[float]:
        data = self._data.get(token_id)
        if data and data.order_book:
            return data.order_book.midpoint
        return None

    def get_order_book(self, token_id: str) -> Optional[OrderBook]:
        data = self._data.get(token_id)
        return data.order_book if data else None

    def get_spread(self, token_id: str) -> Optional[float]:
        data = self._data.get(token_id)
        if data and data.order_book:
            return data.order_book.spread
        return None

    def get_best_bid(self, token_id: str) -> Optional[float]:
        data = self._data.get(token_id)
        if data and data.order_book:
            return data.order_book.best_bid
        return None

    def get_best_ask(self, token_id: str) -> Optional[float]:
        data = self._data.get(token_id)
        if data and data.order_book:
            return data.order_book.best_ask
        return None

    # === Health Checks ===

    def is_fresh(self, token_id: str) -> bool:
        """Check if token data is fresh (not stale)."""
        data = self._data.get(token_id)
        if not data:
            return False
        return data.seconds_since_update() < self._stale_threshold

    def all_fresh(self) -> bool:
        """Check if all tracked tokens have fresh data."""
        if not self._data:
            return False
        return all(self.is_fresh(tid) for tid in self._data)

    def has_gaps(self) -> bool:
        """Check if any sequence gaps were detected."""
        return any(count > 0 for count in self._gap_count.values())

    # === Updates ===

    def register_token(self, token_id: str):
        """Start tracking a token."""
        if token_id not in self._data:
            self._data[token_id] = TokenData(token_id=token_id)
            self._sequence[token_id] = -1
            self._gap_count[token_id] = 0

    def unregister_token(self, token_id: str):
        """Stop tracking a token."""
        self._data.pop(token_id, None)
        self._sequence.pop(token_id, None)
        self._gap_count.pop(token_id, None)

    def check_sequence(self, token_id: str, seq: Optional[int]) -> bool:
        """
        Check message sequence, detect gaps.
        Returns True if sequence is OK, False if gap detected.
        """
        if seq is None:
            return True

        last = self._sequence.get(token_id, -1)

        if last == -1:
            # First message
            self._sequence[token_id] = seq
            return True

        expected = last + 1
        if seq == expected:
            self._sequence[token_id] = seq
            return True

        # Gap detected
        self._gap_count[token_id] = self._gap_count.get(token_id, 0) + 1
        self._sequence[token_id] = seq
        return False

    def clear_gaps(self, token_id: str):
        """Clear gap count after resync."""
        self._gap_count[token_id] = 0

    def update_book(self, token_id: str, bids: list, asks: list, timestamp: Optional[str] = None):
        """Update order book from message."""
        if token_id not in self._data:
            self.register_token(token_id)

        data = self._data[token_id]

        # Parse price levels
        parsed_bids = [
            PriceLevel(price=float(b['price']), size=float(b['size']))
            for b in bids if isinstance(b, dict)
        ]
        parsed_asks = [
            PriceLevel(price=float(a['price']), size=float(a['size']))
            for a in asks if isinstance(a, dict)
        ]

        # Sort: bids descending, asks ascending
        parsed_bids.sort(key=lambda x: x.price, reverse=True)
        parsed_asks.sort(key=lambda x: x.price)

        data.order_book = OrderBook(
            token_id=token_id,
            bids=parsed_bids,
            asks=parsed_asks,
            timestamp=timestamp
        )
        data.update_timestamp()

    def update_price(self, token_id: str, price: float):
        """Update last price."""
        if token_id not in self._data:
            self.register_token(token_id)

        self._data[token_id].last_price = price
        self._data[token_id].update_timestamp()

    def update_trade(self, token_id: str, price: float, size: Optional[float] = None, side: Optional[str] = None):
        """Update last trade."""
        if token_id not in self._data:
            self.register_token(token_id)

        data = self._data[token_id]
        data.last_trade_price = price
        data.last_trade_size = size
        data.last_trade_side = side
        data.update_timestamp()

    def get_token_ids(self) -> List[str]:
        """Get all tracked token IDs."""
        return list(self._data.keys())

    def clear(self):
        """Clear all data."""
        self._data.clear()
        self._sequence.clear()
        self._gap_count.clear()
