"""TDD Tests for Trade Logging."""

import pytest
import json
from pathlib import Path
from decimal import Decimal
from src.telemetry.trade_logger import TradeLogger


class TestTradeLogger:
    """Test trade logging."""

    @pytest.fixture
    def logger(self, tmp_path):
        log_file = tmp_path / "trades.jsonl"
        return TradeLogger(log_file=str(log_file))

    @pytest.fixture
    def log_file(self, tmp_path):
        return tmp_path / "trades.jsonl"

    def test_log_trade(self, logger, log_file):
        """Log trade to file."""
        logger.log_trade(
            market_id="m1",
            side="BUY",
            price=Decimal("0.50"),
            size=Decimal("10"),
            fill_type="maker",
        )

        lines = log_file.read_text().strip().split("\n")
        trade = json.loads(lines[0])

        assert trade["market_id"] == "m1"
        assert trade["side"] == "BUY"
        assert trade["price"] == "0.50"
        assert trade["fill_type"] == "maker"

    def test_log_includes_timestamp(self, logger, log_file):
        """Logged trades include timestamp."""
        logger.log_trade("m1", "BUY", Decimal("0.50"), Decimal("10"))

        trade = json.loads(log_file.read_text().strip())
        assert "timestamp" in trade

    def test_log_quote(self, logger, log_file):
        """Log quote updates."""
        logger.log_quote(
            market_id="m1",
            bid_price=Decimal("0.48"),
            ask_price=Decimal("0.52"),
            bid_size=Decimal("10"),
            ask_size=Decimal("10"),
        )

        record = json.loads(log_file.read_text().strip())
        assert record["type"] == "quote"
        assert record["bid_price"] == "0.48"
        assert record["ask_price"] == "0.52"

    def test_log_event(self, logger, log_file):
        """Log general events."""
        logger.log_event("strategy_change", reason="volatility spike", new_spread="0.06")

        record = json.loads(log_file.read_text().strip())
        assert record["type"] == "strategy_change"
        assert record["reason"] == "volatility spike"

    def test_multiple_records(self, logger, log_file):
        """Multiple records are written as JSONL."""
        logger.log_trade("m1", "BUY", Decimal("0.50"), Decimal("10"))
        logger.log_trade("m1", "SELL", Decimal("0.55"), Decimal("10"))

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2

        trade1 = json.loads(lines[0])
        trade2 = json.loads(lines[1])
        assert trade1["side"] == "BUY"
        assert trade2["side"] == "SELL"

    def test_extra_fields(self, logger, log_file):
        """Extra fields are included."""
        logger.log_trade(
            market_id="m1",
            side="BUY",
            price=Decimal("0.50"),
            size=Decimal("10"),
            custom_field="custom_value",
        )

        trade = json.loads(log_file.read_text().strip())
        assert trade["custom_field"] == "custom_value"
