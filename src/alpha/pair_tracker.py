"""
Token Pair Tracker

Discovers and maintains YES/NO token pairs for all markets.
Uses Polymarket Gamma API to resolve condition_id -> token pairs.
"""

import time
from typing import Dict, List, Optional

from src.markets import fetch_active_markets
from src.alpha.arbitrage import TokenPair


class PairTracker:
    """
    Tracks YES/NO token pairs across markets.

    Usage:
        tracker = PairTracker()
        tracker.refresh()  # Synchronous API call

        pair = tracker.get_pair(condition_id)
        all_pairs = tracker.get_all_pairs()
    """

    def __init__(self, refresh_interval: int = 300):
        """
        Initialize the pair tracker.

        Args:
            refresh_interval: Seconds between auto-refresh (default 5 minutes)
        """
        self._pairs: Dict[str, TokenPair] = {}
        self._last_refresh: float = 0
        self._refresh_interval = refresh_interval

    def refresh(self) -> int:
        """
        Refresh pair mappings from API.

        Returns:
            Number of pairs discovered
        """
        markets = fetch_active_markets(limit=100)

        for market in markets:
            condition_id = market.condition_id
            if not condition_id:
                continue

            yes_token = None
            no_token = None

            for outcome in market.outcomes:
                # Match case-insensitive "Yes"/"No"
                name_lower = outcome.name.lower()
                if name_lower == "yes":
                    yes_token = outcome.token_id
                elif name_lower == "no":
                    no_token = outcome.token_id

            if yes_token and no_token:
                self._pairs[condition_id] = TokenPair(
                    condition_id=condition_id,
                    yes_token_id=yes_token,
                    no_token_id=no_token,
                    market_slug=market.slug or "",
                )

        self._last_refresh = time.time()
        return len(self._pairs)

    def refresh_if_stale(self) -> bool:
        """
        Refresh only if interval has elapsed.

        Returns:
            True if refresh occurred, False otherwise
        """
        if time.time() - self._last_refresh > self._refresh_interval:
            self.refresh()
            return True
        return False

    def get_pair(self, condition_id: str) -> Optional[TokenPair]:
        """Get pair by condition ID."""
        return self._pairs.get(condition_id)

    def get_pair_for_token(self, token_id: str) -> Optional[TokenPair]:
        """Get pair containing this token."""
        for pair in self._pairs.values():
            if token_id in (pair.yes_token_id, pair.no_token_id):
                return pair
        return None

    def get_all_pairs(self) -> List[TokenPair]:
        """Get all tracked pairs."""
        return list(self._pairs.values())

    def get_complement_token(self, token_id: str) -> Optional[str]:
        """Get the complementary token (YES->NO or NO->YES)."""
        pair = self.get_pair_for_token(token_id)
        if pair is None:
            return None
        if token_id == pair.yes_token_id:
            return pair.no_token_id
        return pair.yes_token_id

    @property
    def pair_count(self) -> int:
        """Number of tracked pairs."""
        return len(self._pairs)

    @property
    def last_refresh_time(self) -> float:
        """Unix timestamp of last refresh."""
        return self._last_refresh
