# Polymarket Market Making Bot - Profitability Improvement Plan

## Executive Summary

This plan outlines improvements to transform the current bot from a basic market maker into a highly profitable trading system. The improvements span four key domains: **Alpha Generation**, **Execution Optimization**, **Risk-Adjusted Returns**, and **Infrastructure Hardening**.

---

## Current State Analysis

### Strengths
1. **Solid Foundation**: Clean architecture with WebSocket/REST fallback, risk management, TUI
2. **SmartMarketMaker**: Already has volatility tracking, inventory skewing, book imbalance detection
3. **Market Scorer**: Auto-selection based on volume, spread, depth
4. **Simulator**: DRY_RUN mode for testing without risk

### Critical Gaps (Profit Blockers)
1. **No Alpha Edge**: Pure market making without informational advantage
2. **Naive Quote Timing**: Fixed loop interval regardless of market conditions
3. **Limited Market Intelligence**: No cross-market correlation or event awareness
4. **Suboptimal Fill Rates**: Not optimizing queue position or maker rebates
5. **Missing Hedge/Arbitrage**: No complementary token trading (YES/NO pairs)

---

## Phase 1: Alpha Generation (Highest ROI)

### 1.1 Event-Driven Intelligence
**Goal**: Trade ahead of predictable price moves

```
New Module: src/alpha/event_tracker.py
- Monitor Polymarket event resolution API
- Track Twitter/X sentiment for high-volume markets
- Parse news feeds for relevant event keywords
- Signal strength: -1.0 (confident NO) to +1.0 (confident YES)
```

**Integration Points**:
- `SmartMarketMaker._calculate_quotes()` - adjust quotes based on event signals
- `MarketScorer` - boost markets with upcoming catalysts

**Expected Impact**: 2-5% edge on event-related price moves

### 1.2 Cross-Market Correlation Trading
**Goal**: Exploit correlated market mispricings

```
New Module: src/alpha/correlation.py
- YES + NO tokens must equal ~$1.00 (minus fees)
- Detect divergence: if YES + NO > $1.02 or < $0.98, arbitrage exists
- Multi-market correlation (e.g., related political outcomes)
```

**Strategy**:
```python
# Arbitrage opportunity detection
if yes_price + no_price > 1.00 + 2*fee_rate:
    # Sell both sides, guaranteed profit
    sell(YES, yes_price)
    sell(NO, no_price)
```

**Expected Impact**: Risk-free 0.5-2% on divergence opportunities

### 1.3 Order Flow Prediction
**Goal**: Predict short-term price direction from order flow

```
New Module: src/alpha/flow_signals.py
- Track aggressive vs passive order ratios
- Detect large order accumulation patterns
- Monitor time-weighted imbalance (recent orders matter more)
```

**Signal Types**:
| Signal | Meaning | Action |
|--------|---------|--------|
| Aggressive buy sweep | Big buyer hitting asks | Widen ask, tighten bid |
| Passive bid stacking | Patient buyer accumulating | Expect upward drift |
| Large cancel on bid | Buyer giving up | Short-term bearish |

**Expected Impact**: 1-3% edge on directional predictions

---

## Phase 2: Execution Optimization

### 2.1 Adaptive Quote Timing
**Goal**: React faster when it matters, save resources when quiet

```
Modify: src/strategy/market_maker.py - _loop_iteration()
- Base interval: 2s (current 1s is excessive for quiet markets)
- Fast mode (100ms): Triggered by price moves > 1%, high volume periods
- Sleep mode (5s): No activity for 60+ seconds
```

**Implementation**:
```python
def _calculate_loop_interval(self) -> float:
    if self._recent_volatility > HIGH_VOL_THRESHOLD:
        return 0.1  # 100ms - fast mode
    if self._seconds_since_activity > 60:
        return 5.0  # Sleep mode
    return 2.0  # Normal
```

### 2.2 Queue Position Optimization
**Goal**: Get filled more often without sacrificing edge

```
New Feature: Smart tick improvement
- If queue is long at best bid, improve by 1 tick
- If queue is short, join at best bid (save edge)
- Track historical fill rates by queue position
```

**Integration**: Modify `BookAnalyzer.suggested_bid/ask` to consider queue depth

### 2.3 Partial Fill Handling
**Goal**: Manage inventory risk from partial fills

```
Modify: src/strategy/inventory.py
- Detect partial fill scenarios
- Immediately hedge with opposing quote tightening
- Track fill rate statistics for strategy tuning
```

### 2.4 Maker Rebate Optimization
**Goal**: Maximize fee rebates from Polymarket

```
Research needed: Polymarket maker/taker fee structure
- Ensure all orders qualify as maker (not crossing spread)
- Optimize order placement timing to avoid taker fills
```

---

## Phase 3: Risk-Adjusted Returns

### 3.1 Dynamic Position Limits
**Goal**: Risk more when confident, less when uncertain

```
Modify: src/risk/manager.py
- Base position limit: current $50-100
- Increase limits when: low volatility, high fill rates, positive P&L streak
- Decrease limits when: high vol, adverse selection detected, drawdown
```

**Formula**:
```python
adjusted_limit = base_limit * confidence_multiplier * (1 - drawdown_penalty)
# confidence_multiplier: 0.5 (uncertain) to 2.0 (high conviction)
# drawdown_penalty: 0 (no drawdown) to 0.5 (at daily loss limit)
```

### 3.2 Adverse Selection Detection
**Goal**: Detect when we're trading against informed flow

```
New Module: src/risk/adverse_selection.py
- Track fill patterns: are our bids getting hit right before price drops?
- Calculate "toxicity" metric for each market
- Widen spreads or reduce size in toxic markets
```

**Metrics**:
```python
toxicity_score = (fills_before_adverse_move) / (total_fills)
# Score > 0.3 = we're getting picked off
```

### 3.3 Kelly Criterion Position Sizing
**Goal**: Mathematically optimal bet sizing

```
Modify: src/strategy/market_maker.py - _update_quotes()
- Track historical win rate and average win/loss
- Apply Kelly formula: f* = (p*b - q) / b
  where p=win_prob, q=1-p, b=win/loss ratio
- Use fractional Kelly (0.25-0.5) for safety
```

### 3.4 Correlation-Aware Risk
**Goal**: Don't accumulate correlated positions

```
Modify: src/risk/manager.py
- Track position correlations across markets
- Reduce total exposure when positions are highly correlated
- Alert when portfolio beta exceeds threshold
```

---

## Phase 4: Infrastructure Hardening

### 4.1 Fill Detection Improvement (LIVE mode)
**Goal**: Instant fill notification without polling

```
New Feature: WebSocket order/trade subscription
- Subscribe to user's order fills via Polymarket WS
- Immediate inventory update on fill
- Remove polling delay for position sync
```

### 4.2 Multi-Market Support
**Goal**: Trade multiple markets simultaneously

```
Modify: src/strategy/market_maker.py
- Create MarketMakerPool that manages N instances
- Shared risk manager with portfolio-level limits
- Intelligent capital allocation between markets
```

**Architecture**:
```
MarketMakerPool
├── SmartMarketMaker(market_1)
├── SmartMarketMaker(market_2)
├── SmartMarketMaker(market_3)
└── SharedRiskManager (portfolio-level limits)
```

### 4.3 Performance Profiling
**Goal**: Ensure latency doesn't cost fills

```
New Module: src/telemetry/latency.py
- Track order placement latency (API call → confirmation)
- Track quote update latency (price change → new quote)
- Alert if latency exceeds thresholds
```

### 4.4 Backtesting Framework
**Goal**: Test strategies on historical data

```
New Module: src/backtest/
- Historical order book data ingestion
- Replay engine simulating fills
- Strategy comparison and optimization
```

---

## Phase 5: Market Intelligence

### 5.1 Competitor Detection
**Goal**: Adapt to other market makers

```
New Module: src/alpha/competitors.py
- Identify recurring order patterns from other MMs
- Detect their spread/size strategies
- Avoid fighting against well-funded competitors
```

### 5.2 Liquidity Regime Detection
**Goal**: Different strategies for different market states

```
New Module: src/alpha/regime.py
- Low liquidity: widen spreads, reduce size
- High liquidity: tighten spreads, increase size
- Event approaching: reduce position, widen spreads
- Event passed: aggressive mean reversion
```

### 5.3 Time-of-Day Patterns
**Goal**: Optimize for predictable volume patterns

```
Analysis needed:
- When is volume highest? (likely US market hours)
- When do spreads widen? (overnight, weekends)
- When are fills most profitable?
```

---

## Implementation Priority

### Immediate (Week 1-2) - Highest ROI
1. **YES/NO Arbitrage Detection** (1.2) - Nearly risk-free profit
2. **Adaptive Loop Interval** (2.1) - Better resource usage
3. **Adverse Selection Detection** (3.2) - Stop bleeding to informed traders

### Short-term (Week 3-4)
4. **Order Flow Signals** (1.3) - Directional edge
5. **Queue Position Optimization** (2.2) - Better fill rates
6. **Multi-Market Support** (4.2) - Scale profits

### Medium-term (Month 2)
7. **Event Intelligence** (1.1) - News-driven alpha
8. **Kelly Sizing** (3.3) - Optimal position sizing
9. **Backtesting Framework** (4.4) - Strategy validation

### Long-term (Month 3+)
10. **Competitor Detection** (5.1) - Strategic adaptation
11. **Regime Detection** (5.2) - Market state awareness
12. **Fill WebSocket** (4.1) - Latency improvement

---

## Quick Wins (Can Implement Today)

### 1. Fix Spread Tightness
Current `SPREAD_BASE = 0.04` (4 cents) may be too tight for thin markets.
```python
# config.py - adjust based on market liquidity
SPREAD_BASE = Decimal("0.05")  # 5 cents base
SPREAD_MIN = Decimal("0.03")   # Never go below 3 cents
```

### 2. Increase Volatility Sensitivity
Current vol multiplier range (0.7-2.0) may not react fast enough.
```python
# config.py
VOL_MULT_MIN = 0.5   # Tighter in calm markets
VOL_MULT_MAX = 3.0   # Wider in volatile markets
```

### 3. Add YES/NO Parity Check
Before placing quotes, verify YES+NO pricing:
```python
# In _calculate_quotes()
no_token_price = self._get_complementary_price()
if yes_mid + no_mid > 1.01:  # Arbitrage exists
    # Don't provide liquidity, look to take
    logger.warning(f"Arbitrage opportunity: {yes_mid + no_mid}")
```

### 4. Track P&L Per Market
Add to `InventoryManager`:
```python
def get_market_pnl(self) -> dict:
    return {
        'realized': self._realized_pnl,
        'unrealized': self._unrealized_pnl,
        'fills': len(self._trades),
        'win_rate': self._win_count / max(1, self._trade_count)
    }
```

---

## Success Metrics

| Metric | Current (Estimated) | Target |
|--------|---------------------|--------|
| Daily P&L | ~$0 (DRY_RUN) | +$50-200 |
| Win Rate | ~50% | 52-55% |
| Fill Rate | Unknown | 70%+ |
| Sharpe Ratio | Unknown | >2.0 |
| Max Drawdown | Unknown | <$100 |
| Avg Spread Captured | Unknown | 80%+ of quoted |

---

## Risk Warnings

1. **Market Risk**: Polymarket outcomes are binary - position limits are critical
2. **Liquidity Risk**: Thin markets can gap through quotes
3. **Regulatory Risk**: Prediction markets face uncertain legal status
4. **Technical Risk**: API outages can leave positions unhedged
5. **Adverse Selection**: Informed traders will pick off naive quotes

---

## Next Steps

1. Review this plan and prioritize based on risk appetite
2. Start with Quick Wins section for immediate improvements
3. Implement YES/NO arbitrage detection (highest risk-adjusted return)
4. Set up proper metrics tracking before going live
5. Run extended DRY_RUN tests with each improvement

---

*Generated: 2026-01-21*
*Bot Version: mm-v2 with SmartMarketMaker*
