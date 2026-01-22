"""Tests for arbitrage detection."""

import pytest
from decimal import Decimal
from src.alpha.arbitrage import ArbitrageDetector, ArbitrageType, ArbitrageSignal, TokenPair


@pytest.fixture
def detector():
    return ArbitrageDetector(fee_rate=Decimal("0.001"))


@pytest.fixture
def test_pair():
    return TokenPair(
        condition_id="test-condition",
        yes_token_id="yes-token-123",
        no_token_id="no-token-456",
        market_slug="test-market",
    )


class TestArbitrageSignal:
    """Tests for ArbitrageSignal dataclass."""

    def test_is_actionable_true_when_profit_above_threshold(self):
        """Signal is actionable when type is not NONE and profit > 10 bps."""
        signal = ArbitrageSignal(
            type=ArbitrageType.SELL_BOTH,
            yes_token_id="yes",
            no_token_id="no",
            yes_price=Decimal("0.55"),
            no_price=Decimal("0.48"),
            sum_price=Decimal("1.03"),
            profit_bps=30,
            confidence=0.8,
            recommended_action="SELL",
        )
        assert signal.is_actionable is True

    def test_is_actionable_false_when_none_type(self):
        """Signal is not actionable when type is NONE."""
        signal = ArbitrageSignal(
            type=ArbitrageType.NONE,
            yes_token_id="yes",
            no_token_id="no",
            yes_price=Decimal("0.50"),
            no_price=Decimal("0.50"),
            sum_price=Decimal("1.00"),
            profit_bps=20,  # Even with profit
            confidence=0.0,
            recommended_action="No opportunity",
        )
        assert signal.is_actionable is False

    def test_is_actionable_false_when_low_profit(self):
        """Signal is not actionable when profit is too low."""
        signal = ArbitrageSignal(
            type=ArbitrageType.SELL_BOTH,
            yes_token_id="yes",
            no_token_id="no",
            yes_price=Decimal("0.505"),
            no_price=Decimal("0.500"),
            sum_price=Decimal("1.005"),
            profit_bps=5,  # Too low
            confidence=0.5,
            recommended_action="SELL",
        )
        assert signal.is_actionable is False


class TestArbitrageDetector:
    """Tests for ArbitrageDetector class."""

    def test_no_arbitrage_fair_price(self, detector, test_pair):
        """No signal when prices sum to $1.00."""
        signal = detector.check_pair(
            yes_price=Decimal("0.55"),
            no_price=Decimal("0.45"),
            pair=test_pair,
        )
        assert signal.type == ArbitrageType.NONE
        assert signal.sum_price == Decimal("1.00")
        assert signal.profit_bps == 0
        assert not signal.is_actionable

    def test_sell_both_arbitrage(self, detector, test_pair):
        """Detect sell-both when prices too high."""
        signal = detector.check_pair(
            yes_price=Decimal("0.55"),
            no_price=Decimal("0.48"),  # Sum = 1.03
            pair=test_pair,
        )
        assert signal.type == ArbitrageType.SELL_BOTH
        assert signal.sum_price == Decimal("1.03")
        assert signal.is_actionable
        # 3% deviation = 300 bps, minus 20 bps fees = 280 bps net
        assert signal.profit_bps == 280

    def test_buy_both_arbitrage(self, detector, test_pair):
        """Detect buy-both when prices too low."""
        signal = detector.check_pair(
            yes_price=Decimal("0.50"),
            no_price=Decimal("0.47"),  # Sum = 0.97
            pair=test_pair,
        )
        assert signal.type == ArbitrageType.BUY_BOTH
        assert signal.sum_price == Decimal("0.97")
        assert signal.is_actionable
        # 3% deviation = 300 bps, minus 20 bps fees = 280 bps net
        assert signal.profit_bps == 280

    def test_skew_quotes_near_arbitrage_high(self, detector, test_pair):
        """Detect quote skewing opportunity when prices slightly high but below arb threshold.

        SKEW_QUOTES triggers when deviation is:
        - Above SKEW_THRESHOLD_BPS (10 bps)
        - But net profit (after fees) is below min_profit_bps (20 bps)

        With 0.1% fee each way = 20 bps total fees
        Sum = 1.003 = 30 bps deviation
        Net profit = 30 - 20 = 10 bps < 20 bps threshold -> SKEW_QUOTES
        """
        signal = detector.check_pair(
            yes_price=Decimal("0.502"),
            no_price=Decimal("0.501"),  # Sum = 1.003, 30 bps deviation
            pair=test_pair,
        )
        assert signal.type == ArbitrageType.SKEW_QUOTES
        assert signal.sum_price == Decimal("1.003")
        # Skew profits are gross deviation bps
        assert signal.profit_bps == 30
        assert "skew asks" in signal.recommended_action.lower()

    def test_skew_quotes_near_arbitrage_low(self, detector, test_pair):
        """Detect quote skewing opportunity when prices slightly low but below arb threshold."""
        signal = detector.check_pair(
            yes_price=Decimal("0.498"),
            no_price=Decimal("0.499"),  # Sum = 0.997, 30 bps deviation
            pair=test_pair,
        )
        assert signal.type == ArbitrageType.SKEW_QUOTES
        assert signal.sum_price == Decimal("0.997")
        assert signal.profit_bps == 30
        assert "skew bids" in signal.recommended_action.lower()

    def test_fee_adjusted_threshold(self, detector, test_pair):
        """Arbitrage must exceed fees to be actionable."""
        # With 0.1% fee each way, need > 0.2% (20 bps) profit
        # Sum = 1.005 = 50 bps deviation, minus 20 bps fees = 30 bps net
        signal = detector.check_pair(
            yes_price=Decimal("0.505"),
            no_price=Decimal("0.500"),  # Sum = 1.005, 0.5% high
            pair=test_pair,
        )
        # 50 bps gross - 20 bps fees = 30 bps net, exceeds 20 bps threshold
        assert signal.type == ArbitrageType.SELL_BOTH
        assert signal.profit_bps == 30
        assert signal.is_actionable

    def test_under_fee_threshold_becomes_skew(self, detector, test_pair):
        """Below fee threshold but above skew threshold becomes SKEW_QUOTES."""
        # Sum = 1.002 = 20 bps deviation, minus 20 bps fees = 0 bps net
        signal = detector.check_pair(
            yes_price=Decimal("0.501"),
            no_price=Decimal("0.501"),  # Sum = 1.002, 0.2% high
            pair=test_pair,
        )
        # Net profit = 0, but deviation 20 bps >= 10 bps skew threshold
        assert signal.type == ArbitrageType.SKEW_QUOTES
        assert signal.profit_bps == 20  # Gross bps for skew

    def test_below_all_thresholds(self, detector, test_pair):
        """Very small deviation below all thresholds returns NONE."""
        signal = detector.check_pair(
            yes_price=Decimal("0.5005"),
            no_price=Decimal("0.4999"),  # Sum = 1.0004, only 4 bps
            pair=test_pair,
        )
        assert signal.type == ArbitrageType.NONE
        assert signal.profit_bps == 0


class TestArbitrageDetectorRegisterAndScan:
    """Tests for register_pair and scan_all methods."""

    def test_register_pair(self, detector, test_pair):
        """Can register a pair for monitoring."""
        detector.register_pair(test_pair)
        assert test_pair.condition_id in detector._pairs
        assert detector._pairs[test_pair.condition_id] == test_pair

    def test_scan_all_finds_opportunities(self, detector):
        """scan_all finds all actionable opportunities."""
        pair1 = TokenPair(
            condition_id="cond-1",
            yes_token_id="yes-1",
            no_token_id="no-1",
            market_slug="market-1",
        )
        pair2 = TokenPair(
            condition_id="cond-2",
            yes_token_id="yes-2",
            no_token_id="no-2",
            market_slug="market-2",
        )
        pair3 = TokenPair(
            condition_id="cond-3",
            yes_token_id="yes-3",
            no_token_id="no-3",
            market_slug="market-3",
        )

        detector.register_pair(pair1)
        detector.register_pair(pair2)
        detector.register_pair(pair3)

        # Prices: pair1 = arb opportunity, pair2 = fair, pair3 = arb opportunity
        prices = {
            "yes-1": Decimal("0.55"),
            "no-1": Decimal("0.50"),   # Sum = 1.05, big arb
            "yes-2": Decimal("0.55"),
            "no-2": Decimal("0.45"),   # Sum = 1.00, fair
            "yes-3": Decimal("0.45"),
            "no-3": Decimal("0.52"),   # Sum = 0.97, buy arb
        }

        def price_getter(token_id):
            return prices.get(token_id)

        signals = detector.scan_all(price_getter)

        # Should find 2 opportunities
        assert len(signals) == 2

        # Sorted by profit descending
        assert signals[0].sum_price == Decimal("1.05")  # More profitable
        assert signals[0].type == ArbitrageType.SELL_BOTH

        assert signals[1].sum_price == Decimal("0.97")
        assert signals[1].type == ArbitrageType.BUY_BOTH

    def test_scan_all_handles_missing_prices(self, detector):
        """scan_all gracefully handles missing prices."""
        pair = TokenPair(
            condition_id="cond",
            yes_token_id="yes",
            no_token_id="no",
            market_slug="market",
        )
        detector.register_pair(pair)

        # Only YES price available
        def price_getter(token_id):
            return Decimal("0.55") if token_id == "yes" else None

        signals = detector.scan_all(price_getter)
        assert len(signals) == 0

    def test_scan_all_caches_signals(self, detector, test_pair):
        """scan_all caches signals in _last_signals."""
        detector.register_pair(test_pair)

        prices = {
            "yes-token-123": Decimal("0.55"),
            "no-token-456": Decimal("0.50"),  # Sum = 1.05
        }

        def price_getter(token_id):
            return prices.get(token_id)

        signals = detector.scan_all(price_getter)

        assert test_pair.condition_id in detector._last_signals
        cached = detector._last_signals[test_pair.condition_id]
        assert cached.sum_price == Decimal("1.05")


class TestGetQuoteAdjustment:
    """Tests for get_quote_adjustment method."""

    def test_no_adjustment_without_signal(self, detector, test_pair):
        """No adjustment when no active signal."""
        detector.register_pair(test_pair)

        bid, ask = detector.get_quote_adjustment(
            token_id="yes-token-123",
            base_bid=Decimal("0.50"),
            base_ask=Decimal("0.52"),
        )

        assert bid == Decimal("0.50")
        assert ask == Decimal("0.52")

    def test_no_adjustment_for_unknown_token(self, detector):
        """No adjustment for tokens not in registered pairs."""
        bid, ask = detector.get_quote_adjustment(
            token_id="unknown-token",
            base_bid=Decimal("0.50"),
            base_ask=Decimal("0.52"),
        )

        assert bid == Decimal("0.50")
        assert ask == Decimal("0.52")

    def test_skew_adjustment_prices_high(self, detector, test_pair):
        """Skew quotes when prices are high (more aggressive selling).

        Need to trigger SKEW_QUOTES (not SELL_BOTH), so use prices that:
        - Have deviation above SKEW_THRESHOLD_BPS (10 bps)
        - But net profit below min_profit_bps (20 bps)
        """
        detector.register_pair(test_pair)

        # Sum = 1.003 = 30 bps deviation, net = 10 bps -> SKEW_QUOTES
        prices = {
            "yes-token-123": Decimal("0.502"),
            "no-token-456": Decimal("0.501"),
        }
        detector.scan_all(lambda tid: prices.get(tid))

        bid, ask = detector.get_quote_adjustment(
            token_id="yes-token-123",
            base_bid=Decimal("0.50"),
            base_ask=Decimal("0.52"),
        )

        # Prices high - lower ask more aggressively
        assert bid < Decimal("0.50")  # Bid lowered
        assert ask < Decimal("0.52")  # Ask lowered more
        assert ask < bid + Decimal("0.02")  # Spread reduced

    def test_skew_adjustment_prices_low(self, detector, test_pair):
        """Skew quotes when prices are low (more aggressive buying).

        Need to trigger SKEW_QUOTES (not BUY_BOTH), so use prices that:
        - Have deviation above SKEW_THRESHOLD_BPS (10 bps)
        - But net profit below min_profit_bps (20 bps)
        """
        detector.register_pair(test_pair)

        # Sum = 0.997 = 30 bps deviation, net = 10 bps -> SKEW_QUOTES
        prices = {
            "yes-token-123": Decimal("0.498"),
            "no-token-456": Decimal("0.499"),
        }
        detector.scan_all(lambda tid: prices.get(tid))

        bid, ask = detector.get_quote_adjustment(
            token_id="yes-token-123",
            base_bid=Decimal("0.50"),
            base_ask=Decimal("0.52"),
        )

        # Prices low - raise bid more aggressively
        assert bid > Decimal("0.50")  # Bid raised more
        assert ask > Decimal("0.52")  # Ask raised
        assert bid > Decimal("0.50")  # More aggressive on bid side


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_zero_prices(self, detector, test_pair):
        """Handle zero prices gracefully."""
        signal = detector.check_pair(
            yes_price=Decimal("0"),
            no_price=Decimal("0"),
            pair=test_pair,
        )
        # Sum = 0, deviation = -1.00 = 10000 bps, should be BUY_BOTH
        assert signal.type == ArbitrageType.BUY_BOTH
        assert signal.sum_price == Decimal("0")

    def test_very_high_prices(self, detector, test_pair):
        """Handle very high prices."""
        signal = detector.check_pair(
            yes_price=Decimal("0.99"),
            no_price=Decimal("0.99"),  # Sum = 1.98
            pair=test_pair,
        )
        assert signal.type == ArbitrageType.SELL_BOTH
        assert signal.sum_price == Decimal("1.98")
        # 98% deviation = 9800 bps - 20 bps fees
        assert signal.profit_bps == 9780

    def test_exact_threshold_boundaries(self, detector, test_pair):
        """Test exact threshold boundary conditions."""
        # Exactly at min_profit_bps boundary (20 bps)
        # Need deviation that gives exactly 20 bps profit after 20 bps fees
        # So need 40 bps deviation = 1.004
        signal = detector.check_pair(
            yes_price=Decimal("0.502"),
            no_price=Decimal("0.502"),  # Sum = 1.004
            pair=test_pair,
        )
        # 40 bps deviation - 20 bps fees = 20 bps, exactly at threshold
        assert signal.type == ArbitrageType.SELL_BOTH
        assert signal.profit_bps == 20

    def test_custom_fee_rate(self):
        """Detector respects custom fee rate."""
        # Higher fee rate
        detector = ArbitrageDetector(fee_rate=Decimal("0.005"))  # 0.5%
        pair = TokenPair(
            condition_id="test",
            yes_token_id="yes",
            no_token_id="no",
            market_slug="test",
        )

        # 50 bps deviation, but with 100 bps fees (0.5% x 2 sides)
        signal = detector.check_pair(
            yes_price=Decimal("0.505"),
            no_price=Decimal("0.500"),  # Sum = 1.005
            pair=pair,
        )

        # 50 bps - 100 bps fees = -50 bps net profit, should be SKEW
        assert signal.type == ArbitrageType.SKEW_QUOTES

    def test_custom_min_profit_bps(self):
        """Detector respects custom min_profit_bps."""
        # Higher min profit threshold
        detector = ArbitrageDetector(
            fee_rate=Decimal("0.001"),
            min_profit_bps=50,  # Require 50 bps profit
        )
        pair = TokenPair(
            condition_id="test",
            yes_token_id="yes",
            no_token_id="no",
            market_slug="test",
        )

        # 50 bps gross - 20 bps fees = 30 bps net < 50 bps threshold
        signal = detector.check_pair(
            yes_price=Decimal("0.505"),
            no_price=Decimal("0.500"),  # Sum = 1.005
            pair=pair,
        )

        assert signal.type == ArbitrageType.SKEW_QUOTES  # Not SELL_BOTH

    def test_confidence_calculation_sell_both(self, detector, test_pair):
        """Confidence scales with profit for sell_both."""
        signal = detector.check_pair(
            yes_price=Decimal("0.55"),
            no_price=Decimal("0.50"),  # Sum = 1.05, 500 bps - 20 = 480 bps
            pair=test_pair,
        )
        # Confidence = min(1.0, 480/100) = 1.0
        assert signal.confidence == 1.0

        # Smaller opportunity
        signal2 = detector.check_pair(
            yes_price=Decimal("0.505"),
            no_price=Decimal("0.500"),  # Sum = 1.005, 30 bps net
            pair=test_pair,
        )
        # Confidence = 30/100 = 0.3
        assert signal2.confidence == 0.3

    def test_confidence_calculation_buy_both(self, detector, test_pair):
        """Confidence scales with profit for buy_both."""
        signal = detector.check_pair(
            yes_price=Decimal("0.45"),
            no_price=Decimal("0.50"),  # Sum = 0.95, 500 bps - 20 = 480 bps
            pair=test_pair,
        )
        assert signal.confidence == 1.0

    def test_confidence_skew_is_half(self, detector, test_pair):
        """Skew signals have 0.5 confidence (not guaranteed profit).

        Need deviation in SKEW range: above 10 bps but net profit < 20 bps.
        Sum = 1.003 = 30 bps deviation, 30 - 20 = 10 bps net < 20 -> SKEW
        """
        signal = detector.check_pair(
            yes_price=Decimal("0.502"),
            no_price=Decimal("0.501"),  # Sum = 1.003
            pair=test_pair,
        )
        assert signal.type == ArbitrageType.SKEW_QUOTES
        assert signal.confidence == 0.5
