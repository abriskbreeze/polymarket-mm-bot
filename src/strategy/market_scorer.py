"""
Market scorer - automatically select profitable markets for market making.

Scores markets based on:
- Volume (30%) - need liquidity for fills
- Spread (35%) - 2-8 cents optimal for MM edge
- Depth (15%) - execution quality
- Timing (10%) - avoid resolution edge cases
- Price (10%) - avoid extremes (<5% or >95%)
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, List, Tuple
from datetime import datetime, timezone

from src.config import (
    MARKET_MIN_VOLUME,
    MARKET_MIN_SPREAD,
    MARKET_MAX_SPREAD,
)
from src.models import Market, OrderBook
from src.utils import setup_logging

logger = setup_logging()


@dataclass
class MarketScore:
    """Score breakdown for a market."""
    token_id: str
    market_question: str
    total_score: float  # 0-100

    # Component scores (0-100 each)
    volume_score: float
    spread_score: float
    depth_score: float
    timing_score: float
    price_score: float

    # Raw values for display
    volume_24h: float
    spread: float
    bid_depth: float
    ask_depth: float
    hours_to_resolution: Optional[float]
    mid_price: float

    # Rejection reason if not tradeable
    rejected: bool = False
    reject_reason: str = ""


class MarketScorer:
    """
    Scores markets for market making profitability.

    Usage:
        scorer = MarketScorer()
        scores = scorer.score_markets(markets, order_books)
        best = scores[0]  # Highest scoring market
    """

    # Component weights (must sum to 1.0)
    WEIGHT_VOLUME = 0.30
    WEIGHT_SPREAD = 0.35
    WEIGHT_DEPTH = 0.15
    WEIGHT_TIMING = 0.10
    WEIGHT_PRICE = 0.10

    # Rejection thresholds
    MIN_VOLUME = MARKET_MIN_VOLUME        # $10k default
    MIN_SPREAD = MARKET_MIN_SPREAD        # 2 cents
    MAX_SPREAD = MARKET_MAX_SPREAD        # 15 cents
    MIN_HOURS_TO_RESOLUTION = 12          # Don't trade too close to resolution
    MIN_PRICE = 0.05                      # Avoid extreme prices
    MAX_PRICE = 0.95

    # Optimal ranges for scoring
    OPTIMAL_SPREAD_MIN = 0.02  # 2 cents
    OPTIMAL_SPREAD_MAX = 0.08  # 8 cents
    OPTIMAL_DEPTH_MIN = 100    # $100 minimum depth each side

    def __init__(
        self,
        min_volume: float = MIN_VOLUME,
        min_spread: float = MIN_SPREAD,
        max_spread: float = MAX_SPREAD,
    ):
        self.min_volume = min_volume
        self.min_spread = min_spread
        self.max_spread = max_spread

    def score_market(
        self,
        token_id: str,
        market: Market,
        order_book: Optional[OrderBook],
        volume_24h: float = 0.0,
    ) -> MarketScore:
        """
        Score a single market for MM profitability.

        Args:
            token_id: The token ID to score
            market: Market metadata
            order_book: Current order book (None if unavailable)
            volume_24h: 24-hour trading volume in USD

        Returns:
            MarketScore with breakdown
        """
        # Default values if no order book
        if order_book is None:
            return MarketScore(
                token_id=token_id,
                market_question=market.question,
                total_score=0,
                volume_score=0, spread_score=0, depth_score=0,
                timing_score=0, price_score=0,
                volume_24h=volume_24h, spread=0, bid_depth=0, ask_depth=0,
                hours_to_resolution=None, mid_price=0,
                rejected=True, reject_reason="No order book data"
            )

        # Check for missing bid or ask - can't market make without both
        if not order_book.bids or not order_book.asks:
            return MarketScore(
                token_id=token_id,
                market_question=market.question,
                total_score=0,
                volume_score=0, spread_score=0, depth_score=0,
                timing_score=0, price_score=0,
                volume_24h=volume_24h, spread=0, bid_depth=0, ask_depth=0,
                hours_to_resolution=None, mid_price=0,
                rejected=True, reject_reason="Missing bid or ask side"
            )

        # Extract data
        spread = order_book.spread or 0.0
        mid_price = order_book.midpoint or 0.5
        bid_depth = self._calculate_depth(order_book.bids, within_cents=5)
        ask_depth = self._calculate_depth(order_book.asks, within_cents=5)
        hours_to_resolution = self._hours_until_resolution(market.end_date)

        # Require minimum depth on both sides
        min_depth = 5.0  # $5 minimum
        if bid_depth < min_depth or ask_depth < min_depth:
            return MarketScore(
                token_id=token_id,
                market_question=market.question,
                total_score=0,
                volume_score=0, spread_score=0, depth_score=0,
                timing_score=0, price_score=0,
                volume_24h=volume_24h, spread=spread,
                bid_depth=bid_depth, ask_depth=ask_depth,
                hours_to_resolution=hours_to_resolution, mid_price=mid_price,
                rejected=True, reject_reason=f"Insufficient depth: bid=${bid_depth:.0f}, ask=${ask_depth:.0f}"
            )

        # Check rejection criteria first
        reject_reason = self._check_rejection(
            volume_24h, spread, mid_price, hours_to_resolution
        )
        if reject_reason:
            return MarketScore(
                token_id=token_id,
                market_question=market.question,
                total_score=0,
                volume_score=0, spread_score=0, depth_score=0,
                timing_score=0, price_score=0,
                volume_24h=volume_24h, spread=spread,
                bid_depth=bid_depth, ask_depth=ask_depth,
                hours_to_resolution=hours_to_resolution, mid_price=mid_price,
                rejected=True, reject_reason=reject_reason
            )

        # Calculate component scores
        volume_score = self._score_volume(volume_24h)
        spread_score = self._score_spread(spread)
        depth_score = self._score_depth(bid_depth, ask_depth)
        timing_score = self._score_timing(hours_to_resolution)
        price_score = self._score_price(mid_price)

        # Weighted total
        total_score = (
            volume_score * self.WEIGHT_VOLUME +
            spread_score * self.WEIGHT_SPREAD +
            depth_score * self.WEIGHT_DEPTH +
            timing_score * self.WEIGHT_TIMING +
            price_score * self.WEIGHT_PRICE
        )

        return MarketScore(
            token_id=token_id,
            market_question=market.question,
            total_score=total_score,
            volume_score=volume_score,
            spread_score=spread_score,
            depth_score=depth_score,
            timing_score=timing_score,
            price_score=price_score,
            volume_24h=volume_24h,
            spread=spread,
            bid_depth=bid_depth,
            ask_depth=ask_depth,
            hours_to_resolution=hours_to_resolution,
            mid_price=mid_price
        )

    def score_markets(
        self,
        markets: List[Tuple[str, Market, Optional[OrderBook], float]],
    ) -> List[MarketScore]:
        """
        Score multiple markets and return sorted by score.

        Args:
            markets: List of (token_id, market, order_book, volume_24h)

        Returns:
            List of MarketScore, sorted best-to-worst
        """
        scores = []
        for token_id, market, order_book, volume in markets:
            score = self.score_market(token_id, market, order_book, volume)
            scores.append(score)

        # Sort by total score (descending), rejected markets last
        scores.sort(key=lambda s: (not s.rejected, s.total_score), reverse=True)
        return scores

    def _check_rejection(
        self,
        volume: float,
        spread: float,
        mid_price: float,
        hours_to_resolution: Optional[float],
    ) -> str:
        """Check if market should be rejected. Returns reason or empty string."""
        if volume < self.min_volume:
            return f"Volume too low: ${volume:.0f} < ${self.min_volume:.0f}"

        if spread < self.min_spread:
            return f"Spread too tight: {spread:.3f} < {self.min_spread:.3f}"

        if spread > self.max_spread:
            return f"Spread too wide: {spread:.3f} > {self.max_spread:.3f}"

        if mid_price < self.MIN_PRICE:
            return f"Price too low: {mid_price:.2f} < {self.MIN_PRICE:.2f}"

        if mid_price > self.MAX_PRICE:
            return f"Price too high: {mid_price:.2f} > {self.MAX_PRICE:.2f}"

        if hours_to_resolution is not None:
            if hours_to_resolution < self.MIN_HOURS_TO_RESOLUTION:
                return f"Too close to resolution: {hours_to_resolution:.1f}h < {self.MIN_HOURS_TO_RESOLUTION}h"

        return ""

    def _score_volume(self, volume: float) -> float:
        """Score volume (0-100). Higher is better, diminishing returns above $100k."""
        if volume <= 0:
            return 0

        # Log scale with diminishing returns
        # $10k = 50, $50k = 75, $100k = 85, $500k = 95
        import math
        score = 50 + 20 * math.log10(volume / self.min_volume)
        return max(0, min(100, score))

    def _score_spread(self, spread: float) -> float:
        """Score spread (0-100). Optimal is 2-8 cents."""
        if spread <= 0:
            return 0

        # Perfect score for 3-6 cents (sweet spot)
        if 0.03 <= spread <= 0.06:
            return 100

        # Good score for 2-8 cents
        if self.OPTIMAL_SPREAD_MIN <= spread <= self.OPTIMAL_SPREAD_MAX:
            if spread < 0.03:
                # 2-3 cents: gradually improve toward 3c
                return 80 + 20 * (spread - 0.02) / 0.01
            else:
                # 6-8 cents: gradually decline from 6c
                return 100 - 25 * (spread - 0.06) / 0.02

        # Outside optimal range but still acceptable
        if spread < self.OPTIMAL_SPREAD_MIN:
            # Too tight (1-2c) - very competitive, harder to profit
            return 50 + 30 * spread / self.OPTIMAL_SPREAD_MIN
        else:
            # Too wide (8-15c) - less activity
            return max(0, 75 - 75 * (spread - self.OPTIMAL_SPREAD_MAX) / 0.07)

    def _score_depth(self, bid_depth: float, ask_depth: float) -> float:
        """Score order book depth (0-100). Need liquidity on both sides."""
        min_depth = min(bid_depth, ask_depth)

        if min_depth < 50:
            # Very thin - risky
            return min_depth

        if min_depth >= 500:
            # Excellent depth
            return 100

        # Linear scale $50-$500 -> 50-100
        return 50 + 50 * (min_depth - 50) / 450

    def _score_timing(self, hours_to_resolution: Optional[float]) -> float:
        """Score time until resolution (0-100). Prefer more time."""
        if hours_to_resolution is None:
            # No end date - perpetual market or unknown
            return 80  # Decent score

        if hours_to_resolution < 24:
            # Less than a day - increasing risk
            return max(0, 50 * hours_to_resolution / 24)

        if hours_to_resolution < 72:
            # 1-3 days - moderate
            return 50 + 30 * (hours_to_resolution - 24) / 48

        if hours_to_resolution < 168:  # 7 days
            # 3-7 days - good
            return 80 + 15 * (hours_to_resolution - 72) / 96

        # More than a week - excellent
        return 95 + min(5, (hours_to_resolution - 168) / 168)

    def _score_price(self, mid_price: float) -> float:
        """Score price level (0-100). Prefer mid-range prices."""
        # Optimal is 0.30-0.70 (most price discovery)
        if 0.30 <= mid_price <= 0.70:
            return 100

        # Acceptable is 0.15-0.85
        if 0.15 <= mid_price < 0.30:
            return 70 + 30 * (mid_price - 0.15) / 0.15
        if 0.70 < mid_price <= 0.85:
            return 70 + 30 * (0.85 - mid_price) / 0.15

        # Edges (0.05-0.15 or 0.85-0.95) - risky but tradeable
        if 0.05 <= mid_price < 0.15:
            return 30 + 40 * (mid_price - 0.05) / 0.10
        if 0.85 < mid_price <= 0.95:
            return 30 + 40 * (0.95 - mid_price) / 0.10

        # Extreme edges - very risky
        return max(0, 30 * (mid_price / 0.05 if mid_price < 0.05 else (1 - mid_price) / 0.05))

    def _calculate_depth(
        self,
        levels: List,
        within_cents: float = 5,
    ) -> float:
        """Calculate total depth within X cents of best price."""
        if not levels:
            return 0.0

        best_price = levels[0].price
        total = 0.0

        for level in levels:
            if abs(level.price - best_price) <= within_cents / 100:
                total += level.price * level.size

        return total

    def _hours_until_resolution(self, end_date: Optional[str]) -> Optional[float]:
        """Calculate hours until market resolution."""
        if not end_date:
            return None

        try:
            # Parse ISO format
            if 'Z' in end_date:
                end_date = end_date.replace('Z', '+00:00')
            end_dt = datetime.fromisoformat(end_date)

            # Ensure timezone aware
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            delta = end_dt - now
            return max(0, delta.total_seconds() / 3600)
        except (ValueError, TypeError):
            return None


def get_best_markets(
    markets: List[Tuple[str, Market, Optional[OrderBook], float]],
    top_n: int = 5,
) -> List[MarketScore]:
    """
    Convenience function to get top N markets for trading.

    Args:
        markets: List of (token_id, market, order_book, volume_24h)
        top_n: Number of markets to return

    Returns:
        Top N non-rejected MarketScores
    """
    scorer = MarketScorer()
    scores = scorer.score_markets(markets)

    # Filter out rejected and take top N
    valid = [s for s in scores if not s.rejected]
    return valid[:top_n]
