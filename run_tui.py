#!/usr/bin/env python3
"""
Run the market maker bot with TUI display.

Usage:
    python run_tui.py                     # Interactive market selection
    python run_tui.py --token TOKEN_ID    # Specific token
    python run_tui.py --help              # Help
"""

import asyncio
import argparse
import sys

from src.config import DRY_RUN
from src.markets import fetch_active_markets
from src.tui.runner import run_with_tui
from src.utils import setup_logging

logger = setup_logging()


def select_market_interactive():
    """Interactively select a market."""
    print("\n📊 Fetching active markets...\n")

    try:
        markets = fetch_active_markets(limit=10)
    except Exception as e:
        print(f"Error fetching markets: {e}")
        sys.exit(1)

    # Filter markets with tokens
    markets = [m for m in markets if m.token_ids]

    if not markets:
        print("No active markets with token IDs found.")
        sys.exit(1)

    print("Select a market:\n")
    for i, market in enumerate(markets, 1):
        volume_str = f"${market.volume:,.0f}" if market.volume else "N/A"
        print(f"  {i}. {market.question[:60]}...")
        print(f"     Volume: {volume_str}")
        print()

    while True:
        try:
            choice = input("Enter number (or 'q' to quit): ").strip()
            if choice.lower() == 'q':
                sys.exit(0)

            idx = int(choice) - 1
            if 0 <= idx < len(markets):
                return markets[idx]
            else:
                print("Invalid selection, try again.")
        except ValueError:
            print("Please enter a number.")
        except KeyboardInterrupt:
            print("\nCancelled.")
            sys.exit(0)


def main():
    parser = argparse.ArgumentParser(
        description="Run Polymarket market maker with TUI display"
    )
    parser.add_argument(
        "--token", "-t",
        help="Token ID to trade"
    )
    parser.add_argument(
        "--question", "-q",
        default="",
        help="Market question (for display)"
    )
    parser.add_argument(
        "--spread", "-s",
        type=float,
        default=0.02,
        help="Spread to maintain (default: 0.02)"
    )
    parser.add_argument(
        "--size", "-z",
        type=float,
        default=10.0,
        help="Quote size (default: 10.0)"
    )
    parser.add_argument(
        "--position-limit", "-p",
        type=float,
        default=100.0,
        help="Max position size (default: 100.0)"
    )

    args = parser.parse_args()

    # Print mode banner
    mode = "DRY_RUN" if DRY_RUN else "LIVE"
    mode_color = "\033[96m" if DRY_RUN else "\033[91m"
    reset = "\033[0m"
    print(f"\n{mode_color}{'='*60}")
    print(f"  MODE: {mode}")
    print(f"{'='*60}{reset}\n")

    if not DRY_RUN:
        confirm = input("⚠️  LIVE mode - real money at risk. Continue? [y/N]: ")
        if confirm.lower() != 'y':
            print("Aborted.")
            sys.exit(0)

    # Get token
    if args.token:
        token_id = args.token
        question = args.question
    else:
        market = select_market_interactive()
        token_id = market.token_ids[0]
        question = market.question
        print(f"\n✓ Selected: {question[:50]}...")
        print(f"  Token: {token_id[:20]}...")

    print(f"\n🚀 Starting TUI bot...")
    print(f"   Spread: {args.spread}")
    print(f"   Size: {args.size}")
    print(f"   Position Limit: {args.position_limit}")
    print()

    # Run
    try:
        asyncio.run(run_with_tui(
            token_id=token_id,
            market_question=question,
            spread=args.spread,
            size=args.size,
            position_limit=args.position_limit
        ))
    except KeyboardInterrupt:
        print("\nShutdown complete.")


if __name__ == "__main__":
    main()
