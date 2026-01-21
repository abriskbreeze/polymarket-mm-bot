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


async def log_status_periodically(mm: SimpleMarketMaker, interval: float = 30.0):
    """Log status every N seconds."""
    while mm._running:
        await asyncio.sleep(interval)
        if mm._running:
            status = mm.risk.get_status()
            logger.info(
                f"Status: Mode={status['mode']} | "
                f"PnL={status['daily_pnl']:+.2f} ({status['pnl_percent_of_limit']:.0f}% of limit) | "
                f"Events={status['risk_events_logged']}"
            )


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

    async def run_with_status():
        """Run market maker with periodic status updates."""
        status_task = asyncio.create_task(log_status_periodically(mm))
        try:
            await mm.run()
        finally:
            status_task.cancel()
            try:
                await status_task
            except asyncio.CancelledError:
                pass

    try:
        asyncio.run(run_with_status())
    except KeyboardInterrupt:
        print("\nInterrupted.")


if __name__ == "__main__":
    main()
