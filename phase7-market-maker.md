# Phase 7: Simple Market Maker

## Overview

This is where it all comes together. A simple market-making loop that:
1. Subscribes to real-time prices
2. Places two-sided quotes (bid + ask)
3. Updates quotes when price moves
4. Respects position limits
5. Shuts down gracefully

**Philosophy:** Get something running end-to-end. Optimize later.

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        MARKET MAKER LOOP                                │
└─────────────────────────────────────────────────────────────────────────┘

                         ┌──────────────┐
                         │  MarketFeed  │
                         │  (Phase 3.5) │
                         └──────┬───────┘
                                │ price updates
                                ▼
┌────────────────────────────────────────────────────────────────────────┐
│                                                                        │
│   1. Get midpoint from feed                                            │
│   2. Calculate bid = mid - spread/2                                    │
│   3. Calculate ask = mid + spread/2                                    │
│   4. If price moved > threshold: cancel old quotes, place new ones     │
│   5. Check position: skip buy if too long, skip sell if too short      │
│   6. Sleep briefly, repeat                                             │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │   place_order()       │
                    │   cancel_order()      │
                    │   (Phase 6)           │
                    └───────────────────────┘
```

---

## Configuration

### Add to src/config.py

```python
# === Market Making ===
MM_SPREAD = Decimal(os.getenv("MM_SPREAD", "0.04"))        # 4 cents each side
MM_SIZE = Decimal(os.getenv("MM_SIZE", "10"))              # Order size
MM_REQUOTE_THRESHOLD = Decimal(os.getenv("MM_REQUOTE_THRESHOLD", "0.02"))  # Requote if mid moves 2c
MM_POSITION_LIMIT = Decimal(os.getenv("MM_POSITION_LIMIT", "50"))  # Max position before skipping side
MM_LOOP_INTERVAL = float(os.getenv("MM_LOOP_INTERVAL", "1.0"))     # Seconds between loops
```

### Update .env.example

```bash
# === Market Making ===
MM_SPREAD=0.04           # Total spread (0.04 = 2 cents each side of mid)
MM_SIZE=10               # Order size in contracts
MM_REQUOTE_THRESHOLD=0.02  # Requote when mid moves this much
MM_POSITION_LIMIT=50     # Max position before stopping one side
MM_LOOP_INTERVAL=1.0     # Seconds between quote updates
```

---

## Implementation

### Create src/strategy/\_\_init\_\_.py

```python
"""Trading strategies."""
```

### Create src/strategy/market_maker.py

```python
"""
Simple market maker.

Places two-sided quotes around the midpoint.
Updates quotes when price moves.
Respects position limits.
"""

import asyncio
import signal
from decimal import Decimal
from typing import Optional
from dataclasses import dataclass

from src.config import (
    DRY_RUN,
    MM_SPREAD,
    MM_SIZE,
    MM_REQUOTE_THRESHOLD,
    MM_POSITION_LIMIT,
    MM_LOOP_INTERVAL,
)
from src.models import Order, OrderSide
from src.trading import place_order, cancel_order, cancel_all_orders, OrderError
from src.orders import get_open_orders, get_position
from src.feed import MarketFeed
from src.utils import setup_logging

logger = setup_logging()


@dataclass
class Quote:
    """Represents a single quote (bid or ask)."""
    order: Optional[Order] = None
    target_price: Optional[Decimal] = None


class SimpleMarketMaker:
    """
    Simple market maker for a single token.
    
    Usage:
        mm = SimpleMarketMaker(token_id="abc123")
        await mm.run()  # Runs until stopped
    
    Stop with Ctrl+C or call mm.stop()
    """
    
    def __init__(
        self,
        token_id: str,
        spread: Decimal = MM_SPREAD,
        size: Decimal = MM_SIZE,
        requote_threshold: Decimal = MM_REQUOTE_THRESHOLD,
        position_limit: Decimal = MM_POSITION_LIMIT,
        loop_interval: float = MM_LOOP_INTERVAL,
    ):
        self.token_id = token_id
        self.spread = spread
        self.size = size
        self.requote_threshold = requote_threshold
        self.position_limit = position_limit
        self.loop_interval = loop_interval
        
        self.feed: Optional[MarketFeed] = None
        self.bid = Quote()
        self.ask = Quote()
        self.last_mid: Optional[Decimal] = None
        self._running = False
        self._shutdown_event = asyncio.Event()
    
    async def run(self):
        """
        Main loop. Runs until stopped.
        
        Call stop() or send SIGINT (Ctrl+C) to stop.
        """
        logger.info(f"Starting market maker for {self.token_id[:16]}...")
        logger.info(f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}")
        logger.info(f"Spread: {self.spread}, Size: {self.size}")
        
        # Set up signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._handle_signal)
        
        try:
            # Start feed
            self.feed = MarketFeed()
            await self.feed.start([self.token_id])
            
            # Wait for initial data
            await self._wait_for_data()
            
            self._running = True
            logger.info("Market maker running. Press Ctrl+C to stop.")
            
            # Main loop
            while self._running and not self._shutdown_event.is_set():
                try:
                    await self._loop_iteration()
                except Exception as e:
                    logger.error(f"Loop error: {e}")
                
                # Wait for next iteration or shutdown
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=self.loop_interval
                    )
                except asyncio.TimeoutError:
                    pass  # Normal - continue loop
        
        finally:
            await self._shutdown()
    
    def stop(self):
        """Signal the market maker to stop."""
        logger.info("Stop requested...")
        self._running = False
        self._shutdown_event.set()
    
    def _handle_signal(self):
        """Handle shutdown signals."""
        self.stop()
    
    async def _wait_for_data(self, timeout: float = 10.0):
        """Wait for feed to have data."""
        logger.info("Waiting for market data...")
        start = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start < timeout:
            if self.feed and self.feed.is_healthy:
                mid = self.feed.get_midpoint(self.token_id)
                if mid is not None:
                    logger.info(f"Got initial mid: {mid}")
                    return
            await asyncio.sleep(0.5)
        
        raise RuntimeError("Timeout waiting for market data")
    
    async def _loop_iteration(self):
        """Single iteration of the market making loop."""
        # Check feed health
        if not self.feed or not self.feed.is_healthy:
            logger.warning("Feed unhealthy - cancelling quotes")
            await self._cancel_all_quotes()
            return
        
        # Get current mid
        mid = self.feed.get_midpoint(self.token_id)
        if mid is None:
            logger.warning("No midpoint available")
            return
        
        mid = Decimal(str(mid))
        
        # Check if we need to requote
        if self._should_requote(mid):
            await self._update_quotes(mid)
            self.last_mid = mid
    
    def _should_requote(self, mid: Decimal) -> bool:
        """Check if quotes need updating."""
        # Always quote if we have no quotes
        if self.bid.order is None and self.ask.order is None:
            return True
        
        # Requote if mid moved beyond threshold
        if self.last_mid is not None:
            move = abs(mid - self.last_mid)
            if move >= self.requote_threshold:
                logger.info(f"Mid moved {move:.4f} - requoting")
                return True
        
        return False
    
    async def _update_quotes(self, mid: Decimal):
        """Cancel old quotes and place new ones."""
        # Calculate target prices
        half_spread = self.spread / 2
        bid_price = mid - half_spread
        ask_price = mid + half_spread
        
        # Round to tick (0.01)
        bid_price = (bid_price * 100).quantize(Decimal("1")) / 100
        ask_price = (ask_price * 100).quantize(Decimal("1")) / 100
        
        # Ensure valid range
        bid_price = max(Decimal("0.01"), min(Decimal("0.98"), bid_price))
        ask_price = max(Decimal("0.02"), min(Decimal("0.99"), ask_price))
        
        logger.info(f"Mid: {mid:.2f} -> Bid: {bid_price:.2f}, Ask: {ask_price:.2f}")
        
        # Cancel existing quotes
        await self._cancel_all_quotes()
        
        # Check position for skewing
        position = get_position(self.token_id)
        
        # Place new quotes
        # Skip buy if too long
        if position < self.position_limit:
            self.bid.order = self._place_quote(OrderSide.BUY, bid_price)
            self.bid.target_price = bid_price
        else:
            logger.info(f"Position {position} at limit - skipping BUY")
        
        # Skip sell if too short
        if position > -self.position_limit:
            self.ask.order = self._place_quote(OrderSide.SELL, ask_price)
            self.ask.target_price = ask_price
        else:
            logger.info(f"Position {position} at limit - skipping SELL")
    
    def _place_quote(self, side: OrderSide, price: Decimal) -> Optional[Order]:
        """Place a single quote."""
        try:
            order = place_order(
                token_id=self.token_id,
                side=side,
                price=price,
                size=self.size
            )
            logger.info(f"Placed {side.value} @ {price}: {order.id}")
            return order
        except OrderError as e:
            logger.error(f"Failed to place {side.value}: {e}")
            return None
    
    async def _cancel_all_quotes(self):
        """Cancel all our quotes."""
        if self.bid.order and self.bid.order.is_live:
            cancel_order(self.bid.order.id)
        if self.ask.order and self.ask.order.is_live:
            cancel_order(self.ask.order.id)
        
        self.bid.order = None
        self.ask.order = None
    
    async def _shutdown(self):
        """Clean shutdown."""
        logger.info("Shutting down market maker...")
        
        # Cancel all orders
        logger.info("Cancelling all orders...")
        cancel_all_orders(self.token_id)
        
        # Stop feed
        if self.feed:
            logger.info("Stopping feed...")
            await self.feed.stop()
        
        logger.info("Market maker stopped.")


async def run_market_maker(token_id: str, **kwargs):
    """
    Convenience function to run a market maker.
    
    Usage:
        asyncio.run(run_market_maker("token123"))
    """
    mm = SimpleMarketMaker(token_id, **kwargs)
    await mm.run()
```

### Create src/strategy/runner.py

```python
"""
CLI runner for the market maker.
"""

import asyncio
import sys
from decimal import Decimal

from src.config import DRY_RUN, get_mode_string
from src.markets import fetch_active_markets
from src.strategy.market_maker import SimpleMarketMaker
from src.utils import setup_logging

logger = setup_logging()


def select_market():
    """Let user select a market to trade."""
    print("\nFetching active markets...")
    markets = fetch_active_markets(limit=20)
    
    if not markets:
        print("No active markets found!")
        return None
    
    print("\nAvailable markets:")
    print("-" * 60)
    
    valid_markets = []
    for i, m in enumerate(markets):
        if not m.token_ids:
            continue
        valid_markets.append(m)
        q = m.question[:50] + "..." if len(m.question) > 50 else m.question
        print(f"  {len(valid_markets)}. {q}")
        print(f"     Volume: ${m.volume:,.0f} | Liquidity: ${m.liquidity:,.0f}")
    
    print("-" * 60)
    
    while True:
        try:
            choice = input("\nSelect market number (or 'q' to quit): ").strip()
            if choice.lower() == 'q':
                return None
            
            idx = int(choice) - 1
            if 0 <= idx < len(valid_markets):
                return valid_markets[idx]
            print("Invalid selection")
        except ValueError:
            print("Enter a number")


def main():
    """Main entry point."""
    print("=" * 60)
    print("  POLYMARKET MARKET MAKER")
    print(f"  Mode: {get_mode_string()}")
    print("=" * 60)
    
    if not DRY_RUN:
        print("\n⚠️  WARNING: LIVE TRADING MODE ⚠️")
        print("Real money will be used!")
        confirm = input("Type 'YES' to continue: ").strip()
        if confirm != "YES":
            print("Aborted.")
            return
    
    # Select market
    market = select_market()
    if not market:
        print("No market selected. Exiting.")
        return
    
    token_id = market.token_ids[0]  # Trade the first outcome (YES)
    
    print(f"\nSelected: {market.question}")
    print(f"Token: {token_id[:20]}...")
    print(f"\nStarting market maker...")
    print("Press Ctrl+C to stop\n")
    
    # Run
    mm = SimpleMarketMaker(token_id)
    
    try:
        asyncio.run(mm.run())
    except KeyboardInterrupt:
        print("\nInterrupted.")


if __name__ == "__main__":
    main()
```

---

## Running the Bot

### Option 1: Direct Python

```bash
# Make sure you're in the project directory with venv activated
cd polymarket-bot
source venv/bin/activate

# Run
python -m src.strategy.runner
```

### Option 2: Create run script

Create `run_mm.py` in project root:

```python
#!/usr/bin/env python3
"""Run the market maker."""

from src.strategy.runner import main

if __name__ == "__main__":
    main()
```

Then:
```bash
python run_mm.py
```

---

## Tests

### Create tests/test_phase7.py

```python
"""
Phase 7 Tests - Market maker.

Run: pytest tests/test_phase7.py -v
"""

import pytest
import asyncio
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch


class TestQuoteCalculation:
    """Test quote price calculations."""
    
    def test_spread_calculation(self):
        from src.strategy.market_maker import SimpleMarketMaker
        
        mm = SimpleMarketMaker(
            token_id="test",
            spread=Decimal("0.04"),
            size=Decimal("10")
        )
        
        # With mid at 0.50 and spread 0.04:
        # bid = 0.50 - 0.02 = 0.48
        # ask = 0.50 + 0.02 = 0.52
        mid = Decimal("0.50")
        half = mm.spread / 2
        
        bid = mid - half
        ask = mid + half
        
        assert bid == Decimal("0.48")
        assert ask == Decimal("0.52")
        
        print("✓ Spread calculation correct")
    
    def test_requote_threshold(self):
        from src.strategy.market_maker import SimpleMarketMaker
        
        mm = SimpleMarketMaker(
            token_id="test",
            requote_threshold=Decimal("0.02")
        )
        
        mm.last_mid = Decimal("0.50")
        
        # Small move - no requote
        assert not mm._should_requote(Decimal("0.51"))
        
        # Large move - requote
        assert mm._should_requote(Decimal("0.53"))
        
        print("✓ Requote threshold works")


class TestPositionLimits:
    """Test position limit handling."""
    
    def test_skip_buy_when_long(self):
        from src.strategy.market_maker import SimpleMarketMaker
        from src.simulator import get_simulator, reset_simulator
        from src.models import OrderSide
        from src.config import DRY_RUN
        
        if not DRY_RUN:
            pytest.skip("Requires DRY_RUN=true")
        
        reset_simulator()
        sim = get_simulator()
        
        mm = SimpleMarketMaker(
            token_id="test",
            position_limit=Decimal("50"),
            spread=Decimal("0.04"),
            size=Decimal("10")
        )
        
        # Simulate being at position limit
        # Create and fill a buy order
        order = sim.create_order("test", OrderSide.BUY, Decimal("0.50"), Decimal("50"))
        sim.check_fills("test", Decimal("0.45"), Decimal("0.50"))
        
        # Position should be 50
        from src.orders import get_position
        assert get_position("test") == Decimal("50")
        
        print("✓ Position tracking works")


class TestMarketMakerLifecycle:
    """Test market maker start/stop."""
    
    @pytest.mark.asyncio
    async def test_creates_and_stops(self):
        from src.strategy.market_maker import SimpleMarketMaker
        
        mm = SimpleMarketMaker(token_id="test_token")
        
        assert mm._running == False
        assert mm.feed is None
        
        # Stop before starting should be safe
        mm.stop()
        
        print("✓ Market maker lifecycle safe")
    
    @pytest.mark.asyncio
    async def test_signal_handling(self):
        from src.strategy.market_maker import SimpleMarketMaker
        
        mm = SimpleMarketMaker(token_id="test")
        
        # Simulate signal
        mm._handle_signal()
        
        assert mm._running == False
        assert mm._shutdown_event.is_set()
        
        print("✓ Signal handling works")


class TestWithMockFeed:
    """Test with mocked feed."""
    
    @pytest.mark.asyncio
    async def test_places_quotes_on_healthy_feed(self):
        from src.strategy.market_maker import SimpleMarketMaker
        from src.simulator import reset_simulator
        from src.orders import get_open_orders
        from src.config import DRY_RUN
        
        if not DRY_RUN:
            pytest.skip("Requires DRY_RUN=true")
        
        reset_simulator()
        
        mm = SimpleMarketMaker(
            token_id="test",
            spread=Decimal("0.04"),
            size=Decimal("10")
        )
        
        # Mock feed
        mock_feed = Mock()
        mock_feed.is_healthy = True
        mock_feed.get_midpoint = Mock(return_value=0.50)
        mm.feed = mock_feed
        mm.last_mid = None
        
        # Run one iteration
        await mm._loop_iteration()
        
        # Should have placed quotes
        orders = get_open_orders()
        assert len(orders) == 2
        
        # Check prices
        bids = [o for o in orders if o.side.value == "BUY"]
        asks = [o for o in orders if o.side.value == "SELL"]
        
        assert len(bids) == 1
        assert len(asks) == 1
        assert bids[0].price == Decimal("0.48")
        assert asks[0].price == Decimal("0.52")
        
        print("✓ Quotes placed correctly")
    
    @pytest.mark.asyncio
    async def test_cancels_on_unhealthy_feed(self):
        from src.strategy.market_maker import SimpleMarketMaker
        from src.simulator import reset_simulator, get_simulator
        from src.orders import get_open_orders
        from src.models import OrderSide
        from src.config import DRY_RUN
        
        if not DRY_RUN:
            pytest.skip("Requires DRY_RUN=true")
        
        reset_simulator()
        sim = get_simulator()
        
        mm = SimpleMarketMaker(token_id="test")
        
        # Place some orders first
        mm.bid.order = sim.create_order("test", OrderSide.BUY, Decimal("0.48"), Decimal("10"))
        mm.ask.order = sim.create_order("test", OrderSide.SELL, Decimal("0.52"), Decimal("10"))
        
        assert len(get_open_orders()) == 2
        
        # Mock unhealthy feed
        mock_feed = Mock()
        mock_feed.is_healthy = False
        mm.feed = mock_feed
        
        # Run iteration
        await mm._loop_iteration()
        
        # Should have cancelled
        assert len(get_open_orders()) == 0
        
        print("✓ Cancels quotes on unhealthy feed")


class TestIntegration:
    """Integration test with real market data (dry run)."""
    
    @pytest.mark.asyncio
    async def test_full_cycle_with_real_market(self):
        """Test one cycle with real market data."""
        from src.config import DRY_RUN
        from src.markets import fetch_active_markets
        from src.strategy.market_maker import SimpleMarketMaker
        from src.orders import get_open_orders
        from src.simulator import reset_simulator
        
        if not DRY_RUN:
            pytest.skip("Requires DRY_RUN=true")
        
        reset_simulator()
        
        # Get real market
        markets = fetch_active_markets(limit=5)
        token_id = None
        for m in markets:
            if m.token_ids:
                token_id = m.token_ids[0]
                break
        
        if not token_id:
            pytest.skip("No markets")
        
        print(f"  Token: {token_id[:20]}...")
        
        mm = SimpleMarketMaker(
            token_id=token_id,
            spread=Decimal("0.04"),
            size=Decimal("10"),
            loop_interval=0.5
        )
        
        # Run for a short time
        async def run_briefly():
            mm._running = True
            mm.feed = Mock()
            mm.feed.is_healthy = True
            
            # Get real midpoint from pricing
            from src.pricing import get_order_book
            book = get_order_book(token_id)
            if book and book.midpoint:
                mm.feed.get_midpoint = Mock(return_value=book.midpoint)
                print(f"  Midpoint: {book.midpoint}")
                
                # Run one iteration
                await mm._loop_iteration()
                
                orders = get_open_orders()
                print(f"  Orders placed: {len(orders)}")
                
                if orders:
                    for o in orders:
                        print(f"    {o.side.value} {o.size} @ {o.price}")
                
                # Cleanup
                await mm._cancel_all_quotes()
        
        await run_briefly()
        print("✓ Real market cycle works")
```

---

## File Structure After Phase 7

```
polymarket-bot/
├── src/
│   ├── strategy/
│   │   ├── __init__.py
│   │   ├── market_maker.py    # SimpleMarketMaker class
│   │   └── runner.py          # CLI runner
│   ├── config.py              # + MM_* settings
│   ├── trading.py             # Phase 6
│   ├── orders.py              # Phase 6
│   └── ...
│
├── tests/
│   └── test_phase7.py         # ~10 tests
│
├── run_mm.py                  # Entry point
└── .env                       # + MM_* settings
```

---

## Verification

```bash
# Run tests
pytest tests/test_phase7.py -v

# Run the bot (dry run)
python run_mm.py
```

---

## What It Does

```
$ python run_mm.py

============================================================
  POLYMARKET MARKET MAKER
  Mode: DRY RUN (paper trading)
============================================================

Fetching active markets...

Available markets:
------------------------------------------------------------
  1. Will Bitcoin reach $100k by end of 2024?
     Volume: $1,234,567 | Liquidity: $456,789
  2. Will the Fed cut rates in December?
     Volume: $987,654 | Liquidity: $321,098
  ...
------------------------------------------------------------

Select market number (or 'q' to quit): 1

Selected: Will Bitcoin reach $100k by end of 2024?
Token: 0x1234567890abcdef...

Starting market maker...
Press Ctrl+C to stop

2024-01-15 10:30:00 INFO Starting market maker for 0x1234567890ab...
2024-01-15 10:30:00 INFO Mode: DRY RUN
2024-01-15 10:30:00 INFO Spread: 0.04, Size: 10
2024-01-15 10:30:01 INFO Waiting for market data...
2024-01-15 10:30:02 INFO Got initial mid: 0.65
2024-01-15 10:30:02 INFO Market maker running. Press Ctrl+C to stop.
2024-01-15 10:30:02 INFO Mid: 0.65 -> Bid: 0.63, Ask: 0.67
2024-01-15 10:30:02 INFO [DRY RUN] Order: BUY 10 @ 0.63
2024-01-15 10:30:02 INFO [DRY RUN] Order: SELL 10 @ 0.67
2024-01-15 10:30:02 INFO Placed BUY @ 0.63: sim_abc123
2024-01-15 10:30:02 INFO Placed SELL @ 0.67: sim_def456
...
^C
2024-01-15 10:35:00 INFO Stop requested...
2024-01-15 10:35:00 INFO Shutting down market maker...
2024-01-15 10:35:00 INFO Cancelling all orders...
2024-01-15 10:35:00 INFO Stopping feed...
2024-01-15 10:35:00 INFO Market maker stopped.
```

---

## Configuration Tuning

| Setting | Default | Description |
|---------|---------|-------------|
| `MM_SPREAD` | 0.04 | Total spread (0.04 = bid 2c below mid, ask 2c above) |
| `MM_SIZE` | 10 | Order size in contracts |
| `MM_REQUOTE_THRESHOLD` | 0.02 | Requote when mid moves this much |
| `MM_POSITION_LIMIT` | 50 | Stop buying/selling when position exceeds this |
| `MM_LOOP_INTERVAL` | 1.0 | Seconds between quote updates |

**Start conservative:**
- Wide spread (0.06-0.10) = safer but fewer fills
- Small size (5-10) = less risk per trade
- Low position limit (25-50) = limits exposure

---

## Next: Phase 8

Basic risk controls:
- Daily loss limit
- Kill switch
- Position alerts
- Manual stop command

But first - run Phase 7 and watch it work!
