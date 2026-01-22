"""
State collector for TUI.

Gathers data from all bot components into a BotState snapshot.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from src.tui.state import (
    BotState, BotMode, BotStatus,
    MarketState, OrderState, PositionState,
    RiskState, FeedState, TradeRecord, SmartMMState
)
from src.config import DRY_RUN
from src.feed import FeedState as FeedStateEnum


class StateCollector:
    """
    Collects state from bot components.

    Usage:
        collector = StateCollector()
        collector.set_feed(feed)
        collector.set_risk_manager(risk_manager)
        collector.set_market_maker(market_maker)

        # In render loop:
        state = collector.collect()
    """

    def __init__(self):
        self._feed = None
        self._risk_manager = None
        self._market_maker = None
        self._simulator = None
        self._start_time: Optional[datetime] = None
        self._status = BotStatus.STOPPED

        # Counters
        self._quotes_placed = 0
        self._quotes_cancelled = 0

        # Market info
        self._market_question = ""
        self._token_id = ""

    def set_feed(self, feed):
        """Set the market feed instance."""
        self._feed = feed

    def set_risk_manager(self, risk_manager):
        """Set the risk manager instance."""
        self._risk_manager = risk_manager

    def set_market_maker(self, market_maker):
        """Set the market maker instance."""
        self._market_maker = market_maker

    def set_simulator(self, simulator):
        """Set the order simulator instance."""
        self._simulator = simulator

    def set_market_info(self, token_id: str, question: str = ""):
        """Set market identification info."""
        self._token_id = token_id
        self._market_question = question

    def set_status(self, status: BotStatus):
        """Set bot status."""
        self._status = status
        if status == BotStatus.RUNNING and self._start_time is None:
            self._start_time = datetime.now()

    def record_quote_placed(self):
        """Record a quote was placed."""
        self._quotes_placed += 1

    def record_quote_cancelled(self):
        """Record a quote was cancelled."""
        self._quotes_cancelled += 1

    def collect(self) -> BotState:
        """
        Collect current state from all components.

        Returns:
            BotState snapshot for rendering.
        """
        state = BotState(
            mode=BotMode.DRY_RUN if DRY_RUN else BotMode.LIVE,
            status=self._status,
            start_time=self._start_time,
            quotes_placed=self._quotes_placed,
            quotes_cancelled=self._quotes_cancelled,
            snapshot_time=datetime.now()
        )

        state.update_uptime()

        # Collect from feed
        if self._feed:
            state.market = self._collect_market_state()
            state.feed = self._collect_feed_state()

        # Collect from risk manager
        if self._risk_manager:
            state.risk = self._collect_risk_state()

        # Collect from market maker
        if self._market_maker:
            state.bid_order, state.ask_order = self._collect_order_state()
            state.smart_mm = self._collect_smart_mm_state()

        # Collect from simulator
        if self._simulator:
            state.position = self._collect_position_state()
            state.recent_trades = self._collect_recent_trades()
            state.total_trades = len(self._simulator.trades)
            state.total_volume = self._calculate_total_volume()

        return state

    def _collect_market_state(self) -> Optional[MarketState]:
        """Collect market data from feed."""
        if not self._feed or not self._token_id:
            return None

        try:
            best_bid = self._feed.get_best_bid(self._token_id)
            best_ask = self._feed.get_best_ask(self._token_id)
            midpoint = self._feed.get_midpoint(self._token_id)

            spread = None
            spread_bps = None
            if best_bid is not None and best_ask is not None:
                spread = Decimal(str(best_ask)) - Decimal(str(best_bid))
                if midpoint and midpoint > 0:
                    spread_bps = float(spread / Decimal(str(midpoint)) * 10000)

            return MarketState(
                token_id=self._token_id,
                market_question=self._market_question[:60] + "..." if len(self._market_question) > 60 else self._market_question,
                best_bid=Decimal(str(best_bid)) if best_bid else None,
                best_ask=Decimal(str(best_ask)) if best_ask else None,
                midpoint=Decimal(str(midpoint)) if midpoint else None,
                spread=spread,
                spread_bps=spread_bps,
                last_update=datetime.now()
            )
        except Exception:
            return None

    def _collect_feed_state(self) -> FeedState:
        """Collect feed health state."""
        if not self._feed:
            return FeedState()

        try:
            feed_state = self._feed.state
            status_map = {
                FeedStateEnum.STOPPED: "STOPPED",
                FeedStateEnum.STARTING: "STARTING",
                FeedStateEnum.RUNNING: "RUNNING",
                FeedStateEnum.ERROR: "ERROR",
            }

            last_msg_ago = 0.0
            if hasattr(self._feed, '_data_store'):
                last_msg_ago = self._feed._data_store.seconds_since_any_message()

            return FeedState(
                status=status_map.get(feed_state, "UNKNOWN"),
                data_source=getattr(self._feed, '_data_source', 'unknown'),
                is_healthy=self._feed.is_healthy,
                last_message_ago=last_msg_ago if last_msg_ago != float('inf') else 999,
                reconnect_count=getattr(self._feed, '_reconnect_count', 0)
            )
        except Exception:
            return FeedState(status="ERROR")

    def _collect_risk_state(self) -> RiskState:
        """Collect risk manager state."""
        if not self._risk_manager:
            return RiskState()

        try:
            rm = self._risk_manager
            status_map = {
                0: "OK",      # RiskStatus.OK
                1: "WARNING", # RiskStatus.WARNING
                2: "STOP",    # RiskStatus.STOP
            }

            return RiskState(
                daily_pnl=rm.daily_pnl,
                daily_loss_limit=rm.max_daily_loss,
                position_limit=rm.max_position,
                current_position=Decimal("0"),  # Updated below
                error_count=len(rm._errors),
                kill_switch_active=rm.is_killed,
                risk_status=status_map.get(rm._last_status.value if hasattr(rm, '_last_status') else 0, "OK"),
                enforce_mode=rm.enforce
            )
        except Exception:
            return RiskState()

    def _collect_order_state(self) -> tuple:
        """Collect active order state from market maker."""
        bid_order = None
        ask_order = None

        if not self._market_maker:
            return bid_order, ask_order

        try:
            mm = self._market_maker

            if hasattr(mm, 'bid_order') and mm.bid_order and mm.bid_order.is_live:
                o = mm.bid_order
                bid_order = OrderState(
                    order_id=o.id[:12] + "...",
                    side="BUY",
                    price=o.price,
                    size=o.size,
                    filled=o.filled,
                    status=o.status.value
                )

            if hasattr(mm, 'ask_order') and mm.ask_order and mm.ask_order.is_live:
                o = mm.ask_order
                ask_order = OrderState(
                    order_id=o.id[:12] + "...",
                    side="SELL",
                    price=o.price,
                    size=o.size,
                    filled=o.filled,
                    status=o.status.value
                )
        except Exception:
            pass

        return bid_order, ask_order

    def _collect_smart_mm_state(self) -> Optional[SmartMMState]:
        """Collect SmartMarketMaker state if available."""
        if not self._market_maker:
            return None

        try:
            mm = self._market_maker
            # Check if this is a SmartMarketMaker with _last_state
            if not hasattr(mm, '_last_state') or mm._last_state is None:
                return None

            s = mm._last_state
            return SmartMMState(
                base_spread=s.base_spread,
                vol_multiplier=s.vol_multiplier,
                inv_multiplier=s.inv_multiplier,
                final_spread=s.final_spread,
                volatility_level=s.volatility_level,
                realized_vol=s.realized_vol,
                inventory_pct=s.inventory_pct,
                inventory_level=s.inventory_level,
                bid_skew=s.bid_skew,
                ask_skew=s.ask_skew,
                imbalance_signal=s.imbalance_signal,
                imbalance_adjustment=s.imbalance_adjustment,
                unrealized_pnl=s.unrealized_pnl,
                vwap_entry=s.vwap_entry,
            )
        except Exception:
            return None

    def _collect_position_state(self) -> Optional[PositionState]:
        """Collect position and P&L from simulator."""
        if not self._simulator or not self._token_id:
            return None

        try:
            sim = self._simulator
            position = sim.get_position(self._token_id)

            pnl_data = sim.get_pnl(self._token_id,
                                   self._feed.get_midpoint(self._token_id) if self._feed else Decimal("0.5"))

            return PositionState(
                token_id=self._token_id,
                position=position,
                entry_price=pnl_data.get('avg_entry_price'),
                current_price=pnl_data.get('current_price'),
                unrealized_pnl=pnl_data.get('unrealized_pnl', Decimal("0")),
                realized_pnl=pnl_data.get('realized_pnl', Decimal("0"))
            )
        except Exception:
            return PositionState(token_id=self._token_id)

    def _collect_recent_trades(self, limit: int = 5) -> List[TradeRecord]:
        """Collect recent trades from simulator."""
        if not self._simulator:
            return []

        try:
            trades = self._simulator.get_trades(self._token_id)[-limit:]
            return [
                TradeRecord(
                    timestamp=datetime.now(),  # Ideally parse from trade.timestamp
                    side=t.side.value,
                    price=t.price,
                    size=t.size,
                    is_simulated=t.is_simulated
                )
                for t in trades
            ]
        except Exception:
            return []

    def _calculate_total_volume(self) -> Decimal:
        """Calculate total traded volume."""
        if not self._simulator:
            return Decimal("0")

        try:
            return sum((t.size * t.price for t in self._simulator.trades), Decimal("0"))
        except Exception:
            return Decimal("0")


# Global collector instance
_collector: Optional[StateCollector] = None


def get_collector() -> StateCollector:
    """Get or create global state collector."""
    global _collector
    if _collector is None:
        _collector = StateCollector()
    return _collector


def reset_collector():
    """Reset the global collector."""
    global _collector
    _collector = None
