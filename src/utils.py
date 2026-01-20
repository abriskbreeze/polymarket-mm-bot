"""
Utility functions for the Polymarket Trading Bot
"""

import logging
from datetime import datetime


def setup_logging():
    """
    Configure Python logging for the application

    Sets up console handler with timestamp, level, and message format.

    Returns:
        logging.Logger: Configured logger instance
    """
    # Create logger
    logger = logging.getLogger("polymarket-bot")
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers if setup_logging is called multiple times
    if not logger.handlers:
        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        # Create formatter
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Add formatter to handler
        console_handler.setFormatter(formatter)

        # Add handler to logger
        logger.addHandler(console_handler)

    return logger


def format_timestamp(ts):
    """
    Format a timestamp for display

    Args:
        ts: Unix timestamp (int or float) or datetime object

    Returns:
        str: Formatted timestamp string
    """
    if isinstance(ts, (int, float)):
        dt = datetime.fromtimestamp(ts)
    elif isinstance(ts, datetime):
        dt = ts
    else:
        return str(ts)

    return dt.strftime('%Y-%m-%d %H:%M:%S')
