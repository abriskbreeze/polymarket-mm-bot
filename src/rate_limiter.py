"""
Simple rate limiter for API calls.
"""

import asyncio
import time
from typing import Optional


class RateLimiter:
    """
    Token bucket rate limiter.

    Usage:
        limiter = RateLimiter(calls_per_second=10)

        # Sync usage:
        limiter.wait_sync()
        make_api_call()

        # Async usage:
        await limiter.wait()
        await make_api_call()
    """

    def __init__(self, calls_per_second: float = 10.0):
        self._min_interval = 1.0 / calls_per_second
        self._last_call: float = 0.0
        self._lock = asyncio.Lock()

    def wait_sync(self):
        """Blocking wait for rate limit (for sync code)."""
        now = time.time()
        elapsed = now - self._last_call

        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)

        self._last_call = time.time()

    async def wait(self):
        """Async wait for rate limit."""
        async with self._lock:
            now = time.time()
            elapsed = now - self._last_call

            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)

            self._last_call = time.time()


# Global limiters for different API endpoints
_order_limiter: Optional[RateLimiter] = None
_market_data_limiter: Optional[RateLimiter] = None


def get_order_limiter() -> RateLimiter:
    """Get rate limiter for order operations (more restrictive)."""
    global _order_limiter
    if _order_limiter is None:
        from src.config import RATE_LIMIT_ORDERS_PER_SECOND
        _order_limiter = RateLimiter(RATE_LIMIT_ORDERS_PER_SECOND)
    return _order_limiter


def get_market_data_limiter() -> RateLimiter:
    """Get rate limiter for market data operations."""
    global _market_data_limiter
    if _market_data_limiter is None:
        from src.config import RATE_LIMIT_DATA_PER_SECOND
        _market_data_limiter = RateLimiter(RATE_LIMIT_DATA_PER_SECOND)
    return _market_data_limiter
