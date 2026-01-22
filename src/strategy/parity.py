"""YES/NO Parity Check for Arbitrage Detection."""

from decimal import Decimal
from enum import Enum


class ParityStatus(Enum):
    """Status of YES/NO price parity."""

    FAIR = "fair"
    OVERPRICED = "overpriced"
    UNDERPRICED = "underpriced"
    NEAR_ARBITRAGE = "near_arbitrage"


def check_parity(
    yes_price: Decimal,
    no_price: Decimal,
    tolerance: Decimal = Decimal("0.02"),
) -> ParityStatus:
    """
    Check if YES + NO prices are at fair value.

    In a binary prediction market, YES + NO should equal ~$1.00.
    Deviations indicate arbitrage opportunities:
    - Overpriced (>$1.02): Sell both sides for guaranteed profit
    - Underpriced (<$0.98): Buy both sides for guaranteed profit
    - Near-arbitrage ($1.01-$1.02): Edge exists but may not cover fees

    Args:
        yes_price: Current YES token price
        no_price: Current NO token price
        tolerance: Acceptable deviation from $1.00 (default 2 cents)

    Returns:
        ParityStatus indicating pricing state
    """
    sum_price = yes_price + no_price
    one = Decimal("1.00")

    if sum_price > one + tolerance:
        return ParityStatus.OVERPRICED
    elif sum_price < one - tolerance:
        return ParityStatus.UNDERPRICED
    elif abs(sum_price - one) >= Decimal("0.01"):
        return ParityStatus.NEAR_ARBITRAGE
    else:
        return ParityStatus.FAIR
