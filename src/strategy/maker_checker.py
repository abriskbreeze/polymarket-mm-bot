"""
Maker/Taker Classification

Ensures orders are placed to qualify for maker rebates.
"""

from decimal import Decimal
from typing import Optional


class MakerChecker:
    """
    Checks and adjusts orders to ensure maker status.

    Usage:
        checker = MakerChecker()

        if not checker.would_be_maker("BUY", my_price, best_ask):
            my_price = checker.adjust_to_maker("BUY", my_price, best_ask)
    """

    def __init__(self, tick_size: Decimal = Decimal("0.01")):
        self.tick_size = tick_size

    def would_be_maker(
        self,
        side: str,
        price: Decimal,
        best_bid: Optional[Decimal] = None,
        best_ask: Optional[Decimal] = None,
    ) -> bool:
        """
        Check if order would be a maker (add liquidity).

        Args:
            side: "BUY" or "SELL"
            price: Order price
            best_bid: Current best bid (needed for sells)
            best_ask: Current best ask (needed for buys)

        Returns:
            True if order would rest on book (maker)
        """
        if side == "BUY":
            if best_ask is None:
                return True  # No asks, definitely maker
            return price < best_ask

        else:  # SELL
            if best_bid is None:
                return True  # No bids, definitely maker
            return price > best_bid

    def adjust_to_maker(
        self,
        side: str,
        price: Decimal,
        best_bid: Optional[Decimal] = None,
        best_ask: Optional[Decimal] = None,
    ) -> Decimal:
        """
        Adjust price to ensure maker status.

        Args:
            side: "BUY" or "SELL"
            price: Desired price
            best_bid: Current best bid
            best_ask: Current best ask

        Returns:
            Adjusted price that will be maker
        """
        if self.would_be_maker(side, price, best_bid, best_ask):
            return price

        if side == "BUY" and best_ask is not None:
            # Move bid below ask
            return best_ask - self.tick_size

        elif side == "SELL" and best_bid is not None:
            # Move ask above bid
            return best_bid + self.tick_size

        return price
