"""Tests for EventTracker module."""

import time
import pytest

from src.alpha.events import EventTracker, EventType, MarketEvent, EventSignal


class TestMarketEvent:
    """Tests for MarketEvent dataclass."""

    def test_create_event(self):
        """Test creating a market event."""
        now = time.time()
        event = MarketEvent(
            event_type=EventType.NEWS_CATALYST,
            market_id="market-123",
            timestamp=now,
            description="Breaking news about market outcome",
            impact_estimate=0.5,
            confidence=0.8,
            expires_at=now + 3600,
        )
        assert event.event_type == EventType.NEWS_CATALYST
        assert event.market_id == "market-123"
        assert event.impact_estimate == 0.5
        assert event.confidence == 0.8


class TestEventSignal:
    """Tests for EventSignal dataclass."""

    def test_create_signal(self):
        """Test creating an event signal."""
        signal = EventSignal(
            should_trade=True,
            direction="LONG",
            strength=0.7,
            reason="Strong bullish signal",
            spread_multiplier=1.2,
            size_multiplier=0.8,
        )
        assert signal.should_trade is True
        assert signal.direction == "LONG"
        assert signal.strength == 0.7


class TestEventTracker:
    """Tests for EventTracker class."""

    def test_init(self):
        """Test tracker initialization."""
        tracker = EventTracker()
        assert tracker._events == {}
        assert tracker._market_metadata == {}

    def test_add_event(self):
        """Test adding events to tracker."""
        tracker = EventTracker()
        now = time.time()

        event = MarketEvent(
            event_type=EventType.VOLUME_SPIKE,
            market_id="market-123",
            timestamp=now,
            description="Unusual volume detected",
            impact_estimate=0.3,
            confidence=0.6,
            expires_at=now + 3600,
        )

        tracker.add_event(event)

        events = tracker.get_events("market-123")
        assert len(events) == 1
        assert events[0].event_type == EventType.VOLUME_SPIKE

    def test_add_multiple_events_same_market(self):
        """Test adding multiple events to the same market."""
        tracker = EventTracker()
        now = time.time()

        event1 = MarketEvent(
            event_type=EventType.NEWS_CATALYST,
            market_id="market-123",
            timestamp=now,
            description="News 1",
            impact_estimate=0.3,
            confidence=0.6,
            expires_at=now + 3600,
        )
        event2 = MarketEvent(
            event_type=EventType.POLL_RELEASE,
            market_id="market-123",
            timestamp=now,
            description="Poll released",
            impact_estimate=0.5,
            confidence=0.8,
            expires_at=now + 7200,
        )

        tracker.add_event(event1)
        tracker.add_event(event2)

        events = tracker.get_events("market-123")
        assert len(events) == 2

    def test_set_market_metadata(self):
        """Test setting market metadata."""
        tracker = EventTracker()
        metadata = {"resolution_time": time.time() + 86400}

        tracker.set_market_metadata("market-123", metadata)

        assert tracker._market_metadata["market-123"] == metadata

    def test_get_signal_no_events(self):
        """Test getting signal when no events exist."""
        tracker = EventTracker()

        signal = tracker.get_signal("market-123")

        assert signal.should_trade is True
        assert signal.direction == "NEUTRAL"
        assert signal.strength == 0.0
        assert signal.reason == "No active events"
        assert signal.spread_multiplier == 1.0
        assert signal.size_multiplier == 1.0

    def test_get_signal_resolution_approaching(self):
        """Test signal when resolution is approaching."""
        tracker = EventTracker()
        now = time.time()

        # Resolution in 12 hours (within 24-hour warning window)
        tracker.set_market_metadata("market-123", {
            "resolution_time": now + (12 * 3600)
        })

        signal = tracker.get_signal("market-123")

        assert signal.should_trade is True  # Still tradeable (> 1 hour)
        assert signal.direction == "NEUTRAL"
        assert signal.spread_multiplier > 1.5  # Widened spread
        assert signal.size_multiplier < 1.0  # Reduced size

    def test_get_signal_resolution_imminent(self):
        """Test signal when resolution is imminent (< 1 hour)."""
        tracker = EventTracker()
        now = time.time()

        # Resolution in 30 minutes
        tracker.set_market_metadata("market-123", {
            "resolution_time": now + (0.5 * 3600)
        })

        signal = tracker.get_signal("market-123")

        assert signal.should_trade is False  # Stop trading in last hour
        assert signal.direction == "NEUTRAL"

    def test_get_signal_bullish_events(self):
        """Test signal with bullish events."""
        tracker = EventTracker()
        now = time.time()

        event = MarketEvent(
            event_type=EventType.NEWS_CATALYST,
            market_id="market-123",
            timestamp=now,
            description="Strong positive news",
            impact_estimate=0.6,  # Bullish
            confidence=0.9,  # High confidence
            expires_at=now + 3600,
        )

        tracker.add_event(event)
        signal = tracker.get_signal("market-123")

        assert signal.should_trade is True
        assert signal.direction == "LONG"
        assert signal.strength > 0

    def test_get_signal_bearish_events(self):
        """Test signal with bearish events."""
        tracker = EventTracker()
        now = time.time()

        event = MarketEvent(
            event_type=EventType.NEWS_CATALYST,
            market_id="market-123",
            timestamp=now,
            description="Strong negative news",
            impact_estimate=-0.6,  # Bearish
            confidence=0.9,  # High confidence
            expires_at=now + 3600,
        )

        tracker.add_event(event)
        signal = tracker.get_signal("market-123")

        assert signal.should_trade is True
        assert signal.direction == "SHORT"
        assert signal.strength > 0

    def test_get_signal_low_confidence(self):
        """Test signal with low confidence events stays neutral."""
        tracker = EventTracker()
        now = time.time()

        event = MarketEvent(
            event_type=EventType.NEWS_CATALYST,
            market_id="market-123",
            timestamp=now,
            description="Uncertain news",
            impact_estimate=0.6,  # Would be bullish
            confidence=0.3,  # But low confidence
            expires_at=now + 3600,
        )

        tracker.add_event(event)
        signal = tracker.get_signal("market-123")

        # Should stay neutral due to low confidence
        assert signal.direction == "NEUTRAL"

    def test_expired_events_ignored(self):
        """Test that expired events are ignored in signal calculation."""
        tracker = EventTracker()
        now = time.time()

        # Add expired event
        event = MarketEvent(
            event_type=EventType.NEWS_CATALYST,
            market_id="market-123",
            timestamp=now - 7200,
            description="Old news",
            impact_estimate=0.8,
            confidence=0.9,
            expires_at=now - 3600,  # Expired 1 hour ago
        )

        tracker.add_event(event)
        signal = tracker.get_signal("market-123")

        # Should be neutral as event is expired
        assert signal.direction == "NEUTRAL"
        assert signal.reason == "No active events"

    def test_clear_expired_events(self):
        """Test clearing expired events."""
        tracker = EventTracker()
        now = time.time()

        # Add expired event
        expired = MarketEvent(
            event_type=EventType.NEWS_CATALYST,
            market_id="market-123",
            timestamp=now - 7200,
            description="Old news",
            impact_estimate=0.8,
            confidence=0.9,
            expires_at=now - 3600,
        )

        # Add active event
        active = MarketEvent(
            event_type=EventType.VOLUME_SPIKE,
            market_id="market-123",
            timestamp=now,
            description="Current volume",
            impact_estimate=0.3,
            confidence=0.6,
            expires_at=now + 3600,
        )

        tracker.add_event(expired)
        tracker.add_event(active)

        # Should have 2 events before clearing
        assert len(tracker.get_events("market-123")) == 2

        # Clear expired
        removed = tracker.clear_expired_events()

        assert removed == 1
        assert len(tracker.get_events("market-123")) == 1
        assert tracker.get_events("market-123")[0].event_type == EventType.VOLUME_SPIKE


class TestEventType:
    """Tests for EventType enum."""

    def test_all_event_types(self):
        """Test all event types are defined."""
        assert EventType.RESOLUTION_APPROACHING.value == "resolution_approaching"
        assert EventType.NEWS_CATALYST.value == "news_catalyst"
        assert EventType.VOLUME_SPIKE.value == "volume_spike"
        assert EventType.DEADLINE.value == "deadline"
        assert EventType.POLL_RELEASE.value == "poll_release"
