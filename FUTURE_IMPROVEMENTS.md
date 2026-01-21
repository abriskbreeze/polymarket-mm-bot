# Future Improvements (Option B)

Track items to revisit after basic end-to-end flow is working.

---

## Deferred Complexity (Removed in Simplification)

### REST Fallback
**What:** Automatic fallback to REST polling when WebSocket fails.
**Why Deferred:** If WebSocket fails, market making shouldn't continue anyway - REST is too slow.
**When to Add:** If we need data for non-latency-sensitive operations (reporting, reconciliation).

### Sequence Tracking
**What:** Detect gaps in message sequences to identify missed updates.
**Why Deferred:** Simpler to just reconnect if data seems stale.
**When to Add:** If we see issues with silent data corruption in production.

### Multiple Data Source Abstraction
**What:** Unified interface that switches between WS/REST transparently.
**Why Deferred:** Added complexity for edge case.
**When to Add:** If we have multiple data sources (e.g., multiple exchanges).

---

## Missing Risk Controls (Add Before Real Money)

### Adverse Selection Protection
**What:** Detect when market is moving fast (news) and pull quotes.
**Why Needed:** Informed traders will pick off stale quotes.
**Implementation Ideas:**
- Track price velocity (change per second)
- Widen spread or stop quoting when velocity exceeds threshold
- Monitor trade flow imbalance (all buys = someone knows something)

### Resolution Risk Management
**What:** Stop trading as markets approach resolution.
**Why Needed:** Binary outcome at resolution = huge risk.
**Implementation Ideas:**
- Stop quoting X hours before resolution
- Reduce position size as resolution approaches
- Use GTD orders that expire before resolution

### Inventory Management
**What:** Handle accumulated one-sided positions.
**Why Needed:** Holding large inventory exposes you to directional risk.
**Implementation Ideas:**
- Skew quotes to encourage offsetting trades (lower bid if long, higher ask if short)
- Position limits that halt quoting on one side
- Hedging on related markets

### Market Selection Criteria
**What:** Logic for choosing which markets to trade.
**Why Needed:** Not all markets are good for market making.
**Implementation Ideas:**
- Minimum daily volume threshold
- Maximum spread threshold (too wide = no activity)
- Minimum time to resolution
- Liquidity reward eligibility

---

## Simulator Improvements

### Realistic Fill Modeling
**Current:** Assumes instant fill when price touches order price.
**Reality:** Queue position, partial fills, skipped levels.
**Improvement:**
- Model queue position (orders placed earlier fill first)
- Partial fills based on volume at price level
- Random fill probability based on historical fill rates

### Adverse Selection Simulation
**Current:** None - all fills are "good" fills.
**Reality:** Fills often happen right before price moves against you.
**Improvement:**
- After a fill, simulate price movement in unfavorable direction
- Use historical trade data to model fill quality

---

## Production Hardening (Phase 10+)

### Monitoring & Alerting
- P&L alerts (daily loss limit breach)
- Position alerts (approaching limits)
- Connectivity alerts (WebSocket disconnections)
- Fill rate monitoring (expected vs actual)

### State Persistence
- Save open orders to disk
- Recover state after restart
- Reconcile with exchange on startup

### Graceful Degradation
- Partial functionality when some systems fail
- Automatic position reduction when issues detected
- Clear status dashboard

---

## When to Revisit

1. **After Phase 7 works end-to-end** - Basic market making loop functional
2. **After first real trades** - Understand actual fill rates and behavior
3. **After first loss** - Will reveal which protections are most urgent
4. **Before scaling up** - Before increasing order sizes significantly

---

*Created during architecture review, Phase 5*
*Revisit after basic bot is profitable with tiny sizes*
