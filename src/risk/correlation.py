"""
Correlation-Aware Risk Management

Tracks correlations between markets and limits correlated exposure.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import numpy as np


@dataclass
class CorrelationEntry:
    """Correlation between two markets."""
    market_a: str
    market_b: str
    correlation: float
    sample_count: int


class CorrelationTracker:
    """
    Tracks price correlations between markets.

    Usage:
        tracker = CorrelationTracker()

        # Record prices over time
        tracker.record_price("market_a", 0.55)
        tracker.record_price("market_b", 0.45)

        # Get correlation
        corr = tracker.get_correlation("market_a", "market_b")
    """

    MIN_SAMPLES = 20

    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self._prices: Dict[str, List[float]] = defaultdict(list)

    def record_price(self, market: str, price: float):
        """Record a price observation."""
        self._prices[market].append(price)

        # Keep only recent prices
        if len(self._prices[market]) > self.window_size:
            self._prices[market] = self._prices[market][-self.window_size:]

    def get_correlation(self, market_a: str, market_b: str) -> float:
        """Calculate correlation between two markets."""
        prices_a = self._prices.get(market_a, [])
        prices_b = self._prices.get(market_b, [])

        if len(prices_a) < self.MIN_SAMPLES or len(prices_b) < self.MIN_SAMPLES:
            return 0.0  # Not enough data

        # Align lengths
        min_len = min(len(prices_a), len(prices_b))
        prices_a = prices_a[-min_len:]
        prices_b = prices_b[-min_len:]

        # Calculate correlation
        try:
            corr = np.corrcoef(prices_a, prices_b)[0, 1]
            return float(corr) if not np.isnan(corr) else 0.0
        except Exception:
            return 0.0

    def get_all_correlations(self) -> List[CorrelationEntry]:
        """Get correlations between all tracked markets."""
        markets = list(self._prices.keys())
        entries = []

        for i, market_a in enumerate(markets):
            for market_b in markets[i + 1:]:
                corr = self.get_correlation(market_a, market_b)
                min_samples = min(len(self._prices[market_a]), len(self._prices[market_b]))

                entries.append(CorrelationEntry(
                    market_a=market_a,
                    market_b=market_b,
                    correlation=corr,
                    sample_count=min_samples,
                ))

        return entries


class PortfolioRisk:
    """
    Portfolio-level risk management with correlation awareness.

    Usage:
        risk = PortfolioRisk(max_correlated_exposure=Decimal("200"))

        # Set correlations
        risk.set_correlation("market_a", "market_b", 0.8)

        # Check if can add position
        if risk.can_add_position("market_a", size, existing_positions):
            # Proceed with trade
            pass
    """

    def __init__(
        self,
        max_correlated_exposure: Decimal = Decimal("500"),
        correlation_threshold: float = 0.5,
    ):
        self.max_correlated_exposure = max_correlated_exposure
        self.correlation_threshold = correlation_threshold
        self._correlations: Dict[Tuple[str, str], float] = {}

    def set_correlation(self, market_a: str, market_b: str, correlation: float):
        """Set correlation between markets."""
        key = (market_a, market_b) if market_a <= market_b else (market_b, market_a)
        self._correlations[key] = correlation

    def get_correlation(self, market_a: str, market_b: str) -> float:
        """Get correlation between markets."""
        key = (market_a, market_b) if market_a <= market_b else (market_b, market_a)
        return self._correlations.get(key, 0.0)

    def can_add_position(
        self,
        market: str,
        size: Decimal,
        existing_positions: Dict[str, Decimal],
    ) -> bool:
        """Check if position can be added without exceeding correlated limits."""
        correlated_exposure = Decimal("0")

        for other_market, other_size in existing_positions.items():
            if other_market == market:
                continue

            corr = self.get_correlation(market, other_market)

            if corr >= self.correlation_threshold:
                # Count as correlated exposure
                correlated_exposure += other_size

        # Would new position exceed limit?
        return (correlated_exposure + size) <= self.max_correlated_exposure

    def calculate_portfolio_beta(self, positions: Dict[str, Decimal]) -> float:
        """
        Calculate portfolio beta based on correlations.

        Higher beta = more correlated positions = more risk.
        """
        if len(positions) <= 1:
            return 1.0

        total_exposure = sum(abs(p) for p in positions.values())
        if total_exposure == 0:
            return 1.0

        # Weight-adjusted correlation contribution
        markets = list(positions.keys())
        correlation_sum = 0.0

        for i, market_a in enumerate(markets):
            for market_b in markets[i + 1:]:
                corr = self.get_correlation(market_a, market_b)
                weight_a = float(abs(positions[market_a]) / total_exposure)
                weight_b = float(abs(positions[market_b]) / total_exposure)

                correlation_sum += corr * weight_a * weight_b

        # Beta increases with positive correlations
        return 1.0 + correlation_sum
