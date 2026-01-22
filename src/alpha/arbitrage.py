"""
YES/NO Arbitrage Detection

Polymarket markets have YES and NO tokens that should sum to ~$1.00.
When they diverge beyond fees, arbitrage exists.

Strategies:
1. SELL_BOTH: YES + NO > $1.00 + fees -> sell both, guaranteed profit
2. BUY_BOTH: YES + NO < $1.00 - fees -> buy both, guaranteed profit
3. SKEW_QUOTES: Near-arbitrage -> skew MM quotes to capture
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, List, Tuple, Callable
from enum import Enum


class ArbitrageType(Enum):
    NONE = "none"
    SELL_BOTH = "sell_both"      # Prices too high
    BUY_BOTH = "buy_both"        # Prices too low
    SKEW_QUOTES = "skew_quotes"  # Near-arbitrage, adjust quotes


@dataclass
class ArbitrageSignal:
    """Detected arbitrage opportunity."""
    type: ArbitrageType
    yes_token_id: str
    no_token_id: str
    yes_price: Decimal
    no_price: Decimal
    sum_price: Decimal
    profit_bps: int              # Profit in basis points
    confidence: float            # 0.0-1.0
    recommended_action: str      # Human-readable action

    @property
    def is_actionable(self) -> bool:
        return self.type != ArbitrageType.NONE and self.profit_bps > 10


@dataclass
class TokenPair:
    """YES/NO token pair for a market."""
    condition_id: str
    yes_token_id: str
    no_token_id: str
    market_slug: str


class ArbitrageDetector:
    """
    Monitors YES/NO pairs for arbitrage opportunities.

    Usage:
        detector = ArbitrageDetector(fee_rate=0.001)

        # Check single pair
        signal = detector.check_pair(yes_price=0.55, no_price=0.48, pair=pair)

        # Scan all tracked pairs
        signals = detector.scan_all(price_feed)
    """

    # Thresholds
    ARBITRAGE_MIN_PROFIT_BPS = 20    # 0.2% minimum for execution
    SKEW_THRESHOLD_BPS = 10          # 0.1% for quote skewing
    CONFIDENCE_DECAY_SECONDS = 5     # Signal confidence decays over time

    def __init__(
        self,
        fee_rate: Decimal = Decimal("0.001"),  # 0.1% per side
        min_profit_bps: int = 20,
    ):
        self.fee_rate = fee_rate
        self.min_profit_bps = min_profit_bps
        self._pairs: dict[str, TokenPair] = {}
        self._last_signals: dict[str, ArbitrageSignal] = {}

    def register_pair(self, pair: TokenPair):
        """Register a YES/NO pair for monitoring."""
        self._pairs[pair.condition_id] = pair

    def check_pair(
        self,
        yes_price: Decimal,
        no_price: Decimal,
        pair: TokenPair,
    ) -> ArbitrageSignal:
        """
        Check a single pair for arbitrage.

        Args:
            yes_price: Current YES token mid price
            no_price: Current NO token mid price
            pair: Token pair info

        Returns:
            ArbitrageSignal with opportunity details
        """
        sum_price = yes_price + no_price

        # Calculate deviation from fair value ($1.00)
        deviation = sum_price - Decimal("1.00")
        deviation_bps = int(abs(deviation) * 10000)

        # Account for round-trip fees (buy + sell = 2x fee)
        fee_cost_bps = int(self.fee_rate * 2 * 10000)
        net_profit_bps = deviation_bps - fee_cost_bps

        # Determine arbitrage type
        if deviation > 0 and net_profit_bps >= self.min_profit_bps:
            arb_type = ArbitrageType.SELL_BOTH
            action = f"SELL YES@{yes_price} + SELL NO@{no_price} = ${sum_price} profit"
            confidence = min(1.0, net_profit_bps / 100)

        elif deviation < 0 and net_profit_bps >= self.min_profit_bps:
            arb_type = ArbitrageType.BUY_BOTH
            action = f"BUY YES@{yes_price} + BUY NO@{no_price} = ${sum_price} discount"
            confidence = min(1.0, net_profit_bps / 100)

        elif abs(deviation_bps) >= self.SKEW_THRESHOLD_BPS:
            arb_type = ArbitrageType.SKEW_QUOTES
            if deviation > 0:
                action = "Prices high - skew asks lower to sell"
            else:
                action = "Prices low - skew bids higher to buy"
            confidence = 0.5
            net_profit_bps = abs(deviation_bps)  # Potential, not guaranteed

        else:
            arb_type = ArbitrageType.NONE
            action = "No opportunity"
            confidence = 0.0
            net_profit_bps = 0

        return ArbitrageSignal(
            type=arb_type,
            yes_token_id=pair.yes_token_id,
            no_token_id=pair.no_token_id,
            yes_price=yes_price,
            no_price=no_price,
            sum_price=sum_price,
            profit_bps=net_profit_bps,
            confidence=confidence,
            recommended_action=action,
        )

    def scan_all(self, price_getter: Callable[[str], Optional[Decimal]]) -> List[ArbitrageSignal]:
        """
        Scan all registered pairs for arbitrage.

        Args:
            price_getter: Callable(token_id) -> Optional[Decimal]

        Returns:
            List of actionable signals, sorted by profit
        """
        signals = []

        for condition_id, pair in self._pairs.items():
            yes_price = price_getter(pair.yes_token_id)
            no_price = price_getter(pair.no_token_id)

            if yes_price is None or no_price is None:
                continue

            signal = self.check_pair(yes_price, no_price, pair)
            if signal.is_actionable:
                signals.append(signal)
                self._last_signals[condition_id] = signal

        # Sort by profit descending
        signals.sort(key=lambda s: s.profit_bps, reverse=True)
        return signals

    def get_quote_adjustment(
        self,
        token_id: str,
        base_bid: Decimal,
        base_ask: Decimal,
    ) -> Tuple[Decimal, Decimal]:
        """
        Adjust quotes based on arbitrage signals.

        If near-arbitrage detected, skew quotes to capture.

        Returns:
            (adjusted_bid, adjusted_ask)
        """
        # Find if this token is part of a pair with active signal
        for condition_id, pair in self._pairs.items():
            if token_id not in (pair.yes_token_id, pair.no_token_id):
                continue

            signal = self._last_signals.get(condition_id)
            if signal is None or signal.type == ArbitrageType.NONE:
                continue

            if signal.type == ArbitrageType.SKEW_QUOTES:
                if signal.sum_price > Decimal("1.00"):
                    # Prices high - be more aggressive selling
                    # Lower ask to get filled, raise bid less aggressively
                    skew = Decimal("0.005")  # Half a cent
                    return (base_bid - skew, base_ask - skew * 2)
                else:
                    # Prices low - be more aggressive buying
                    skew = Decimal("0.005")
                    return (base_bid + skew * 2, base_ask + skew)

        return (base_bid, base_ask)
