"""
utils/logger.py
===============
Centralised logging configuration for AURA.

Provides a single ``setup_logging`` function that configures the root
logger from a config dict, and a ``get_logger`` convenience wrapper.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional


def setup_logging(config: dict) -> None:
    """
    Configure the root logger based on the ``logging`` section of *config*.

    Parameters
    ----------
    config:
        Application config dict.  Reads ``logging.level`` (default ``INFO``)
        and ``logging.file`` (default ``aura.log``).  Set ``logging.file``
        to an empty string to disable file logging.
    """
    log_cfg = config.get("logging", {})
    level_name: str = log_cfg.get("level", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    log_file: Optional[str] = log_cfg.get("file", "aura.log")

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


def get_logger(name: str) -> logging.Logger:
    """Return a named logger instance."""
    return logging.getLogger(name)
