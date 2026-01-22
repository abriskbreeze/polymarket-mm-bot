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
from src.pricing import get_order_books
from src.strategy.market_scorer import MarketScorer
from src.tui.runner import run_with_tui
from src.utils import setup_logging

logger = setup_logging()


def auto_select_market():
    """Auto-select the best market using MarketScorer."""
    print("\n📊 Fetching and scoring markets...\n")

    try:
        markets = fetch_active_markets(limit=50)
    except Exception as e:
        print(f"Error fetching markets: {e}")
        return None, None

    # Filter markets with tokens
    markets = [m for m in markets if m.token_ids]
    if not markets:
        print("No active markets with token IDs found.")
        return None, None

    # Fetch order books for scoring
    token_ids = [m.token_ids[0] for m in markets]
    books = get_order_books(token_ids)

    # Build scoring input
    scorer = MarketScorer()
    score_input = []
    for m in markets:
        token_id = m.token_ids[0]
        book = books.get(token_id)
        volume = m.volume or 0
        score_input.append((token_id, m, book, volume))

    # Score and sort
    scores = scorer.score_markets(score_input)

    # Find best non-rejected market
    for score in scores:
        if not score.rejected:
            for m in markets:
                if m.token_ids[0] == score.token_id:
                    print(f"✓ Auto-selected: {score.market_question[:55]}...")
                    print(f"  Score: {score.total_score:.1f}/100")
                    print(f"  Volume: ${score.volume_24h:,.0f} | Spread: {score.spread:.3f}")
                    return m, score
            break

    # All rejected
    print("No suitable markets found. Top rejections:")
    for score in scores[:3]:
        print(f"  - {score.market_question[:40]}... ({score.reject_reason})")
    return None, None


def select_market_interactive():
    """Interactively select a market."""
    print("\n📊 Fetching active markets...\n")

    try:
        # Fetch more markets since API sorting is unreliable
        markets = fetch_active_markets(limit=100)
    except Exception as e:
        print(f"Error fetching markets: {e}")
        sys.exit(1)

    # Filter markets with tokens and sort by volume client-side
    markets = [m for m in markets if m.token_ids]
    markets.sort(key=lambda m: m.volume or 0, reverse=True)
    markets = markets[:15]  # Top 15 by volume

    if not markets:
        print("No active markets with token IDs found.")
        sys.exit(1)

    # Fetch order books to show spreads
    print("Fetching spreads...")
    token_ids = [m.token_ids[0] for m in markets]
    books = get_order_books(token_ids)

    print("\nSelect a market:\n")
    for i, market in enumerate(markets, 1):
        volume_str = f"${market.volume:,.0f}" if market.volume else "N/A"
        token_id = market.token_ids[0]
        book = books.get(token_id)
        if book and book.spread and book.midpoint:
            spread_pct = (book.spread / book.midpoint) * 100
            spread_str = f"{spread_pct:.1f}%"
        else:
            spread_str = "N/A"
        print(f"  {i}. {market.question[:55]}...")
        print(f"     Volume: {volume_str:>12}  |  Spread: {spread_str}")
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
    parser.add_argument(
        "--manual", "-m",
        action="store_true",
        help="Manually select market instead of auto-selecting best"
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
    market = None
    if args.token:
        token_id = args.token
        question = args.question
    elif args.manual:
        market = select_market_interactive()
        token_id = market.token_ids[0]
        question = market.question
        print(f"\n✓ Selected: {question[:50]}...")
        print(f"  Token: {token_id[:20]}...")
    else:
        market, score = auto_select_market()
        if not market:
            print("\nNo suitable market found. Try --manual to select manually.")
            sys.exit(1)
        token_id = market.token_ids[0]
        question = market.question

    # Get complement token for arbitrage (if available)
    complement_token_id = None
    if market and hasattr(market, 'token_ids') and len(market.token_ids) == 2:
        complement_token_id = [tid for tid in market.token_ids if tid != token_id][0]
        print(f"   Complement token: {complement_token_id[:20]}...")

    print(f"\n🚀 Starting TUI bot...")
    print(f"   Market Maker: SmartMarketMaker")
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
            position_limit=args.position_limit,
            complement_token_id=complement_token_id,
        ))
    except KeyboardInterrupt:
        print("\nShutdown complete.")


if __name__ == "__main__":
    main()
