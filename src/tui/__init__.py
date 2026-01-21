"""
TUI package for market maker bot.

Provides terminal user interface for monitoring bot status,
positions, P&L, and risk metrics in real-time.
"""

from src.tui.state import (
    BotState,
    BotMode,
    BotStatus,
    MarketState,
    OrderState,
    PositionState,
    RiskState,
    FeedState,
    TradeRecord
)
from src.tui.collector import StateCollector, get_collector, reset_collector
from src.tui.renderer import TUIRenderer
from src.tui.runner import TUIBotRunner, run_with_tui

__all__ = [
    # State
    "BotState",
    "BotMode",
    "BotStatus",
    "MarketState",
    "OrderState",
    "PositionState",
    "RiskState",
    "FeedState",
    "TradeRecord",

    # Collector
    "StateCollector",
    "get_collector",
    "reset_collector",

    # Renderer
    "TUIRenderer",

    # Runner
    "TUIBotRunner",
    "run_with_tui"
]
