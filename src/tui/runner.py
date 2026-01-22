"""
TUI-enabled bot runner.

Runs the market maker with live TUI display.
"""

import asyncio
import signal
from decimal import Decimal
from typing import Optional

from src.tui.state import BotStatus
from src.tui.collector import StateCollector, get_collector
from src.tui.renderer import TUIRenderer
from src.config import DRY_RUN
from src.feed import MarketFeed
from src.risk.manager import RiskManager, get_risk_manager
from src.strategy.market_maker import SimpleMarketMaker, SmartMarketMaker
from src.simulator import get_simulator
from src.utils import setup_logging

logger = setup_logging()


class TUIBotRunner:
    """
    Runs market maker with TUI display.

    Usage:
        runner = TUIBotRunner(token_id="...", market_question="...")
        await runner.run()
    """

    def __init__(
        self,
        token_id: str,
        market_question: str = "",
        spread: float = 0.02,
        size: float = 10.0,
        position_limit: float = 100.0,
        update_interval: float = 0.5,
        use_smart_mm: bool = False,
    ):
        self.token_id = token_id
        self.market_question = market_question
        self.spread = spread
        self.size = size
        self.position_limit = position_limit
        self.update_interval = update_interval
        self.use_smart_mm = use_smart_mm

        # Components
        self.feed: Optional[MarketFeed] = None
        self.market_maker = None  # SimpleMarketMaker or SmartMarketMaker
        self.risk_manager: Optional[RiskManager] = None
        self.collector: Optional[StateCollector] = None
        self.renderer: Optional[TUIRenderer] = None

        # Control
        self._shutdown_event = asyncio.Event()
        self._loop = None

    def _handle_signal(self):
        """Handle shutdown signal."""
        logger.info("Received shutdown signal (Ctrl+C)")
        self._shutdown_event.set()
        # Context manager will handle Live cleanup when loop exits

    async def run(self):
        """Main run loop with TUI."""
        logger.info("Starting TUI bot runner...")

        # Initialize components
        self._init_components()

        # Start renderer
        self.renderer = TUIRenderer()

        # Set up signal handlers on the event loop
        self._loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            self._loop.add_signal_handler(sig, self._handle_signal)

        try:
            with self.renderer.live_context():
                # Start feed
                await self.feed.start([self.token_id])
                self.collector.set_status(BotStatus.STARTING)

                # Wait for feed to be healthy
                for _ in range(30):
                    if self.feed.is_healthy:
                        break
                    state = self.collector.collect()
                    self.renderer.update(state)
                    await asyncio.sleep(0.5)

                if not self.feed.is_healthy:
                    logger.error("Feed failed to become healthy")
                    self.collector.set_status(BotStatus.ERROR)
                    return

                self.collector.set_status(BotStatus.RUNNING)

                # Start market maker task
                mm_task = asyncio.create_task(self._run_market_maker())

                # TUI update loop
                while not self._shutdown_event.is_set():
                    state = self.collector.collect()
                    self.renderer.update(state)

                    # Check for risk stop
                    if self.risk_manager.is_killed:
                        logger.warning("Kill switch activated, stopping...")
                        break

                    # Use interruptible wait instead of sleep
                    try:
                        await asyncio.wait_for(
                            self._shutdown_event.wait(),
                            timeout=self.update_interval
                        )
                        break  # Event was set, exit loop immediately
                    except asyncio.TimeoutError:
                        pass  # Normal timeout, continue loop

                # Cleanup
                mm_task.cancel()
                try:
                    await mm_task
                except asyncio.CancelledError:
                    pass

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            # Remove signal handlers
            if self._loop:
                for sig in (signal.SIGINT, signal.SIGTERM):
                    self._loop.remove_signal_handler(sig)

            self.collector.set_status(BotStatus.STOPPED)
            await self._cleanup()

    def _init_components(self):
        """Initialize all bot components."""
        # Feed
        self.feed = MarketFeed()

        # Risk manager
        self.risk_manager = get_risk_manager()

        # Market maker (convert floats to Decimal for arithmetic compatibility)
        if self.use_smart_mm:
            logger.info("Using SmartMarketMaker (adaptive spread, inventory skewing)")
            self.market_maker = SmartMarketMaker(
                token_id=self.token_id,
                base_spread=Decimal(str(self.spread)),
                size=Decimal(str(self.size)),
                position_limit=Decimal(str(self.position_limit)),
            )
        else:
            self.market_maker = SimpleMarketMaker(
                token_id=self.token_id,
                spread=Decimal(str(self.spread)),
                size=Decimal(str(self.size)),
                position_limit=Decimal(str(self.position_limit)),
            )

        # State collector
        self.collector = get_collector()
        self.collector.set_feed(self.feed)
        self.collector.set_risk_manager(self.risk_manager)
        self.collector.set_market_maker(self.market_maker)
        self.collector.set_market_info(self.token_id, self.market_question)

        if DRY_RUN:
            self.collector.set_simulator(get_simulator())

    async def _run_market_maker(self):
        """Run the market maker strategy."""
        try:
            # Skip signal handlers - TUIBotRunner handles signals
            await self.market_maker.run(install_signals=False)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Market maker error: {e}")
            self.collector.set_status(BotStatus.ERROR)

    async def _cleanup(self):
        """Clean up resources."""
        if self.market_maker:
            self.market_maker.stop()

        if self.feed:
            await self.feed.stop()

        logger.info("Cleanup complete")


async def run_with_tui(
    token_id: str,
    market_question: str = "",
    spread: float = 0.02,
    size: float = 10.0,
    position_limit: float = 100.0,
    use_smart_mm: bool = False,
):
    """
    Convenience function to run bot with TUI.

    Args:
        token_id: Token to trade
        market_question: Market question for display
        spread: Spread to maintain (base spread for SmartMM)
        size: Quote size
        position_limit: Max position
        use_smart_mm: Use SmartMarketMaker instead of SimpleMarketMaker
    """
    runner = TUIBotRunner(
        token_id=token_id,
        market_question=market_question,
        spread=spread,
        size=size,
        use_smart_mm=use_smart_mm,
        position_limit=position_limit
    )
    await runner.run()
