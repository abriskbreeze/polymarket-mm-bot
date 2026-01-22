"""Per-Market P&L Tracking."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional


@dataclass
class MarketStats:
    """Statistics for a single market."""

    market_id: str
    trade_count: int = 0
    total_bought: Decimal = field(default_factory=lambda: Decimal("0"))
    total_sold: Decimal = field(default_factory=lambda: Decimal("0"))
    total_buy_value: Decimal = field(default_factory=lambda: Decimal("0"))
    total_sell_value: Decimal = field(default_factory=lambda: Decimal("0"))
    realized_pnl: Decimal = field(default_factory=lambda: Decimal("0"))
    winning_trades: int = 0
    losing_trades: int = 0

    @property
    def win_rate(self) -> float:
        """Calculate win rate as fraction of winning trades."""
        total = self.winning_trades + self.losing_trades
        return self.winning_trades / total if total > 0 else 0.0


@dataclass
class TradeRecord:
    """A single trade record for position tracking."""

    side: str
    price: Decimal
    size: Decimal


class MarketPnLTracker:
    """
    Tracks P&L per market using FIFO matching.

    Usage:
        tracker = MarketPnLTracker()

        # Record trades
        tracker.record_trade("market-1", "BUY", Decimal("0.50"), Decimal("10"))
        tracker.record_trade("market-1", "SELL", Decimal("0.55"), Decimal("10"))

        # Get stats
        stats = tracker.get_market_stats("market-1")
        print(f"P&L: {stats.realized_pnl}")  # $0.50
    """

    def __init__(self):
        self._stats: Dict[str, MarketStats] = {}
        self._open_positions: Dict[str, List[TradeRecord]] = {}

    def record_trade(
        self,
        market_id: str,
        side: str,
        price: Decimal,
        size: Decimal,
    ) -> None:
        """
        Record a trade and update P&L.

        Args:
            market_id: Unique market identifier
            side: "BUY" or "SELL"
            price: Trade price
            size: Trade size (number of contracts)
        """
        # Initialize if needed
        if market_id not in self._stats:
            self._stats[market_id] = MarketStats(market_id=market_id)
            self._open_positions[market_id] = []

        stats = self._stats[market_id]
        stats.trade_count += 1

        if side == "BUY":
            stats.total_bought += size
            stats.total_buy_value += price * size
            self._open_positions[market_id].append(TradeRecord("BUY", price, size))

        else:  # SELL
            stats.total_sold += size
            stats.total_sell_value += price * size

            # Match against open buys (FIFO)
            remaining = size
            while remaining > 0 and self._open_positions[market_id]:
                buy = self._open_positions[market_id][0]
                if buy.side != "BUY":
                    self._open_positions[market_id].pop(0)
                    continue

                matched = min(remaining, buy.size)
                pnl = matched * (price - buy.price)
                stats.realized_pnl += pnl

                if pnl > 0:
                    stats.winning_trades += 1
                else:
                    stats.losing_trades += 1

                remaining -= matched
                buy.size -= matched

                if buy.size <= 0:
                    self._open_positions[market_id].pop(0)

    def get_market_stats(self, market_id: str) -> Optional[MarketStats]:
        """Get stats for a market, or None if not tracked."""
        return self._stats.get(market_id)

    def get_all_stats(self) -> List[MarketStats]:
        """Get stats for all tracked markets."""
        return list(self._stats.values())

    def get_best_markets(self, top_n: int = 5) -> List[MarketStats]:
        """Get top performing markets by realized P&L."""
        all_stats = self.get_all_stats()
        all_stats.sort(key=lambda s: s.realized_pnl, reverse=True)
        return all_stats[:top_n]

    def get_worst_markets(self, top_n: int = 5) -> List[MarketStats]:
        """Get worst performing markets by realized P&L."""
        all_stats = self.get_all_stats()
        all_stats.sort(key=lambda s: s.realized_pnl)
        return all_stats[:top_n]

    def get_total_pnl(self) -> Decimal:
        """Get total realized P&L across all markets."""
        return sum(
            (s.realized_pnl for s in self._stats.values()),
            Decimal("0"),
        )
