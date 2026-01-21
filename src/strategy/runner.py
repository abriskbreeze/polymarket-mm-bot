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
