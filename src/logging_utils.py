"""Logging utilities for UDP bridge."""

import logging


def setup_logging(level: str = "INFO") -> None:
    """Setup logging configuration.

    :param level: Logging level (DEBUG, INFO, WARNING, ERROR)
    :return: None
    """
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def log(message: str, level: str = "INFO") -> None:
    """Log a message with specified level.

    :param message: Message to log
    :param level: Logging level (DEBUG, INFO, WARNING, ERROR)
    :return: None
    """
    getattr(logging, level.lower())(message)

