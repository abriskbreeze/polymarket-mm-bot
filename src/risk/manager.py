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
        pnl_check = self._check_daily_pnl()
        if pnl_check.status == RiskStatus.STOP:
            return pnl_check

        # Check positions
        pos_check = RiskCheck(RiskStatus.OK)
        if token_ids:
            pos_check = self._check_positions(token_ids)
            if pos_check.status == RiskStatus.STOP:
                return pos_check

        # Return worst of P&L and position checks
        # Priority: STOP > WARN > OK
        if pnl_check.status == RiskStatus.WARN or pos_check.status == RiskStatus.WARN:
            # Return the WARN check (prefer P&L warning if both)
            if pnl_check.status == RiskStatus.WARN:
                return pnl_check
            return pos_check

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
        realized_pnl: Optional[Decimal] = None,
        fee: Decimal = Decimal("0")
    ):
        """
        Record a trade for P&L tracking.

        Args:
            token_id: Token traded
            side: BUY or SELL
            price: Execution price
            size: Trade size
            realized_pnl: Pre-calculated P&L (if available)
            fee: Transaction fee (subtracted from P&L)
        """
        self._trades.append({
            "time": time.time(),
            "token_id": token_id,
            "side": side,
            "price": float(price),
            "size": float(size),
            "fee": float(fee),
        })

        if realized_pnl is not None:
            # Subtract fee from realized P&L
            net_pnl = realized_pnl - fee
            self._daily_pnl += net_pnl
            logger.info(f"P&L update: {net_pnl:+.2f} (gross: {realized_pnl:+.2f}, fee: {fee:.2f}, daily: {self._daily_pnl:+.2f})")
        elif fee > 0:
            # If no realized_pnl but we have a fee, just deduct fee
            self._daily_pnl -= fee
            logger.info(f"Fee deducted: {fee:.2f} (daily: {self._daily_pnl:+.2f})")

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
