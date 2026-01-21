"""
Utility functions for the Polymarket Trading Bot
"""

import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: str = None):
    """
    Configure Python logging for the application

    Sets up console handler and rotating file handler.
    Logs are saved to logs/ directory with 10MB rotation, keeping 5 backups.

    Args:
        log_dir: Optional custom log directory. Defaults to ./logs/

    Returns:
        logging.Logger: Configured logger instance
    """
    logger = logging.getLogger("polymarket-bot")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # File handler with rotation
        if log_dir is None:
            log_dir = Path(__file__).parent.parent / "logs"
        else:
            log_dir = Path(log_dir)

        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / "bot.log"

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

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
