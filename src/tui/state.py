"""
Centralized bot state for TUI rendering.

Collects data from all components into a single snapshot.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class BotMode(Enum):
    """Bot operating mode."""
    DRY_RUN = "DRY_RUN"
    LIVE = "LIVE"


class BotStatus(Enum):
    """Bot running status."""
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    ERROR = "ERROR"


@dataclass
class MarketState:
    """Current market data snapshot."""
    token_id: str
    market_question: str = ""
    best_bid: Optional[Decimal] = None
    best_ask: Optional[Decimal] = None
    midpoint: Optional[Decimal] = None
    spread: Optional[Decimal] = None
    spread_bps: Optional[float] = None  # Spread in basis points
    last_update: Optional[datetime] = None


@dataclass
class OrderState:
    """Active order state."""
    order_id: str
    side: str  # "BUY" or "SELL"
    price: Decimal
    size: Decimal
    filled: Decimal = Decimal("0")
    status: str = "LIVE"

    @property
    def remaining(self) -> Decimal:
        return self.size - self.filled

    @property
    def fill_pct(self) -> float:
        if self.size == 0:
            return 0.0
        return float(self.filled / self.size * 100)


@dataclass
class PositionState:
    """Position and P&L state."""
    token_id: str
    position: Decimal = Decimal("0")
    entry_price: Optional[Decimal] = None
    current_price: Optional[Decimal] = None
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")

    @property
    def total_pnl(self) -> Decimal:
        return self.unrealized_pnl + self.realized_pnl

    @property
    def position_value(self) -> Decimal:
        if self.current_price is None:
            return Decimal("0")
        return self.position * self.current_price


@dataclass
class RiskState:
    """Risk manager state."""
    daily_pnl: Decimal = Decimal("0")
    daily_loss_limit: Decimal = Decimal("100")
    position_limit: Decimal = Decimal("1000")
    current_position: Decimal = Decimal("0")
    error_count: int = 0
    kill_switch_active: bool = False
    risk_status: str = "OK"  # OK, WARNING, STOP
    enforce_mode: bool = False

    @property
    def loss_pct(self) -> float:
        """Percentage of daily loss limit used."""
        if self.daily_loss_limit == 0:
            return 0.0
        return float(abs(min(self.daily_pnl, Decimal("0"))) / self.daily_loss_limit * 100)

    @property
    def position_pct(self) -> float:
        """Percentage of position limit used."""
        if self.position_limit == 0:
            return 0.0
        return float(abs(self.current_position) / self.position_limit * 100)


@dataclass
class FeedState:
    """Market feed state."""
    status: str = "STOPPED"  # STOPPED, STARTING, RUNNING, ERROR
    data_source: str = "none"  # websocket, rest, none
    is_healthy: bool = False
    last_message_ago: float = 0.0  # Seconds since last message
    reconnect_count: int = 0


@dataclass
class SmartMMState:
    """Smart market maker state (optional, for SmartMarketMaker only)."""
    # Spread dynamics
    base_spread: Decimal = Decimal("0.04")
    vol_multiplier: float = 1.0
    inv_multiplier: float = 1.0
    final_spread: Decimal = Decimal("0.04")

    # Volatility
    volatility_level: str = "UNKNOWN"  # LOW, NORMAL, HIGH, EXTREME
    realized_vol: float = 0.0

    # Inventory
    inventory_pct: float = 0.0
    inventory_level: str = "NEUTRAL"  # NEUTRAL, LONG, SHORT, MAX_LONG, MAX_SHORT
    bid_skew: Decimal = Decimal("0")
    ask_skew: Decimal = Decimal("0")

    # Book imbalance
    imbalance_signal: str = "BALANCED"  # BID_HEAVY, ASK_HEAVY, BALANCED
    imbalance_adjustment: Decimal = Decimal("0")

    # P&L
    unrealized_pnl: Decimal = Decimal("0")
    vwap_entry: Optional[Decimal] = None

    @property
    def spread_description(self) -> str:
        """Human-readable spread description."""
        parts = []
        if self.vol_multiplier != 1.0:
            parts.append(f"vol:{self.vol_multiplier:.1f}x")
        if self.inv_multiplier != 1.0:
            parts.append(f"inv:{self.inv_multiplier:.1f}x")
        if not parts:
            return "base"
        return " ".join(parts)


@dataclass
class TradeRecord:
    """Recent trade record."""
    timestamp: datetime
    side: str
    price: Decimal
    size: Decimal
    pnl: Optional[Decimal] = None
    is_simulated: bool = False


@dataclass
class BotState:
    """
    Complete bot state snapshot for TUI rendering.

    Collected from all components each render cycle.
    """
    # Bot info
    mode: BotMode = BotMode.DRY_RUN
    status: BotStatus = BotStatus.STOPPED
    uptime_seconds: float = 0.0
    start_time: Optional[datetime] = None

    # Market
    market: Optional[MarketState] = None

    # Orders
    bid_order: Optional[OrderState] = None
    ask_order: Optional[OrderState] = None
    open_order_count: int = 0

    # Position & P&L
    position: Optional[PositionState] = None

    # Risk
    risk: RiskState = field(default_factory=RiskState)

    # Feed
    feed: FeedState = field(default_factory=FeedState)

    # Smart MM state (None if using SimpleMarketMaker)
    smart_mm: Optional[SmartMMState] = None

    # Recent activity
    recent_trades: List[TradeRecord] = field(default_factory=list)
    recent_errors: List[str] = field(default_factory=list)

    # Stats
    total_trades: int = 0
    total_volume: Decimal = Decimal("0")
    quotes_placed: int = 0
    quotes_cancelled: int = 0

    # Timestamps
    last_quote_time: Optional[datetime] = None
    last_fill_time: Optional[datetime] = None
    snapshot_time: datetime = field(default_factory=datetime.now)

    def update_uptime(self):
        """Update uptime based on start time."""
        if self.start_time:
            delta = datetime.now() - self.start_time
            self.uptime_seconds = delta.total_seconds()
