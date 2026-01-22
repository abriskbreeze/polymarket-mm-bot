"""
Kelly Criterion Position Sizing

Calculates optimal position size based on edge and variance.

Kelly Formula: f* = (p*b - q) / b
Where:
- f* = fraction of bankroll to bet
- p = probability of winning
- q = probability of losing (1-p)
- b = ratio of win to loss (win_amount / loss_amount)

We use fractional Kelly (typically 0.25-0.5) for safety.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Dict, Optional

from src.config import (
    KELLY_FRACTION,
    KELLY_MAX_POSITION,
    KELLY_MIN_TRADES,
)


@dataclass
class KellyResult:
    """Kelly calculation result."""
    full_kelly: float
    applied_kelly: float
    fraction_used: float
    win_rate: float
    win_loss_ratio: float
    recommended_size: Decimal


class KellyCalculator:
    """
    Calculates Kelly criterion position sizing.

    Usage:
        kelly = KellyCalculator(fraction=0.25)  # Quarter Kelly

        # From known stats
        size_pct = kelly.calculate(win_rate=0.55, win_loss_ratio=1.2)

        # From trade history
        size_pct = kelly.calculate_from_trades(trade_history)

        # Get actual position size
        kelly.set_bankroll(Decimal("10000"))
        shares = kelly.get_position_size(win_rate, ratio, price)
    """

    MIN_TRADES_FOR_KELLY = KELLY_MIN_TRADES

    def __init__(
        self,
        fraction: float = KELLY_FRACTION,
        max_position_pct: float = KELLY_MAX_POSITION,
    ):
        """
        Args:
            fraction: Kelly fraction to use (0.25 = quarter Kelly)
            max_position_pct: Maximum position as percent of bankroll
        """
        self.fraction = fraction
        self.max_position_pct = max_position_pct
        self._bankroll: Optional[Decimal] = None

    def set_bankroll(self, bankroll: Decimal):
        """Set current bankroll for sizing."""
        self._bankroll = bankroll

    def calculate(
        self,
        win_rate: float,
        win_loss_ratio: float,
    ) -> float:
        """
        Calculate Kelly fraction.

        Args:
            win_rate: Probability of winning (0-1)
            win_loss_ratio: Average win / average loss

        Returns:
            Recommended fraction of bankroll to risk
        """
        if win_rate <= 0 or win_rate >= 1:
            return 0.0

        if win_loss_ratio <= 0:
            return 0.0

        p = win_rate
        q = 1 - win_rate
        b = win_loss_ratio

        # Kelly formula
        full_kelly = (p * b - q) / b

        # Don't bet on negative edge
        if full_kelly <= 0:
            return 0.0

        # Apply fractional Kelly
        applied = full_kelly * self.fraction

        # Cap at max position
        return min(applied, self.max_position_pct)

    def calculate_from_trades(
        self,
        trades: List[Dict],
        min_trades: Optional[int] = None,
    ) -> float:
        """
        Calculate Kelly from trade history.

        Args:
            trades: List of trades with 'pnl' field
            min_trades: Minimum trades required

        Returns:
            Recommended Kelly fraction
        """
        min_trades = min_trades or self.MIN_TRADES_FOR_KELLY

        if len(trades) < min_trades:
            return 0.0

        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] < 0]

        if not wins or not losses:
            return 0.0

        win_rate = len(wins) / len(trades)
        avg_win = sum(t["pnl"] for t in wins) / len(wins)
        avg_loss = abs(sum(t["pnl"] for t in losses) / len(losses))

        if avg_loss == 0:
            return 0.0

        win_loss_ratio = float(avg_win / avg_loss)

        return self.calculate(win_rate, win_loss_ratio)

    def get_position_size(
        self,
        win_rate: float,
        win_loss_ratio: float,
        price: Decimal,
    ) -> Decimal:
        """
        Get position size in shares/contracts.

        Args:
            win_rate: Probability of winning
            win_loss_ratio: Average win / average loss
            price: Current price per unit

        Returns:
            Number of units to trade
        """
        if self._bankroll is None:
            raise ValueError("Bankroll not set. Call set_bankroll() first.")

        kelly_pct = self.calculate(win_rate, win_loss_ratio)

        if kelly_pct <= 0:
            return Decimal("0")

        dollar_amount = self._bankroll * Decimal(str(kelly_pct))
        shares = dollar_amount / price

        return shares.quantize(Decimal("1"))

    def get_result(
        self,
        win_rate: float,
        win_loss_ratio: float,
        price: Optional[Decimal] = None,
    ) -> KellyResult:
        """Get detailed Kelly calculation result."""
        p = win_rate
        q = 1 - win_rate
        b = win_loss_ratio

        full_kelly = max(0, (p * b - q) / b) if b > 0 else 0
        applied_kelly = min(full_kelly * self.fraction, self.max_position_pct)

        size = Decimal("0")
        if self._bankroll and price and applied_kelly > 0:
            size = (self._bankroll * Decimal(str(applied_kelly)) / price).quantize(Decimal("1"))

        return KellyResult(
            full_kelly=full_kelly,
            applied_kelly=applied_kelly,
            fraction_used=self.fraction,
            win_rate=win_rate,
            win_loss_ratio=win_loss_ratio,
            recommended_size=size,
        )
