"""
Capital Allocator

Allocates capital between markets based on scoring.
"""

from decimal import Decimal
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class AllocationResult:
    """Result of allocation calculation."""
    token_id: str
    allocation: Decimal
    score: float
    weight: float

class CapitalAllocator:
    """
    Allocates capital between markets.

    Strategies:
    - equal: Equal allocation to all markets
    - scored: Weight by market score
    - risk_parity: Equal risk contribution

    Usage:
        allocator = CapitalAllocator(total_capital=Decimal("1000"))

        allocations = allocator.allocate(
            markets=["token-1", "token-2"],
            scores={"token-1": 80, "token-2": 60},
            method="scored",
        )
    """

    def __init__(
        self,
        total_capital: Decimal,
        min_allocation: Decimal = Decimal("50"),
        max_allocation_pct: float = 0.5,
    ):
        self.total_capital = total_capital
        self.min_allocation = min_allocation
        self.max_allocation_pct = max_allocation_pct

    def allocate(
        self,
        markets: List[str],
        scores: Optional[Dict[str, float]] = None,
        method: str = "equal",
    ) -> List[AllocationResult]:
        """
        Allocate capital to markets.

        Args:
            markets: List of token IDs
            scores: Optional scores for weighted allocation
            method: "equal" or "scored"

        Returns:
            List of allocation results
        """
        if not markets:
            return []

        scores = scores or {}

        if method == "scored" and scores:
            return self._allocate_scored(markets, scores)
        else:
            return self._allocate_equal(markets)

    def _allocate_equal(self, markets: List[str]) -> List[AllocationResult]:
        """Equal allocation."""
        per_market = self.total_capital / len(markets)
        per_market = min(per_market, self.total_capital * Decimal(str(self.max_allocation_pct)))
        per_market = max(per_market, self.min_allocation)

        return [
            AllocationResult(
                token_id=token_id,
                allocation=per_market,
                score=0.0,
                weight=1.0 / len(markets),
            )
            for token_id in markets
        ]

    def _allocate_scored(
        self,
        markets: List[str],
        scores: Dict[str, float],
    ) -> List[AllocationResult]:
        """Score-weighted allocation."""
        # Get scores, default to 1.0
        market_scores = {m: scores.get(m, 1.0) for m in markets}
        total_score = sum(market_scores.values())

        if total_score == 0:
            return self._allocate_equal(markets)

        results = []
        for token_id in markets:
            score = market_scores[token_id]
            weight = score / total_score
            allocation = self.total_capital * Decimal(str(weight))

            # Apply bounds
            allocation = min(allocation, self.total_capital * Decimal(str(self.max_allocation_pct)))
            allocation = max(allocation, self.min_allocation)

            results.append(AllocationResult(
                token_id=token_id,
                allocation=allocation,
                score=score,
                weight=weight,
            ))

        return results
