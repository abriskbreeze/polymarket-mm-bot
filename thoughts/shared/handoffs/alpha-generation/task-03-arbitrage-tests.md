# Task 03: Arbitrage Detection Tests

**Status:** COMPLETE
**Created:** 2025-01-21

## Summary

Created comprehensive test suite for the ArbitrageDetector module with 27 tests covering all public methods and edge cases.

## Tests Created

File: `/Users/rico/Desktop/Portfolio25/bots/mm-v2/tests/test_arbitrage.py`

### Test Classes

1. **TestArbitrageSignal** (3 tests)
   - `test_is_actionable_true_when_profit_above_threshold` - Validates actionable logic
   - `test_is_actionable_false_when_none_type` - NONE type is never actionable
   - `test_is_actionable_false_when_low_profit` - Low profit signals not actionable

2. **TestArbitrageDetector** (8 tests)
   - `test_no_arbitrage_fair_price` - No signal when prices sum to $1.00
   - `test_sell_both_arbitrage` - Detect SELL_BOTH when sum > $1.00 + fees
   - `test_buy_both_arbitrage` - Detect BUY_BOTH when sum < $1.00 - fees
   - `test_skew_quotes_near_arbitrage_high` - SKEW_QUOTES for near-arb (high)
   - `test_skew_quotes_near_arbitrage_low` - SKEW_QUOTES for near-arb (low)
   - `test_fee_adjusted_threshold` - Arb must exceed fee cost
   - `test_under_fee_threshold_becomes_skew` - Sub-threshold becomes SKEW
   - `test_below_all_thresholds` - Very small deviations return NONE

3. **TestArbitrageDetectorRegisterAndScan** (4 tests)
   - `test_register_pair` - Pair registration works
   - `test_scan_all_finds_opportunities` - Finds multiple opportunities
   - `test_scan_all_handles_missing_prices` - Graceful handling of missing data
   - `test_scan_all_caches_signals` - Signals cached in `_last_signals`

4. **TestGetQuoteAdjustment** (4 tests)
   - `test_no_adjustment_without_signal` - No adjustment without active signal
   - `test_no_adjustment_for_unknown_token` - Unknown tokens unchanged
   - `test_skew_adjustment_prices_high` - Quotes skewed for aggressive selling
   - `test_skew_adjustment_prices_low` - Quotes skewed for aggressive buying

5. **TestEdgeCases** (8 tests)
   - `test_zero_prices` - Handles zero prices
   - `test_very_high_prices` - Handles extreme prices (0.99 each)
   - `test_exact_threshold_boundaries` - Boundary condition at 20 bps
   - `test_custom_fee_rate` - Respects custom fee rate
   - `test_custom_min_profit_bps` - Respects custom profit threshold
   - `test_confidence_calculation_sell_both` - Confidence scales with profit
   - `test_confidence_calculation_buy_both` - Confidence for buy arb
   - `test_confidence_skew_is_half` - SKEW signals have 0.5 confidence

## Test Results

```
27 passed in 0.05s
```

## Fixes Made During Testing

Initial test values didn't account for the precise threshold logic:
- SKEW_QUOTES only triggers when: `SKEW_THRESHOLD_BPS (10) <= deviation < min_profit_bps (20) + fee_cost_bps (20)`
- Fixed 5 failing tests by adjusting prices to land in the SKEW zone (sum = 1.003 or 0.997)

## Key Implementation Details Verified

1. Fee calculation: 2x fee_rate (buy + sell) = 20 bps with default 0.1% fee
2. SELL_BOTH threshold: net profit >= 20 bps (default min_profit_bps)
3. BUY_BOTH threshold: same as SELL_BOTH for discount
4. SKEW_QUOTES: deviation >= 10 bps but net profit < 20 bps
5. NONE: deviation < 10 bps

## Dependencies

- `src/alpha/arbitrage.py` - Implementation (Task 01)
- pytest - Test framework
