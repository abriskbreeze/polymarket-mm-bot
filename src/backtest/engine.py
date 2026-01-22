"""
Backtest Engine

Replays historical data to evaluate strategy performance.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Callable
from enum import Enum
import uuid
import statistics

from src.backtest.data import HistoricalData, OrderBookSnapshot

class OrderStatus(Enum):
    OPEN = "open"
    FILLED = "filled"
    CANCELLED = "cancelled"

@dataclass
class BacktestOrder:
    """Order in backtest."""
    id: str
    side: str
    price: Decimal
    size: Decimal
    status: OrderStatus = OrderStatus.OPEN
    fill_price: Optional[Decimal] = None
    fill_time: Optional[int] = None

    @property
    def is_filled(self) -> bool:
        return self.status == OrderStatus.FILLED

@dataclass
class BacktestResult:
    """Result of backtest run."""
    initial_capital: Decimal
    final_capital: Decimal
    total_return: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    sharpe_ratio: float
    max_drawdown: float
    profit_factor: float

class BacktestEngine:
    """
    Backtesting engine for strategy evaluation.

    Usage:
        engine = BacktestEngine(initial_capital=Decimal("1000"))

        data = HistoricalData()
        data.load_from_file("data.csv")

        result = engine.run(data, strategy="smart_mm")
        print(result.sharpe_ratio)
    """

    def __init__(self, initial_capital: Decimal = Decimal("1000")):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position = Decimal("0")
        self.realized_pnl = Decimal("0")
        self._avg_entry_price = Decimal("0")

        self._orders: Dict[str, BacktestOrder] = {}
        self._trades: List[dict] = []
        self._equity_curve: List[Decimal] = [initial_capital]

    def run(
        self,
        data: HistoricalData,
        strategy: str = "simple_mm",
        strategy_fn: Optional[Callable] = None,
    ) -> BacktestResult:
        """
        Run backtest on historical data.

        Args:
            data: Historical order book data
            strategy: Strategy name or "custom"
            strategy_fn: Custom strategy function

        Returns:
            BacktestResult with performance metrics
        """
        for snapshot in data.iterate():
            # Check for fills
            self._check_fills(snapshot)

            # Run strategy
            if strategy_fn:
                strategy_fn(self, snapshot)
            else:
                self._run_default_strategy(snapshot)

            # Update equity curve
            unrealized = self._calculate_unrealized(snapshot)
            self._equity_curve.append(self.capital + unrealized)

        return self._build_result()

    def place_order(
        self,
        side: str,
        price: Decimal,
        size: Decimal,
    ) -> str:
        """Place an order."""
        order_id = str(uuid.uuid4())[:8]
        order = BacktestOrder(
            id=order_id,
            side=side.upper(),
            price=price,
            size=size,
        )
        self._orders[order_id] = order
        return order_id

    def cancel_order(self, order_id: str):
        """Cancel an order."""
        if order_id in self._orders:
            self._orders[order_id].status = OrderStatus.CANCELLED

    def get_order(self, order_id: str) -> Optional[BacktestOrder]:
        """Get order by ID."""
        return self._orders.get(order_id)

    def process_snapshot(self, snapshot: OrderBookSnapshot):
        """Process a single snapshot (for testing)."""
        self._check_fills(snapshot)

    def generate_report(self) -> dict:
        """Generate performance report as dict."""
        result = self._build_result()
        return {
            "total_return": result.total_return,
            "sharpe_ratio": result.sharpe_ratio,
            "max_drawdown": result.max_drawdown,
            "win_rate": result.win_rate,
            "total_trades": result.total_trades,
            "profit_factor": result.profit_factor,
            "initial_capital": result.initial_capital,
            "final_capital": result.final_capital,
        }

    def _build_result(self) -> BacktestResult:
        """Build BacktestResult from current state."""
        final = self._equity_curve[-1] if self._equity_curve else self.initial_capital
        total_return = float((final - self.initial_capital) / self.initial_capital)

        wins = [t for t in self._trades if t["pnl"] > 0]
        losses = [t for t in self._trades if t["pnl"] < 0]

        win_rate = len(wins) / max(1, len(self._trades))
        sharpe = self._calculate_sharpe()
        max_dd = self._calculate_max_drawdown()
        profit_factor = self._calculate_profit_factor()

        return BacktestResult(
            initial_capital=self.initial_capital,
            final_capital=final,
            total_return=total_return,
            total_trades=len(self._trades),
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate=win_rate,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            profit_factor=profit_factor,
        )

    def _check_fills(self, snapshot: OrderBookSnapshot):
        """Check if any orders should fill."""
        for order_id, order in self._orders.items():
            if order.status != OrderStatus.OPEN:
                continue

            filled = False
            fill_price = Decimal("0")

            if order.side == "BUY":
                # Buy fills if ask <= our bid
                if snapshot.best_ask <= order.price:
                    filled = True
                    fill_price = order.price

            else:  # SELL
                # Sell fills if bid >= our ask
                if snapshot.best_bid >= order.price:
                    filled = True
                    fill_price = order.price

            if filled:
                order.status = OrderStatus.FILLED
                order.fill_price = fill_price
                order.fill_time = snapshot.timestamp

                self._process_fill(order, snapshot)

    def _process_fill(self, order: BacktestOrder, snapshot: OrderBookSnapshot):
        """Process a filled order."""
        pnl = Decimal("0")
        fill_price = order.fill_price or order.price  # Fallback to order price

        if order.side == "BUY":
            new_position = self.position + order.size

            # Track entry price for P&L calculation
            if self.position <= 0:
                # Opening or flipping to long
                self._avg_entry_price = fill_price
            elif new_position != 0:
                # Averaging into existing long
                total_cost = self._avg_entry_price * self.position + fill_price * order.size
                self._avg_entry_price = total_cost / new_position

            self.position = new_position
            self.capital -= order.size * fill_price
        else:
            # SELL
            new_position = self.position - order.size

            # Realize P&L if closing long position
            if self.position > 0:
                close_size = min(order.size, self.position)
                pnl = (fill_price - self._avg_entry_price) * close_size
                self.realized_pnl += pnl

            self.position = new_position
            self.capital += order.size * fill_price

            # If flipping to short or closing, reset entry
            if self.position <= 0:
                self._avg_entry_price = fill_price if self.position < 0 else Decimal("0")

        # Record trade
        self._trades.append({
            "order_id": order.id,
            "side": order.side,
            "price": order.fill_price,
            "size": order.size,
            "timestamp": order.fill_time,
            "pnl": pnl,
        })

    def _calculate_unrealized(self, snapshot: OrderBookSnapshot) -> Decimal:
        """Calculate unrealized P&L."""
        if self.position == 0:
            return Decimal("0")

        mid = (snapshot.best_bid + snapshot.best_ask) / 2
        return (mid - self._avg_entry_price) * self.position

    def _calculate_sharpe(self) -> float:
        """Calculate Sharpe ratio."""
        if len(self._equity_curve) < 2:
            return 0.0

        returns = []
        for i in range(1, len(self._equity_curve)):
            ret = (self._equity_curve[i] - self._equity_curve[i-1]) / self._equity_curve[i-1]
            returns.append(float(ret))

        if not returns:
            return 0.0

        try:
            mean = statistics.mean(returns)
            std = statistics.stdev(returns) if len(returns) > 1 else 1
            return (mean / std) * (252 ** 0.5) if std > 0 else 0  # Annualized
        except Exception:
            return 0.0

    def _calculate_max_drawdown(self) -> float:
        """Calculate maximum drawdown."""
        if not self._equity_curve:
            return 0.0

        peak = self._equity_curve[0]
        max_dd = 0.0

        for value in self._equity_curve:
            if value > peak:
                peak = value
            dd = float((peak - value) / peak)
            max_dd = max(max_dd, dd)

        return max_dd

    def _calculate_profit_factor(self) -> float:
        """Calculate profit factor."""
        gross_profit = sum(t["pnl"] for t in self._trades if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in self._trades if t["pnl"] < 0))

        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0
        return float(gross_profit / gross_loss)

    def _run_default_strategy(self, snapshot: OrderBookSnapshot):
        """Default simple MM strategy for testing."""
        # Cancel existing open orders
        for order_id, order in list(self._orders.items()):
            if order.status == OrderStatus.OPEN:
                self.cancel_order(order_id)

        # Place orders at market prices (aggressive - will fill on next price movement)
        # BUY at best_ask (crossing the spread to ensure fills)
        # SELL at best_bid (crossing the spread to ensure fills)
        self.place_order("BUY", snapshot.best_ask, Decimal("10"))
        self.place_order("SELL", snapshot.best_bid, Decimal("10"))
