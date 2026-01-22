"""
Event Intelligence

Tracks market events and generates trading signals.

Event Types:
- Resolution approaching: Market about to resolve
- News catalyst: Relevant news for market outcome
- Volume spike: Unusual activity suggesting informed trading
- Deadline: Hard deadline for market resolution
"""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class EventType(Enum):
    RESOLUTION_APPROACHING = "resolution_approaching"
    NEWS_CATALYST = "news_catalyst"
    VOLUME_SPIKE = "volume_spike"
    DEADLINE = "deadline"
    POLL_RELEASE = "poll_release"  # For political markets


@dataclass
class MarketEvent:
    """A market-relevant event."""

    event_type: EventType
    market_id: str
    timestamp: float
    description: str
    impact_estimate: float  # -1.0 to +1.0 (bearish to bullish)
    confidence: float  # 0.0 to 1.0
    expires_at: float  # When signal becomes stale


@dataclass
class EventSignal:
    """Trading signal from event analysis."""

    should_trade: bool
    direction: str  # "LONG", "SHORT", "NEUTRAL"
    strength: float  # 0.0 to 1.0
    reason: str
    spread_multiplier: float  # Widen spread near events
    size_multiplier: float  # Reduce size near events


class EventTracker:
    """
    Tracks events and generates trading signals.

    Usage:
        tracker = EventTracker()

        # Register events
        tracker.add_event(MarketEvent(...))

        # Get signal for a market
        signal = tracker.get_signal(market_id)
    """

    # Time thresholds
    RESOLUTION_WARNING_HOURS = 24
    HIGH_CONFIDENCE_THRESHOLD = 0.7

    def __init__(self) -> None:
        self._events: Dict[str, List[MarketEvent]] = {}
        self._market_metadata: Dict[str, dict] = {}

    def set_market_metadata(self, market_id: str, metadata: dict) -> None:
        """Set market metadata including resolution time."""
        self._market_metadata[market_id] = metadata

    def add_event(self, event: MarketEvent) -> None:
        """Add an event to tracking."""
        if event.market_id not in self._events:
            self._events[event.market_id] = []
        self._events[event.market_id].append(event)

    def get_events(self, market_id: str) -> List[MarketEvent]:
        """Get all events for a market."""
        return self._events.get(market_id, [])

    def clear_expired_events(self) -> int:
        """Remove expired events from all markets. Returns count removed."""
        now = time.time()
        removed = 0
        for market_id in list(self._events.keys()):
            original_count = len(self._events[market_id])
            self._events[market_id] = [
                e for e in self._events[market_id] if e.expires_at > now
            ]
            removed += original_count - len(self._events[market_id])
            # Clean up empty lists
            if not self._events[market_id]:
                del self._events[market_id]
        return removed

    def get_signal(self, market_id: str) -> EventSignal:
        """Get trading signal for a market based on events."""
        now = time.time()
        events = self._events.get(market_id, [])
        metadata = self._market_metadata.get(market_id, {})

        # Filter active events
        active_events = [e for e in events if e.expires_at > now]

        # Check resolution proximity
        resolution_time = metadata.get("resolution_time")
        hours_to_resolution: Optional[float] = None
        if resolution_time:
            hours_to_resolution = (resolution_time - now) / 3600

        # Default: neutral
        if not active_events and (
            hours_to_resolution is None
            or hours_to_resolution > self.RESOLUTION_WARNING_HOURS
        ):
            return EventSignal(
                should_trade=True,
                direction="NEUTRAL",
                strength=0.0,
                reason="No active events",
                spread_multiplier=1.0,
                size_multiplier=1.0,
            )

        # Resolution approaching - reduce exposure
        if (
            hours_to_resolution is not None
            and hours_to_resolution < self.RESOLUTION_WARNING_HOURS
        ):
            hours_factor = hours_to_resolution / self.RESOLUTION_WARNING_HOURS
            return EventSignal(
                should_trade=hours_to_resolution > 1,  # Stop trading last hour
                direction="NEUTRAL",
                strength=0.0,
                reason=f"Resolution in {hours_to_resolution:.1f} hours",
                spread_multiplier=1.5 + (1 - hours_factor),  # Up to 2.5x spread
                size_multiplier=max(0.2, hours_factor),  # Down to 20% size
            )

        # Aggregate event signals
        total_impact = 0.0
        total_confidence = 0.0

        for event in active_events:
            weight = event.confidence
            total_impact += event.impact_estimate * weight
            total_confidence += weight

        if total_confidence > 0:
            avg_impact = total_impact / total_confidence
            avg_confidence = total_confidence / len(active_events)
        else:
            avg_impact = 0.0
            avg_confidence = 0.0

        # Determine direction
        if avg_impact > 0.2 and avg_confidence > self.HIGH_CONFIDENCE_THRESHOLD:
            direction = "LONG"
        elif avg_impact < -0.2 and avg_confidence > self.HIGH_CONFIDENCE_THRESHOLD:
            direction = "SHORT"
        else:
            direction = "NEUTRAL"

        return EventSignal(
            should_trade=True,
            direction=direction,
            strength=abs(avg_impact) * avg_confidence,
            reason=f"{len(active_events)} active events",
            spread_multiplier=1.0 + (1 - avg_confidence) * 0.5,  # Widen on uncertainty
            size_multiplier=avg_confidence,  # Reduce on uncertainty
        )
