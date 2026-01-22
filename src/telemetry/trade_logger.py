"""Structured Trade Logging to JSONL."""

import json
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional


class TradeLogger:
    """
    Logs trades and events to JSONL file for analysis.

    JSONL format allows easy streaming and analysis with tools like jq.

    Usage:
        logger = TradeLogger(log_file="trades.jsonl")

        logger.log_trade(
            market_id="abc123",
            side="BUY",
            price=Decimal("0.50"),
            size=Decimal("10"),
        )

        # Analyze with: cat trades.jsonl | jq 'select(.side=="BUY")'
    """

    def __init__(self, log_file: str = "trades.jsonl"):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def _write_record(self, record: dict[str, Any]) -> None:
        """Write a record to the log file."""
        # Convert any Decimal values to strings for JSON serialization
        serializable = {
            k: str(v) if isinstance(v, Decimal) else v
            for k, v in record.items()
        }
        with open(self.log_file, "a") as f:
            f.write(json.dumps(serializable) + "\n")

    def log_trade(
        self,
        market_id: str,
        side: str,
        price: Decimal,
        size: Decimal,
        fill_type: str = "unknown",
        order_id: Optional[str] = None,
        **extra: Any,
    ) -> None:
        """
        Log a trade execution.

        Args:
            market_id: Market identifier
            side: "BUY" or "SELL"
            price: Execution price
            size: Number of contracts
            fill_type: "maker" or "taker"
            order_id: Optional order ID
            **extra: Additional fields to include
        """
        record = {
            "timestamp": time.time(),
            "type": "trade",
            "market_id": market_id,
            "side": side,
            "price": str(price),
            "size": str(size),
            "fill_type": fill_type,
            "order_id": order_id,
            **extra,
        }
        self._write_record(record)

    def log_quote(
        self,
        market_id: str,
        bid_price: Decimal,
        ask_price: Decimal,
        bid_size: Decimal,
        ask_size: Decimal,
        **extra: Any,
    ) -> None:
        """
        Log a quote update.

        Args:
            market_id: Market identifier
            bid_price: Bid price
            ask_price: Ask price
            bid_size: Bid size
            ask_size: Ask size
            **extra: Additional fields
        """
        record = {
            "timestamp": time.time(),
            "type": "quote",
            "market_id": market_id,
            "bid_price": str(bid_price),
            "ask_price": str(ask_price),
            "bid_size": str(bid_size),
            "ask_size": str(ask_size),
            **extra,
        }
        self._write_record(record)

    def log_event(self, event_type: str, **data: Any) -> None:
        """
        Log a general event.

        Args:
            event_type: Type of event (e.g., "strategy_change", "error")
            **data: Event-specific data
        """
        record = {
            "timestamp": time.time(),
            "type": event_type,
            **data,
        }
        self._write_record(record)
