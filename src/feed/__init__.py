"""
Market data feed with automatic failover.

Simple usage:
    feed = MarketFeed()
    await feed.start(["token1", "token2"])

    if feed.is_healthy:
        price = feed.get_midpoint("token1")
"""

from src.feed.feed import MarketFeed, FeedState

__all__ = ['MarketFeed', 'FeedState']
