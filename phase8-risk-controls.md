# Phase 8: Basic Risk Controls

## Overview

Phase 8 adds safety rails to prevent catastrophic losses:

1. **Daily loss limit** - Stop trading if losses exceed threshold
2. **Kill switch** - Immediate stop, cancel all orders
3. **Position monitoring** - Track and alert on positions
4. **Cooldown** - Pause after errors or rapid losses

**Philosophy:** Simple controls that prevent disaster. Not sophisticated risk management (that's Option B / future).

---

## Data Gathering Mode (Default in Dry-Run)

In dry-run mode, we want **maximum data** for later analysis. Risk rails default to **log-only**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         RISK ENFORCEMENT MODES                          │
└─────────────────────────────────────────────────────────────────────────┘

  DRY_RUN=true (default)                DRY_RUN=false (live)
  RISK_ENFORCE=false (default)          RISK_ENFORCE=true (default)
  ════════════════════════════          ════════════════════════════
  
  Risk event detected:                  Risk event detected:
  → LOG the event                       → LOG the event
  → RECORD for analysis                 → STOP trading
  → CONTINUE trading                    → Cancel all orders
  
  Result: Maximum data collected        Result: Money protected
          Know when rails WOULD stop            Rails enforced
```

**What gets recorded in data-gathering mode:**
- Every risk event (what triggered, when, severity)
- Full P&L distribution (including big losses)
- Position behavior at extremes
- Fill rates across all conditions

**Later analysis can answer:**
- "How often would I have been stopped out?"
- "What's my actual P&L distribution without rails?"
- "Are my limits set correctly?"

---

## What We're Building

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          RISK CONTROLS                                  │
└─────────────────────────────────────────────────────────────────────────┘

  Market Maker Loop
         │
         ▼
  ┌──────────────────┐
  │  RiskManager     │
  │  .check()        │──── Returns: OK, WARN, or STOP
  └──────────────────┘
         │
         ├─── OK:   Continue trading
         ├─── WARN: Log warning, continue (maybe reduce size)
         └─── STOP: Kill switch - cancel all, stop trading

  Triggers for STOP:
  • Daily loss > limit
  • Position > limit (already in Phase 7, but tracked here too)
  • Manual kill switch
  • Too many errors in short time
  • Feed unhealthy for too long
```

---

## Configuration

### Add to src/config.py

```python
# === Risk Management ===
RISK_MAX_DAILY_LOSS = Decimal(os.getenv("RISK_MAX_DAILY_LOSS", "50"))  # Stop if lose $50
RISK_MAX_POSITION = Decimal(os.getenv("RISK_MAX_POSITION", "100"))     # Max position per token
RISK_MAX_TOTAL_EXPOSURE = Decimal(os.getenv("RISK_MAX_TOTAL_EXPOSURE", "500"))  # Total across all
RISK_ERROR_COOLDOWN = int(os.getenv("RISK_ERROR_COOLDOWN", "60"))      # Seconds to pause after errors
RISK_MAX_ERRORS_PER_MINUTE = int(os.getenv("RISK_MAX_ERRORS_PER_MINUTE", "5"))  # Error rate limit

# Enforce risk limits? Default: OFF in dry-run (gather data), ON in live (protect money)
_default_enforce = "false" if DRY_RUN else "true"
RISK_ENFORCE = os.getenv("RISK_ENFORCE", _default_enforce).lower() == "true"
```

### Update .env.example

```bash
# === Risk Management ===
RISK_MAX_DAILY_LOSS=50       # Stop trading if daily loss exceeds this
RISK_MAX_POSITION=100        # Max position per token
RISK_MAX_TOTAL_EXPOSURE=500  # Max total exposure across all tokens
RISK_ERROR_COOLDOWN=60       # Seconds to pause after too many errors
RISK_MAX_ERRORS_PER_MINUTE=5 # Max errors before cooldown

# Enforce risk limits?
# false = log events but continue (good for data gathering in dry-run)
# true = actually stop trading when limits hit
# Default: false in DRY_RUN mode, true in LIVE mode
RISK_ENFORCE=false
```

---

## Implementation

### Create src/risk/\_\_init\_\_.py

```python
"""Risk management."""

from src.risk.manager import (
    RiskManager, 
    RiskStatus, 
    RiskCheck, 
    RiskEvent,
    get_risk_manager,
    reset_risk_manager,
)
```

### Create src/risk/manager.py

```python
"""
Risk manager - safety controls for trading.

Tracks P&L, positions, errors, and triggers kill switch when limits breached.

In data-gathering mode (RISK_ENFORCE=false):
- Logs all risk events but doesn't stop trading
- Captures data for later analysis and improvement
- Default in DRY_RUN mode

In enforcement mode (RISK_ENFORCE=true):
- Actually stops trading when limits hit
- Default in LIVE mode (protects real money)
"""

import time
from enum import Enum
from decimal import Decimal
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import deque

from src.config import (
    DRY_RUN,
    RISK_ENFORCE,
    RISK_MAX_DAILY_LOSS,
    RISK_MAX_POSITION,
    RISK_MAX_TOTAL_EXPOSURE,
    RISK_ERROR_COOLDOWN,
    RISK_MAX_ERRORS_PER_MINUTE,
)
from src.orders import get_position, get_trades
from src.trading import cancel_all_orders
from src.utils import setup_logging

logger = setup_logging()


class RiskStatus(Enum):
    """Risk check result."""
    OK = "OK"           # All clear
    WARN = "WARN"       # Warning, but continue
    STOP = "STOP"       # Kill switch - stop immediately


@dataclass
class RiskCheck:
    """Result of a risk check."""
    status: RiskStatus
    reason: str = ""
    details: Dict = field(default_factory=dict)


@dataclass
class RiskEvent:
    """A logged risk event for later analysis."""
    timestamp: float
    status: str
    reason: str
    details: Dict
    enforced: bool


class RiskManager:
    """
    Manages trading risk.
    
    Usage:
        risk = RiskManager()
        
        # In trading loop:
        check = risk.check()
        if check.status == RiskStatus.STOP:
            cancel_all_orders()
            stop_trading()
        
        # After a trade:
        risk.record_trade(token_id, side, price, size)
        
        # After an error:
        risk.record_error("Connection failed")
        
        # Manual kill switch:
        risk.kill_switch("Manual stop requested")
        
        # Get logged risk events for analysis:
        events = risk.get_risk_events()
    """
    
    def __init__(
        self,
        max_daily_loss: Decimal = RISK_MAX_DAILY_LOSS,
        max_position: Decimal = RISK_MAX_POSITION,
        max_total_exposure: Decimal = RISK_MAX_TOTAL_EXPOSURE,
        error_cooldown: int = RISK_ERROR_COOLDOWN,
        max_errors_per_minute: int = RISK_MAX_ERRORS_PER_MINUTE,
        enforce: bool = RISK_ENFORCE,
    ):
        self.max_daily_loss = max_daily_loss
        self.max_position = max_position
        self.max_total_exposure = max_total_exposure
        self.error_cooldown = error_cooldown
        self.max_errors_per_minute = max_errors_per_minute
        self.enforce = enforce
        
        # State
        self._killed = False
        self._kill_reason = ""
        self._start_time = time.time()
        self._errors: deque = deque(maxlen=100)  # Recent errors with timestamps
        self._cooldown_until: float = 0
        
        # P&L tracking (simple: track entry prices)
        self._trades: List[Dict] = []
        self._daily_pnl = Decimal("0")
        
        # Risk event log for data gathering
        self._risk_events: List[RiskEvent] = []
        
        logger.info(f"RiskManager initialized: enforce={enforce}")
    
    def check(self, token_ids: Optional[List[str]] = None) -> RiskCheck:
        """
        Run all risk checks.
        
        Args:
            token_ids: Tokens to check positions for (optional)
        
        Returns:
            RiskCheck with status and reason
            
        Note:
            If enforce=False, logs STOP/WARN events but returns OK to continue trading.
            This allows maximum data collection in dry-run mode.
        """
        # Always check kill switch (even in non-enforce mode, manual kills apply)
        if self._killed:
            return RiskCheck(RiskStatus.STOP, f"Kill switch: {self._kill_reason}")
        
        # Run all checks
        check = self._run_checks(token_ids)
        
        # If not enforcing and check failed, log but return OK
        if check.status != RiskStatus.OK and not self.enforce:
            self._log_risk_event(check, enforced=False)
            logger.warning(
                f"[DATA MODE] Risk event (not enforced): "
                f"{check.status.value} - {check.reason}"
            )
            return RiskCheck(RiskStatus.OK)
        
        # If enforcing and check failed, log and return the check
        if check.status != RiskStatus.OK:
            self._log_risk_event(check, enforced=True)
        
        return check
    
    def _run_checks(self, token_ids: Optional[List[str]] = None) -> RiskCheck:
        """Run all risk checks and return the result."""
        # Check cooldown
        if time.time() < self._cooldown_until:
            remaining = int(self._cooldown_until - time.time())
            return RiskCheck(RiskStatus.STOP, f"In cooldown for {remaining}s")
        
        # Check error rate
        check = self._check_error_rate()
        if check.status == RiskStatus.STOP:
            return check
        
        # Check daily P&L
        check = self._check_daily_pnl()
        if check.status == RiskStatus.STOP:
            return check
        
        # Check positions
        if token_ids:
            check = self._check_positions(token_ids)
            if check.status != RiskStatus.OK:
                return check
        
        return RiskCheck(RiskStatus.OK)
    
    def _log_risk_event(self, check: RiskCheck, enforced: bool):
        """Log a risk event for later analysis."""
        event = RiskEvent(
            timestamp=time.time(),
            status=check.status.value,
            reason=check.reason,
            details=check.details,
            enforced=enforced
        )
        self._risk_events.append(event)
    
    def _check_error_rate(self) -> RiskCheck:
        """Check if too many errors recently."""
        now = time.time()
        minute_ago = now - 60
        
        recent_errors = sum(1 for ts, _ in self._errors if ts > minute_ago)
        
        if recent_errors >= self.max_errors_per_minute:
            self._cooldown_until = now + self.error_cooldown
            return RiskCheck(
                RiskStatus.STOP,
                f"Too many errors ({recent_errors}/min) - cooling down",
                {"error_count": recent_errors}
            )
        
        return RiskCheck(RiskStatus.OK)
    
    def _check_daily_pnl(self) -> RiskCheck:
        """Check if daily loss limit exceeded."""
        if self._daily_pnl < -self.max_daily_loss:
            if self.enforce:
                self._killed = True
                self._kill_reason = f"Daily loss limit exceeded: {self._daily_pnl}"
            return RiskCheck(
                RiskStatus.STOP,
                f"Daily loss limit exceeded: {self._daily_pnl}",
                {"daily_pnl": float(self._daily_pnl)}
            )
        
        # Warning at 80% of limit
        warn_threshold = -self.max_daily_loss * Decimal("0.8")
        if self._daily_pnl < warn_threshold:
            return RiskCheck(
                RiskStatus.WARN,
                f"Approaching daily loss limit: {self._daily_pnl}",
                {"daily_pnl": float(self._daily_pnl)}
            )
        
        return RiskCheck(RiskStatus.OK)
    
    def _check_positions(self, token_ids: List[str]) -> RiskCheck:
        """Check position limits."""
        total_exposure = Decimal("0")
        
        for token_id in token_ids:
            position = get_position(token_id)
            abs_position = abs(position)
            total_exposure += abs_position
            
            if abs_position > self.max_position:
                return RiskCheck(
                    RiskStatus.WARN,
                    f"Position limit exceeded for {token_id[:16]}: {position}",
                    {"token_id": token_id, "position": float(position)}
                )
        
        if total_exposure > self.max_total_exposure:
            return RiskCheck(
                RiskStatus.WARN,
                f"Total exposure {total_exposure} exceeds limit {self.max_total_exposure}",
                {"total_exposure": float(total_exposure)}
            )
        
        return RiskCheck(RiskStatus.OK)
    
    def record_trade(
        self,
        token_id: str,
        side: str,
        price: Decimal,
        size: Decimal,
        realized_pnl: Optional[Decimal] = None
    ):
        """
        Record a trade for P&L tracking.
        
        If realized_pnl is provided, use it directly.
        Otherwise, we'd need entry price tracking (simplified for now).
        """
        self._trades.append({
            "time": time.time(),
            "token_id": token_id,
            "side": side,
            "price": float(price),
            "size": float(size),
        })
        
        if realized_pnl is not None:
            self._daily_pnl += realized_pnl
            logger.info(f"P&L update: {realized_pnl:+.2f} (daily: {self._daily_pnl:+.2f})")
    
    def record_error(self, error: str):
        """Record an error for rate limiting."""
        self._errors.append((time.time(), error))
        logger.warning(f"Error recorded: {error}")
    
    def kill_switch(self, reason: str = "Manual"):
        """
        Trigger kill switch - immediate stop.
        
        Note: Kill switch is ALWAYS enforced, even in data-gathering mode.
        This is for manual stops or truly critical failures.
        """
        self._killed = True
        self._kill_reason = reason
        logger.critical(f"KILL SWITCH: {reason}")
    
    def reset_kill_switch(self):
        """Reset kill switch (use with caution)."""
        self._killed = False
        self._kill_reason = ""
        logger.info("Kill switch reset")
    
    def reset_daily_pnl(self):
        """Reset daily P&L (call at start of day)."""
        self._daily_pnl = Decimal("0")
        self._trades.clear()
        logger.info("Daily P&L reset")
    
    @property
    def is_killed(self) -> bool:
        """Check if kill switch is active."""
        return self._killed
    
    @property
    def daily_pnl(self) -> Decimal:
        """Get current daily P&L."""
        return self._daily_pnl
    
    def get_risk_events(self) -> List[RiskEvent]:
        """Get all logged risk events for analysis."""
        return self._risk_events.copy()
    
    def get_risk_event_summary(self) -> Dict:
        """Get summary of risk events."""
        if not self._risk_events:
            return {"total_events": 0}
        
        stop_events = [e for e in self._risk_events if e.status == "STOP"]
        warn_events = [e for e in self._risk_events if e.status == "WARN"]
        enforced = [e for e in self._risk_events if e.enforced]
        
        return {
            "total_events": len(self._risk_events),
            "stop_events": len(stop_events),
            "warn_events": len(warn_events),
            "enforced_events": len(enforced),
            "non_enforced_events": len(self._risk_events) - len(enforced),
        }
    
    def get_status(self) -> Dict:
        """Get current risk status summary."""
        now = time.time()
        minute_ago = now - 60
        recent_errors = sum(1 for ts, _ in self._errors if ts > minute_ago)
        
        return {
            "mode": "ENFORCE" if self.enforce else "DATA_GATHER",
            "killed": self._killed,
            "kill_reason": self._kill_reason,
            "daily_pnl": float(self._daily_pnl),
            "max_daily_loss": float(self.max_daily_loss),
            "pnl_percent_of_limit": float(abs(self._daily_pnl) / self.max_daily_loss * 100) if self.max_daily_loss else 0,
            "errors_last_minute": recent_errors,
            "in_cooldown": time.time() < self._cooldown_until,
            "cooldown_remaining": max(0, int(self._cooldown_until - time.time())),
            "uptime_seconds": int(now - self._start_time),
            "risk_events_logged": len(self._risk_events),
        }


# Global instance
_risk_manager: Optional[RiskManager] = None


def get_risk_manager() -> RiskManager:
    """Get global risk manager instance."""
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = RiskManager()
    return _risk_manager


def reset_risk_manager():
    """Reset global risk manager."""
    global _risk_manager
    _risk_manager = None
```

---

## Integrate with Market Maker

### Update src/strategy/market_maker.py

Add risk checks to the main loop:

```python
# Add import at top
from src.risk import RiskManager, RiskStatus, get_risk_manager

# In SimpleMarketMaker.__init__, add:
self.risk = get_risk_manager()

# In _loop_iteration, add at the start:
async def _loop_iteration(self):
    """Single iteration of the market making loop."""
    
    # === RISK CHECK ===
    check = self.risk.check([self.token_id])
    
    if check.status == RiskStatus.STOP:
        # In enforce mode: stop trading
        # In data-gather mode: this won't happen (check returns OK)
        logger.error(f"Risk stop: {check.reason}")
        await self._cancel_all_quotes()
        self.stop()
        return
    
    if check.status == RiskStatus.WARN:
        logger.warning(f"Risk warning: {check.reason}")
        # Could reduce size here in future
    
    # Rest of existing code...
    if not self.feed or not self.feed.is_healthy:
        # ... etc

# In _shutdown, add summary:
async def _shutdown(self):
    """Clean shutdown."""
    logger.info("Shutting down market maker...")
    
    # Log risk event summary
    summary = self.risk.get_risk_event_summary()
    if summary["total_events"] > 0:
        logger.info(f"Risk Event Summary:")
        logger.info(f"  Total events: {summary['total_events']}")
        logger.info(f"  STOP events: {summary['stop_events']} (enforced: {summary['enforced_events']})")
        logger.info(f"  WARN events: {summary['warn_events']}")
        logger.info(f"  Final P&L: {self.risk.daily_pnl}")
    
    # Cancel all orders
    # ... rest of shutdown
```

### Add to the runner for status display

In `src/strategy/runner.py`, update periodic status logging:

```python
async def log_status_periodically(mm: SimpleMarketMaker, interval: float = 30.0):
    """Log status every N seconds."""
    while mm._running:
        await asyncio.sleep(interval)
        if mm._running:
            status = mm.risk.get_status()
            logger.info(
                f"Status: Mode={status['mode']} | "
                f"PnL={status['daily_pnl']:+.2f} ({status['pnl_percent_of_limit']:.0f}% of limit) | "
                f"Events={status['risk_events_logged']}"
            )
```

---

## Tests

### Create tests/test_phase8.py

```python
"""
Phase 8 Tests - Risk management.

Run: pytest tests/test_phase8.py -v
"""

import pytest
import time
from decimal import Decimal


class TestRiskStatus:
    """Test risk status checks."""
    
    def test_ok_by_default(self):
        from src.risk.manager import RiskManager, RiskStatus
        
        risk = RiskManager()
        check = risk.check()
        
        assert check.status == RiskStatus.OK
        print("✓ Default status is OK")
    
    def test_kill_switch(self):
        from src.risk.manager import RiskManager, RiskStatus
        
        risk = RiskManager()
        
        risk.kill_switch("Test stop")
        check = risk.check()
        
        assert check.status == RiskStatus.STOP
        assert "Test stop" in check.reason
        assert risk.is_killed
        
        print("✓ Kill switch works")
    
    def test_reset_kill_switch(self):
        from src.risk.manager import RiskManager, RiskStatus
        
        risk = RiskManager()
        
        risk.kill_switch("Test")
        assert risk.is_killed
        
        risk.reset_kill_switch()
        assert not risk.is_killed
        
        check = risk.check()
        assert check.status == RiskStatus.OK
        
        print("✓ Kill switch reset works")


class TestEnforceMode:
    """Test enforce vs data-gathering mode."""
    
    def test_enforce_true_stops(self):
        from src.risk.manager import RiskManager, RiskStatus
        
        risk = RiskManager(max_daily_loss=Decimal("50"), enforce=True)
        
        # Record a big loss
        risk.record_trade("t1", "SELL", Decimal("0.50"), Decimal("10"), 
                         realized_pnl=Decimal("-60"))
        
        check = risk.check()
        
        assert check.status == RiskStatus.STOP
        print("✓ Enforce=True stops trading")
    
    def test_enforce_false_continues(self):
        from src.risk.manager import RiskManager, RiskStatus
        
        risk = RiskManager(max_daily_loss=Decimal("50"), enforce=False)
        
        # Record a big loss
        risk.record_trade("t1", "SELL", Decimal("0.50"), Decimal("10"), 
                         realized_pnl=Decimal("-60"))
        
        check = risk.check()
        
        # Should return OK even though limit exceeded
        assert check.status == RiskStatus.OK
        
        # But event should be logged
        events = risk.get_risk_events()
        assert len(events) == 1
        assert events[0].status == "STOP"
        assert events[0].enforced == False
        
        print("✓ Enforce=False continues trading but logs event")
    
    def test_kill_switch_always_enforced(self):
        from src.risk.manager import RiskManager, RiskStatus
        
        # Even with enforce=False, manual kill switch works
        risk = RiskManager(enforce=False)
        
        risk.kill_switch("Emergency")
        check = risk.check()
        
        assert check.status == RiskStatus.STOP
        print("✓ Kill switch always enforced")


class TestRiskEventLogging:
    """Test risk event logging for data gathering."""
    
    def test_events_logged(self):
        from src.risk.manager import RiskManager
        
        risk = RiskManager(
            max_daily_loss=Decimal("50"),
            max_position=Decimal("30"),
            enforce=False
        )
        
        # Trigger multiple events
        risk.record_trade("t1", "BUY", Decimal("0.50"), Decimal("10"),
                         realized_pnl=Decimal("-45"))  # Warning
        risk.check(["t1"])
        
        risk.record_trade("t1", "BUY", Decimal("0.50"), Decimal("10"),
                         realized_pnl=Decimal("-20"))  # Stop (exceeded)
        risk.check(["t1"])
        
        events = risk.get_risk_events()
        assert len(events) >= 2
        
        summary = risk.get_risk_event_summary()
        assert summary["total_events"] >= 2
        assert summary["non_enforced_events"] >= 2
        
        print(f"✓ Risk events logged: {summary}")
    
    def test_event_details_captured(self):
        from src.risk.manager import RiskManager
        
        risk = RiskManager(max_daily_loss=Decimal("50"), enforce=False)
        
        risk.record_trade("t1", "SELL", Decimal("0.50"), Decimal("10"),
                         realized_pnl=Decimal("-60"))
        risk.check()
        
        events = risk.get_risk_events()
        event = events[0]
        
        assert event.status == "STOP"
        assert "loss" in event.reason.lower()
        assert "daily_pnl" in event.details
        assert event.enforced == False
        assert event.timestamp > 0
        
        print("✓ Event details captured correctly")


class TestDailyLoss:
    """Test daily loss limit."""
    
    def test_loss_limit_stop(self):
        from src.risk.manager import RiskManager, RiskStatus
        
        risk = RiskManager(max_daily_loss=Decimal("50"), enforce=True)
        
        # Record a big loss
        risk.record_trade("t1", "SELL", Decimal("0.50"), Decimal("10"), 
                         realized_pnl=Decimal("-60"))
        
        check = risk.check()
        
        assert check.status == RiskStatus.STOP
        assert "loss limit" in check.reason.lower()
        
        print("✓ Daily loss limit triggers stop")
    
    def test_loss_warning(self):
        from src.risk.manager import RiskManager, RiskStatus
        
        risk = RiskManager(max_daily_loss=Decimal("50"), enforce=True)
        
        # Record loss at 80% of limit
        risk.record_trade("t1", "SELL", Decimal("0.50"), Decimal("10"),
                         realized_pnl=Decimal("-42"))
        
        check = risk.check()
        
        assert check.status == RiskStatus.WARN
        
        print("✓ Approaching loss limit triggers warning")
    
    def test_reset_daily_pnl(self):
        from src.risk.manager import RiskManager, RiskStatus
        
        risk = RiskManager(max_daily_loss=Decimal("50"))
        
        risk.record_trade("t1", "SELL", Decimal("0.50"), Decimal("10"),
                         realized_pnl=Decimal("-30"))
        
        assert risk.daily_pnl == Decimal("-30")
        
        risk.reset_daily_pnl()
        
        assert risk.daily_pnl == Decimal("0")
        
        print("✓ Daily P&L reset works")


class TestErrorRate:
    """Test error rate limiting."""
    
    def test_error_cooldown(self):
        from src.risk.manager import RiskManager, RiskStatus
        
        risk = RiskManager(max_errors_per_minute=3, error_cooldown=5, enforce=True)
        
        # Record enough errors
        for i in range(5):
            risk.record_error(f"Error {i}")
        
        check = risk.check()
        
        assert check.status == RiskStatus.STOP
        assert "error" in check.reason.lower() or "cooldown" in check.reason.lower()
        
        print("✓ Error rate triggers cooldown")


class TestPositionLimits:
    """Test position limit checks."""
    
    def test_position_warning(self):
        from src.risk.manager import RiskManager, RiskStatus
        from src.simulator import get_simulator, reset_simulator
        from src.models import OrderSide
        from src.config import DRY_RUN
        
        if not DRY_RUN:
            pytest.skip("Requires DRY_RUN=true")
        
        reset_simulator()
        sim = get_simulator()
        
        # Build up a large position
        order = sim.create_order("t1", OrderSide.BUY, Decimal("0.50"), Decimal("150"))
        sim.check_fills("t1", Decimal("0.45"), Decimal("0.50"))
        
        risk = RiskManager(max_position=Decimal("100"), enforce=True)
        check = risk.check(["t1"])
        
        assert check.status == RiskStatus.WARN
        assert "position" in check.reason.lower()
        
        print("✓ Position limit triggers warning")


class TestGetStatus:
    """Test status reporting."""
    
    def test_get_status(self):
        from src.risk.manager import RiskManager
        
        risk = RiskManager(max_daily_loss=Decimal("100"), enforce=False)
        
        risk.record_trade("t1", "BUY", Decimal("0.50"), Decimal("10"),
                         realized_pnl=Decimal("-20"))
        risk.record_error("Test error")
        risk.check()  # Log an event
        
        status = risk.get_status()
        
        assert "mode" in status
        assert status["mode"] == "DATA_GATHER"
        assert "killed" in status
        assert "daily_pnl" in status
        assert "errors_last_minute" in status
        assert "risk_events_logged" in status
        
        assert status["daily_pnl"] == -20.0
        assert status["errors_last_minute"] >= 1
        
        print(f"✓ Status: {status}")


class TestGlobalInstance:
    """Test global risk manager."""
    
    def test_global_instance(self):
        from src.risk.manager import get_risk_manager, reset_risk_manager
        
        reset_risk_manager()
        
        rm1 = get_risk_manager()
        rm2 = get_risk_manager()
        
        assert rm1 is rm2  # Same instance
        
        reset_risk_manager()
        rm3 = get_risk_manager()
        
        assert rm3 is not rm1  # New instance after reset
        
        print("✓ Global instance works")


class TestIntegration:
    """Integration tests."""
    
    def test_data_gathering_workflow(self):
        """Test full data gathering workflow in non-enforce mode."""
        from src.risk.manager import RiskManager, RiskStatus
        from src.simulator import reset_simulator
        from src.config import DRY_RUN
        
        if not DRY_RUN:
            pytest.skip("Requires DRY_RUN=true")
        
        reset_simulator()
        
        # Data gathering mode - don't enforce limits
        risk = RiskManager(
            max_daily_loss=Decimal("50"),
            max_position=Decimal("50"),
            enforce=False
        )
        
        # Simulate a full trading session with big losses
        trades = [
            ("t1", "BUY", Decimal("10")),
            ("t1", "SELL", Decimal("-20")),  # loss
            ("t1", "BUY", Decimal("-15")),   # loss
            ("t1", "SELL", Decimal("-30")),  # loss - exceeds limit
            ("t1", "BUY", Decimal("-25")),   # more loss
        ]
        
        for token, side, pnl in trades:
            risk.record_trade(token, side, Decimal("0.50"), Decimal("10"),
                            realized_pnl=pnl)
            check = risk.check([token])
            # Should always return OK in data gather mode
            assert check.status == RiskStatus.OK
        
        # Total P&L should be tracked
        assert risk.daily_pnl == Decimal("-80")  # 10 - 20 - 15 - 30 - 25
        
        # Events should be logged
        events = risk.get_risk_events()
        assert len(events) > 0
        
        summary = risk.get_risk_event_summary()
        print(f"  Total events: {summary['total_events']}")
        print(f"  Stop events: {summary['stop_events']}")
        print(f"  Warn events: {summary['warn_events']}")
        print(f"  Final P&L: {risk.daily_pnl}")
        
        # All events should be non-enforced
        assert summary["enforced_events"] == 0
        
        print("✓ Data gathering workflow works")
```

---

## File Structure After Phase 8

```
polymarket-bot/
├── src/
│   ├── risk/
│   │   ├── __init__.py
│   │   └── manager.py         # RiskManager class
│   ├── strategy/
│   │   ├── market_maker.py    # Updated with risk checks
│   │   └── runner.py
│   └── ...
│
├── tests/
│   └── test_phase8.py         # ~12 tests
│
└── .env                       # + RISK_* settings
```

---

## Verification

```bash
# Run tests
pytest tests/test_phase8.py -v

# Run bot with risk controls
python run_mm.py
```

---

## What It Does

### Data Gathering Mode (DRY_RUN=true, default)

```
$ python run_mm.py

...
2024-01-15 10:30:00 INFO RiskManager initialized: enforce=False
2024-01-15 10:30:05 INFO Mid: 0.65 -> Bid: 0.63, Ask: 0.67
2024-01-15 10:30:05 INFO [DRY RUN] Order: BUY 10 @ 0.63
2024-01-15 10:30:05 INFO [DRY RUN] Order: SELL 10 @ 0.67
2024-01-15 10:30:35 INFO Status: Mode=DATA_GATHER | PnL=+5.00 (5% of limit) | Events=0
2024-01-15 10:31:05 INFO Status: Mode=DATA_GATHER | PnL=-12.00 (12% of limit) | Events=0
...
2024-01-15 10:45:00 WARNING [DATA MODE] Risk event (not enforced): WARN - Approaching daily loss limit: -42.00
2024-01-15 10:45:30 INFO Status: Mode=DATA_GATHER | PnL=-42.00 (84% of limit) | Events=1
...
2024-01-15 10:50:00 WARNING [DATA MODE] Risk event (not enforced): STOP - Daily loss limit exceeded: -55.00
2024-01-15 10:50:05 INFO Status: Mode=DATA_GATHER | PnL=-55.00 (110% of limit) | Events=2
...
# Trading CONTINUES - gathering data about what happens after limit exceeded
...
2024-01-15 11:30:00 INFO Status: Mode=DATA_GATHER | PnL=-23.00 (46% of limit) | Events=5
# Price recovered! Would have missed this if we stopped at -55

^C
2024-01-15 11:35:00 INFO Shutting down...
2024-01-15 11:35:00 INFO Risk Event Summary:
2024-01-15 11:35:00 INFO   Total events: 5
2024-01-15 11:35:00 INFO   STOP events: 2 (not enforced)
2024-01-15 11:35:00 INFO   WARN events: 3 (not enforced)
2024-01-15 11:35:00 INFO   Final P&L: -23.00
```

### Enforcement Mode (DRY_RUN=false or RISK_ENFORCE=true)

```
$ DRY_RUN=false python run_mm.py

...
2024-01-15 10:30:00 INFO RiskManager initialized: enforce=True
...
2024-01-15 10:45:00 WARNING Risk warning: Approaching daily loss limit: -42.00
2024-01-15 10:50:00 ERROR Risk stop: Daily loss limit exceeded: -55.00
2024-01-15 10:50:00 CRITICAL KILL SWITCH: Daily loss limit exceeded: -55.00
2024-01-15 10:50:00 INFO Cancelling all orders...
2024-01-15 10:50:00 INFO Market maker stopped.
```

---

## Configuration Guide

| Setting | Default | What It Does |
|---------|---------|--------------|
| `RISK_ENFORCE` | false (dry-run) / true (live) | Whether to actually stop trading on limits |
| `RISK_MAX_DAILY_LOSS` | 50 | Log/stop if daily loss exceeds this |
| `RISK_MAX_POSITION` | 100 | Log/warn if position in any token exceeds this |
| `RISK_MAX_TOTAL_EXPOSURE` | 500 | Log/warn if total exposure exceeds this |
| `RISK_ERROR_COOLDOWN` | 60 | Seconds to pause after too many errors |
| `RISK_MAX_ERRORS_PER_MINUTE` | 5 | Number of errors that triggers cooldown |

### Mode Behavior

| Mode | RISK_ENFORCE | Behavior |
|------|--------------|----------|
| Data Gathering | false (default in dry-run) | Log events, continue trading, collect data |
| Enforcement | true (default in live) | Stop trading when limits hit |

**Recommended workflow:**
1. Run in dry-run with `RISK_ENFORCE=false` (default) to gather data
2. Analyze risk events: "How often would rails trigger?"
3. Tune limits based on data
4. Switch to live with `RISK_ENFORCE=true` (automatic)

---

## Next: Phase 9

Live testing with real (tiny) orders!

But first - make sure Phases 6, 7, and 8 all work in dry-run mode. Run the bot, watch it place simulated orders, see risk events get logged.

When ready for Phase 9:
- Switch `DRY_RUN=false` (this automatically sets `RISK_ENFORCE=true`)
- Use TINY sizes ($5-10)
- Watch closely
- Be ready to Ctrl+C

---

## Analyzing Collected Data

After a dry-run session, analyze the risk events:

```python
# In Python or a notebook:
from src.risk import get_risk_manager

risk = get_risk_manager()

# Get all events
events = risk.get_risk_events()
for e in events:
    print(f"{e.timestamp}: {e.status} - {e.reason}")

# Summary
summary = risk.get_risk_event_summary()
print(f"Total events: {summary['total_events']}")
print(f"Would have stopped {summary['stop_events']} times")
print(f"Final P&L: {risk.daily_pnl}")

# Questions to answer:
# 1. How often would rails have stopped me?
# 2. Did P&L recover after "stop" events?
# 3. Are my limits too tight or too loose?
```

**Key insight:** If P&L often recovered after STOP events, your limits might be too tight. If it kept getting worse, your limits saved you.
