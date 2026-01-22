"""
TDD Tests for Fill WebSocket

Tests WebSocket subscription for order fills.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from src.feed.fill_feed import FillFeed, FillEvent


class TestFillSubscription:
    """Test fill subscription."""

    @pytest.fixture
    def feed(self):
        return FillFeed()

    @pytest.mark.asyncio
    async def test_connect_to_fill_stream(self, feed):
        """Connect to fill WebSocket."""
        async def mock_connect():
            feed._connected = True

        with patch.object(feed, '_connect', side_effect=mock_connect):
            await feed.start()
            assert feed.is_connected

    @pytest.mark.asyncio
    async def test_receive_fill_event(self, feed):
        """Receive and parse fill event."""
        callback = Mock()
        feed.on_fill(callback)

        # Simulate incoming fill
        fill_data = {
            "type": "trade",
            "order_id": "order-123",
            "price": "0.55",
            "size": "10",
            "side": "BUY",
        }

        feed._handle_message(fill_data)

        callback.assert_called_once()
        event = callback.call_args[0][0]
        assert event.order_id == "order-123"


class TestFillEventParsing:
    """Test fill event parsing."""

    def test_parse_fill_event(self):
        """Parse fill from WebSocket message."""
        data = {
            "type": "trade",
            "order_id": "order-123",
            "price": "0.55",
            "size": "10",
            "side": "BUY",
            "timestamp": 1234567890,
        }

        event = FillEvent.from_ws_message(data)

        assert event.order_id == "order-123"
        assert event.price == pytest.approx(0.55)
        assert event.size == pytest.approx(10)
        assert event.side == "BUY"
