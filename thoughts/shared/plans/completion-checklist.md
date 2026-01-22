# MM-V2 Completion Checklist

**Status**: 8/10 - Production-ready with minor gaps
**Tests**: 325 passed, 2 skipped
**Last Updated**: 2026-01-22

---

## Executive Summary

The bot has implemented ~90% of the profitability improvement plan. What remains:

| Category | Items | Priority | Effort |
|----------|-------|----------|--------|
| Config Extraction | 8 values | Medium | 2h |
| Missing Tests | 2 modules | Low | 4h |
| Backtest Validation | Untested | Medium | 3h |
| Production Ops | Not started | High | 8h |

---

## 1. Config Extraction (Remaining Hardcoded Values)

The config.py already has **75+ configurable values**. These 8 remain hardcoded:

### In src/alpha/competitors.py
```python
# Line ~45: Aggression threshold
AGGRESSION_THRESHOLD = 0.7  # Should be: COMPETITOR_AGGRESSION_THRESHOLD

# Line ~52: MM cluster count
N_CLUSTERS = 5  # Should be: COMPETITOR_CLUSTER_COUNT
```

### In src/alpha/regime.py
```python
# Line ~30: Crisis threshold
CRISIS_THRESHOLD = 0.1  # Should be: REGIME_CRISIS_THRESHOLD (add to config)
```

### In src/risk/adverse_selection.py
```python
# Line ~25: Price move threshold
PRICE_MOVE_THRESHOLD = 0.005  # Should be: ADVERSE_PRICE_MOVE_THRESHOLD

# Line ~28: Highly toxic threshold
HIGHLY_TOXIC_THRESHOLD = 0.6  # Should be: ADVERSE_HIGHLY_TOXIC_THRESHOLD
```

### In src/risk/kelly.py
```python
# Line ~18: Minimum trades for Kelly
MIN_TRADES = 20  # Should be: KELLY_MIN_TRADES
```

### In src/strategy/market_scorer.py
```python
# Line ~35-37: Scoring weights
VOLUME_WEIGHT = 0.30
SPREAD_WEIGHT = 0.35
DEPTH_WEIGHT = 0.20
RESOLUTION_WEIGHT = 0.15
# Should be: MARKET_SCORE_VOLUME_WEIGHT, etc.
```

### Action Required
- [ ] Add 8 config variables to src/config.py
- [ ] Update modules to import from config
- [ ] Document in .env.example

**Estimated Effort**: 2 hours

---

## 2. Missing Test Coverage

### Current Coverage
- **325 tests passing** across 32 test files
- Strategy: 14 modules, 12 have tests
- Alpha: 7 modules, all have tests
- Risk: 6 modules, all have tests

### Missing Tests

| Module | Priority | Why |
|--------|----------|-----|
| `src/strategy/allocator.py` | Medium | Capital allocation logic |
| `src/strategy/runner.py` | Low | Orchestration (integration tested) |

### Test Templates

```python
# tests/test_allocator.py
import pytest
from src.strategy.allocator import CapitalAllocator

class TestCapitalAllocator:
    def test_equal_allocation(self):
        """Test equal allocation across N markets"""
        allocator = CapitalAllocator(total_capital=1000)
        result = allocator.allocate(n_markets=4)
        assert sum(result.values()) == 1000

    def test_performance_weighted_allocation(self):
        """Test allocation weighted by historical performance"""
        pass

    def test_risk_adjusted_allocation(self):
        """Test allocation considers position correlation"""
        pass
```

### Action Required
- [ ] Write test_allocator.py (8-10 tests)
- [ ] Add integration test for runner.py
- [ ] Verify all edge cases in backtest/engine.py

**Estimated Effort**: 4 hours

---

## 3. Backtest Validation

### Current State
- `src/backtest/data.py` - Data loading implemented
- `src/backtest/engine.py` - Engine implemented
- `tests/test_backtest.py` - EXISTS but need to verify coverage

### Validation Checklist

```bash
# Run backtest tests
source venv/bin/activate && python -m pytest tests/test_backtest.py -v
```

- [ ] Test data loading from historical files
- [ ] Test fill simulation accuracy
- [ ] Test P&L calculation matches live simulation
- [ ] Benchmark: run backtest on 1 week of data
- [ ] Compare backtest results to DRY_RUN results

### Backtest Benchmark Protocol
```python
# Run this to validate backtest engine
from src.backtest.engine import BacktestEngine
from src.backtest.data import load_historical_data

# 1. Load sample data (need to create/download)
data = load_historical_data("2026-01-01", "2026-01-07")

# 2. Run backtest with default strategy
results = BacktestEngine().run(data, strategy="smart_mm")

# 3. Verify P&L calculation
assert results.total_pnl is not None
assert results.sharpe_ratio is not None
```

### Data Needed
- [ ] Download/generate 1 week of historical order book data
- [ ] Create data fixtures for reproducible tests

**Estimated Effort**: 3 hours

---

## 4. Production Operations

### 4.1 Monitoring Setup

| Component | Tool | Status |
|-----------|------|--------|
| Logs | File/stdout | Done |
| Metrics | Prometheus? | Not done |
| Alerts | PagerDuty/Discord? | Not done |
| Dashboard | Grafana? | Not done |

### Minimum Viable Monitoring
```python
# src/telemetry/prometheus.py (proposed)
from prometheus_client import Counter, Gauge, Histogram

# Key metrics
orders_placed = Counter('mm_orders_placed_total', 'Orders placed', ['side', 'market'])
orders_filled = Counter('mm_orders_filled_total', 'Orders filled', ['side'])
position_value = Gauge('mm_position_value_usd', 'Current position value', ['token'])
pnl_daily = Gauge('mm_pnl_daily_usd', 'Daily P&L')
quote_latency = Histogram('mm_quote_latency_seconds', 'Quote update latency')
```

### Alerting Rules
```yaml
# alerts.yaml (proposed)
alerts:
  - name: daily_loss_limit
    condition: pnl_daily < -40
    severity: critical
    action: notify + pause trading

  - name: high_latency
    condition: quote_latency_p99 > 1s
    severity: warning
    action: notify

  - name: no_fills_1h
    condition: orders_filled == 0 for 1h
    severity: warning
    action: notify
```

### Action Required
- [ ] Add prometheus_client to requirements.txt
- [ ] Create src/telemetry/prometheus.py
- [ ] Add metrics to SmartMarketMaker._loop_iteration()
- [ ] Create alerting webhook (Discord or Slack)
- [ ] Set up Grafana dashboard (optional for v1)

**Estimated Effort**: 8 hours

---

## 5. Pre-Live Checklist

Before going from DRY_RUN to LIVE:

### Security
- [ ] API keys in .env (not committed)
- [ ] .gitignore includes *.env, credentials.json
- [ ] No hardcoded secrets in code
- [ ] Position limits enforced (RISK_ENFORCE=true)

### Risk Controls
- [ ] Daily loss limit set (currently $50)
- [ ] Position limits per market (currently $100)
- [ ] Kill switch tested manually
- [ ] Adverse selection detection enabled

### Testing
- [ ] Run DRY_RUN for 24h+ without errors
- [ ] Verify fill simulation matches expected behavior
- [ ] Check P&L tracking accuracy
- [ ] Test WebSocket reconnection

### Operational
- [ ] Monitoring alerts configured
- [ ] Runbook for common issues
- [ ] Documented shutdown procedure
- [ ] Backup API credentials

---

## 6. Implementation Priority

### Week 1: Critical Path
1. **Day 1-2**: Config extraction (8 values)
2. **Day 3**: Backtest validation
3. **Day 4-5**: 24h DRY_RUN stress test

### Week 2: Production Hardening
4. **Day 1-2**: Basic monitoring (Prometheus metrics)
5. **Day 3**: Discord/Slack alerting
6. **Day 4-5**: Documentation & runbook

### Week 3: Go-Live
7. **Day 1**: Final security audit
8. **Day 2**: Small-size live test ($10 positions)
9. **Day 3-5**: Monitor and tune

---

## 7. Success Metrics (Post-Launch)

Track these daily:

| Metric | Target | Current |
|--------|--------|---------|
| Daily P&L | +$50-200 | Unknown |
| Win Rate | 52-55% | Unknown |
| Fill Rate | 70%+ | Unknown |
| Sharpe Ratio | >2.0 | Unknown |
| Max Drawdown | <$100 | Unknown |
| Uptime | >99% | Unknown |

---

## Quick Commands

```bash
# Run all tests
source venv/bin/activate && python -m pytest tests/ -v

# Run specific module tests
python -m pytest tests/test_smart_mm.py -v

# Run bot in DRY_RUN
DRY_RUN=true python -m src.strategy.runner

# Check config values
python -c "from src import config; print(f'DRY_RUN={config.DRY_RUN}')"
```

---

*Generated: 2026-01-22*
