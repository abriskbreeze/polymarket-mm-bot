"""
TUI renderer using rich library.

Renders BotState to terminal with live updates.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.style import Style
from rich import box

from src.tui.state import BotState, BotStatus, BotMode


class TUIRenderer:
    """
    Renders bot state to terminal.

    Usage:
        renderer = TUIRenderer()

        with renderer.live_context():
            while running:
                state = collector.collect()
                renderer.update(state)
                await asyncio.sleep(0.5)
    """

    def __init__(self, refresh_rate: float = 4.0):
        self.console = Console()
        self.refresh_rate = refresh_rate
        self._live: Optional[Live] = None

    def live_context(self) -> Live:
        """Get live display context manager."""
        self._live = Live(
            self._render_empty(),
            console=self.console,
            refresh_per_second=self.refresh_rate,
            screen=True
        )
        return self._live

    def stop(self):
        """Stop the live display immediately."""
        if self._live:
            self._live.stop()
            self._live = None

    def update(self, state: BotState):
        """Update display with new state."""
        if self._live:
            self._live.update(self._render(state))

    def _render_empty(self) -> Panel:
        """Render empty/loading state."""
        return Panel(
            Text("Starting...", style="dim"),
            title="[bold blue]Polymarket MM Bot[/]",
            border_style="blue"
        )

    def _render(self, state: BotState) -> Layout:
        """Render complete dashboard."""
        layout = Layout()

        # Create main sections
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3)
        )

        # Body split into left and right
        layout["body"].split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=1)
        )

        # Left side: market + orders + trades
        layout["left"].split_column(
            Layout(name="market", size=8),
            Layout(name="orders", size=10),
            Layout(name="trades")
        )

        # Right side: position + risk + feed
        layout["right"].split_column(
            Layout(name="position", size=10),
            Layout(name="risk", size=10),
            Layout(name="feed")
        )

        # Render each section
        layout["header"].update(self._render_header(state))
        layout["market"].update(self._render_market(state))
        layout["orders"].update(self._render_orders(state))
        layout["trades"].update(self._render_trades(state))
        layout["position"].update(self._render_position(state))
        layout["risk"].update(self._render_risk(state))
        layout["feed"].update(self._render_feed(state))
        layout["footer"].update(self._render_footer(state))

        return layout

    def _render_header(self, state: BotState) -> Panel:
        """Render header with bot status."""
        # Status color
        status_colors = {
            BotStatus.STOPPED: "red",
            BotStatus.STARTING: "yellow",
            BotStatus.RUNNING: "green",
            BotStatus.PAUSED: "yellow",
            BotStatus.ERROR: "red bold"
        }
        status_color = status_colors.get(state.status, "white")

        # Mode badge
        mode_style = "cyan" if state.mode == BotMode.DRY_RUN else "red bold"
        mode_text = f"[{mode_style}]{state.mode.value}[/]"

        # Uptime
        hours = int(state.uptime_seconds // 3600)
        minutes = int((state.uptime_seconds % 3600) // 60)
        seconds = int(state.uptime_seconds % 60)
        uptime = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        header = Text()
        header.append("◉ ", style=status_color)
        header.append(state.status.value, style=status_color)
        header.append("  │  ", style="dim")
        header.append_text(Text.from_markup(mode_text))
        header.append("  │  ", style="dim")
        header.append(f"⏱ {uptime}", style="dim")

        return Panel(
            header,
            title="[bold blue]🤖 Polymarket Market Maker[/]",
            border_style="blue"
        )

    def _render_market(self, state: BotState) -> Panel:
        """Render market data panel with smart MM metrics if available."""
        if not state.market:
            return Panel(
                Text("No market data", style="dim"),
                title="[bold]📊 Market[/]",
                border_style="dim"
            )

        m = state.market

        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        table.add_column("Label", style="dim")
        table.add_column("Value", justify="right")

        # Market question
        table.add_row("Market", Text(m.market_question, style="bold"))
        table.add_row("", "")

        # Prices
        bid_style = "green" if m.best_bid else "dim"
        ask_style = "red" if m.best_ask else "dim"
        mid_style = "yellow" if m.midpoint else "dim"

        table.add_row("Best Bid", Text(f"${m.best_bid:.4f}" if m.best_bid else "—", style=bid_style))
        table.add_row("Best Ask", Text(f"${m.best_ask:.4f}" if m.best_ask else "—", style=ask_style))
        table.add_row("Midpoint", Text(f"${m.midpoint:.4f}" if m.midpoint else "—", style=mid_style))
        table.add_row("Spread", Text(f"${m.spread:.4f} ({m.spread_bps:.1f} bps)" if m.spread else "—", style="cyan"))

        # Smart MM metrics (if available)
        if state.smart_mm:
            s = state.smart_mm
            table.add_row("", "")

            # Dynamic spread
            spread_info = f"${s.final_spread:.3f}"
            if s.vol_multiplier != 1.0 or s.inv_multiplier != 1.0:
                spread_info += f" ({s.spread_description})"
            table.add_row("Our Spread", Text(spread_info, style="cyan bold"))

            # Volatility indicator
            vol_styles = {"LOW": "green", "NORMAL": "blue", "HIGH": "yellow", "EXTREME": "red bold"}
            vol_style = vol_styles.get(s.volatility_level, "dim")
            vol_text = f"{s.volatility_level} ({s.realized_vol:.1%})" if s.realized_vol > 0 else s.volatility_level
            table.add_row("Volatility", Text(vol_text, style=vol_style))

            # Imbalance arrow
            imbal_styles = {"BID_HEAVY": ("green", "↑"), "ASK_HEAVY": ("red", "↓"), "BALANCED": ("dim", "=")}
            imbal_style, imbal_icon = imbal_styles.get(s.imbalance_signal, ("dim", "?"))
            table.add_row("Imbalance", Text(f"{imbal_icon} {s.imbalance_signal}", style=imbal_style))

            # Inventory
            inv_styles = {"NEUTRAL": "blue", "LONG": "green", "SHORT": "red", "MAX_LONG": "green bold", "MAX_SHORT": "red bold"}
            inv_style = inv_styles.get(s.inventory_level, "dim")
            inv_text = f"{s.inventory_level} ({s.inventory_pct:+.0f}%)"
            table.add_row("Inventory", Text(inv_text, style=inv_style))

            # Skews
            if s.bid_skew != 0 or s.ask_skew != 0:
                skew_text = f"bid:{s.bid_skew:+.3f} ask:{s.ask_skew:+.3f}"
                table.add_row("Skew", Text(skew_text, style="yellow"))

        return Panel(
            table,
            title="[bold]📊 Market[/]" + (" [cyan](SMART)[/]" if state.smart_mm else ""),
            border_style="blue"
        )

    def _render_orders(self, state: BotState) -> Panel:
        """Render active orders panel."""
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold")
        table.add_column("Side", width=6)
        table.add_column("Price", justify="right", width=10)
        table.add_column("Size", justify="right", width=10)
        table.add_column("Filled", justify="right", width=10)
        table.add_column("Status", width=10)

        if state.bid_order:
            o = state.bid_order
            table.add_row(
                Text("BUY", style="green bold"),
                f"${o.price:.4f}",
                f"{o.size:.2f}",
                f"{o.filled:.2f} ({o.fill_pct:.0f}%)",
                Text(o.status, style="green" if o.status == "LIVE" else "dim")
            )
        else:
            table.add_row(
                Text("BUY", style="dim"),
                "—", "—", "—",
                Text("NONE", style="dim")
            )

        if state.ask_order:
            o = state.ask_order
            table.add_row(
                Text("SELL", style="red bold"),
                f"${o.price:.4f}",
                f"{o.size:.2f}",
                f"{o.filled:.2f} ({o.fill_pct:.0f}%)",
                Text(o.status, style="green" if o.status == "LIVE" else "dim")
            )
        else:
            table.add_row(
                Text("SELL", style="dim"),
                "—", "—", "—",
                Text("NONE", style="dim")
            )

        subtitle = f"Placed: {state.quotes_placed} │ Cancelled: {state.quotes_cancelled}"

        return Panel(
            table,
            title="[bold]📝 Active Orders[/]",
            subtitle=subtitle,
            border_style="blue"
        )

    def _render_trades(self, state: BotState) -> Panel:
        """Render recent trades panel."""
        if not state.recent_trades:
            return Panel(
                Text("No trades yet", style="dim"),
                title="[bold]💰 Recent Trades[/]",
                border_style="dim"
            )

        table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
        table.add_column("Time", width=8)
        table.add_column("Side", width=6)
        table.add_column("Price", justify="right", width=10)
        table.add_column("Size", justify="right", width=8)

        for trade in reversed(state.recent_trades[-5:]):
            side_style = "green" if trade.side == "BUY" else "red"
            table.add_row(
                trade.timestamp.strftime("%H:%M:%S"),
                Text(trade.side, style=side_style),
                f"${trade.price:.4f}",
                f"{trade.size:.2f}"
            )

        return Panel(
            table,
            title=f"[bold]💰 Recent Trades[/] ({state.total_trades} total)",
            border_style="blue"
        )

    def _render_position(self, state: BotState) -> Panel:
        """Render position and P&L panel."""
        if not state.position:
            return Panel(
                Text("No position", style="dim"),
                title="[bold]💼 Position & P&L[/]",
                border_style="dim"
            )

        p = state.position

        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        table.add_column("Label", style="dim")
        table.add_column("Value", justify="right")

        # Position
        pos_style = "green" if p.position > 0 else ("red" if p.position < 0 else "dim")
        pos_text = f"{p.position:+.2f}" if p.position != 0 else "0.00"
        table.add_row("Position", Text(pos_text, style=pos_style))

        # Entry price
        if p.entry_price:
            table.add_row("Avg Entry", f"${p.entry_price:.4f}")

        # P&L
        table.add_row("", "")

        unreal_style = "green" if p.unrealized_pnl > 0 else ("red" if p.unrealized_pnl < 0 else "dim")
        table.add_row("Unrealized", Text(f"${p.unrealized_pnl:+.2f}", style=unreal_style))

        real_style = "green" if p.realized_pnl > 0 else ("red" if p.realized_pnl < 0 else "dim")
        table.add_row("Realized", Text(f"${p.realized_pnl:+.2f}", style=real_style))

        total_style = "green bold" if p.total_pnl > 0 else ("red bold" if p.total_pnl < 0 else "dim")
        table.add_row("Total P&L", Text(f"${p.total_pnl:+.2f}", style=total_style))

        return Panel(
            table,
            title="[bold]💼 Position & P&L[/]",
            border_style="green" if p.total_pnl >= 0 else "red"
        )

    def _render_risk(self, state: BotState) -> Panel:
        """Render risk status panel."""
        r = state.risk

        # Status indicator
        status_styles = {
            "OK": ("green", "✓"),
            "WARNING": ("yellow", "⚠"),
            "STOP": ("red bold", "✗")
        }
        status_style, status_icon = status_styles.get(r.risk_status, ("dim", "?"))

        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        table.add_column("Label", style="dim")
        table.add_column("Value", justify="right")

        # Status
        table.add_row("Status", Text(f"{status_icon} {r.risk_status}", style=status_style))
        table.add_row("Mode", Text("ENFORCE" if r.enforce_mode else "DATA_GATHER", style="yellow" if r.enforce_mode else "cyan"))

        table.add_row("", "")

        # Daily P&L with limit
        pnl_style = "green" if r.daily_pnl >= 0 else "red"
        table.add_row("Daily P&L", Text(f"${r.daily_pnl:+.2f} / ${r.daily_loss_limit:.0f}", style=pnl_style))

        # Progress bar for loss
        loss_bar = self._progress_bar(r.loss_pct, width=15, danger_threshold=80)
        table.add_row("Loss Used", loss_bar)

        table.add_row("", "")

        # Position limit
        table.add_row("Position", f"{abs(r.current_position):.0f} / {r.position_limit:.0f}")
        pos_bar = self._progress_bar(r.position_pct, width=15, danger_threshold=90)
        table.add_row("Pos Used", pos_bar)

        # Kill switch
        table.add_row("", "")
        ks_style = "red bold blink" if r.kill_switch_active else "green"
        ks_text = "🔴 ACTIVE" if r.kill_switch_active else "🟢 OFF"
        table.add_row("Kill Switch", Text(ks_text, style=ks_style))

        border = "red" if r.kill_switch_active or r.risk_status == "STOP" else ("yellow" if r.risk_status == "WARNING" else "blue")

        return Panel(
            table,
            title="[bold]⚠️ Risk[/]",
            border_style=border
        )

    def _render_feed(self, state: BotState) -> Panel:
        """Render feed health panel."""
        f = state.feed

        # Status color
        status_styles = {
            "STOPPED": "red",
            "STARTING": "yellow",
            "RUNNING": "green",
            "ERROR": "red bold"
        }
        status_style = status_styles.get(f.status, "dim")

        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        table.add_column("Label", style="dim")
        table.add_column("Value", justify="right")

        table.add_row("Status", Text(f.status, style=status_style))
        table.add_row("Source", Text(f.data_source.upper(), style="cyan"))
        table.add_row("Healthy", Text("✓ Yes" if f.is_healthy else "✗ No", style="green" if f.is_healthy else "red"))

        # Last message
        if f.last_message_ago < 999:
            msg_style = "green" if f.last_message_ago < 5 else ("yellow" if f.last_message_ago < 30 else "red")
            table.add_row("Last Msg", Text(f"{f.last_message_ago:.1f}s ago", style=msg_style))
        else:
            table.add_row("Last Msg", Text("—", style="dim"))

        if f.reconnect_count > 0:
            table.add_row("Reconnects", Text(str(f.reconnect_count), style="yellow"))

        border = "green" if f.is_healthy else ("yellow" if f.status == "STARTING" else "red")

        return Panel(
            table,
            title="[bold]📡 Feed[/]",
            border_style=border
        )

    def _render_footer(self, state: BotState) -> Panel:
        """Render footer with stats and controls."""
        stats = Text()
        stats.append(f"Volume: ${state.total_volume:.2f}", style="dim")
        stats.append("  │  ", style="dim")
        stats.append(f"Trades: {state.total_trades}", style="dim")
        stats.append("  │  ", style="dim")
        stats.append(f"Updated: {state.snapshot_time.strftime('%H:%M:%S')}", style="dim")
        stats.append("  │  ", style="dim")
        stats.append("Press Ctrl+C to exit", style="dim italic")

        return Panel(stats, border_style="dim")

    def _progress_bar(self, percent: float, width: int = 20, danger_threshold: float = 80) -> Text:
        """Create a text-based progress bar."""
        percent = min(max(percent, 0), 100)
        filled = int(width * percent / 100)
        empty = width - filled

        if percent >= danger_threshold:
            style = "red"
        elif percent >= danger_threshold * 0.7:
            style = "yellow"
        else:
            style = "green"

        bar = Text()
        bar.append("█" * filled, style=style)
        bar.append("░" * empty, style="dim")
        bar.append(f" {percent:.0f}%", style=style)

        return bar
