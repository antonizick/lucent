"""
Logging setup for Lucent Email System.

Provides consistent logging across all components.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

from .config import LoggingConfig


def setup_logging(config: LoggingConfig) -> logging.Logger:
    """
    Set up logging based on configuration.

    Args:
        config: LoggingConfig instance.

    Returns:
        Configured logger instance.
    """
    # Create logger
    logger = logging.getLogger("lucent_email")

    # Clear existing handlers
    logger.handlers = []

    # Set level
    level = getattr(logging, config.level.upper(), logging.INFO)
    logger.setLevel(level)

    # Create formatter
    formatter = logging.Formatter(
        "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Add file handler if path specified
    if config.path:
        log_path = Path(config.path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "lucent_email") -> logging.Logger:
    """
    Get or create a logger.

    Args:
        name: Logger name (default: "lucent_email").

    Returns:
        Logger instance.
    """
    return logging.getLogger(name)


# Convenience function to log operations
def log_sync_start(logger: logging.Logger, backend: str) -> None:
    """Log sync start."""
    logger.info(f"Starting sync for {backend} backend")


def log_sync_complete(logger: logging.Logger, backend: str, count: int, duration: float) -> None:
    """Log sync completion."""
    logger.info(f"Sync complete for {backend}: {count} emails in {duration:.2f}s")


def log_search(logger: logging.Logger, query: str, count: int, duration: float) -> None:
    """Log search operation."""
    logger.info(f"Search '{query}': {count} results in {duration:.3f}s")


def log_error(logger: logging.Logger, component: str, error: str) -> None:
    """Log error."""
    logger.error(f"{component}: {error}")
