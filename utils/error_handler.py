"""
utils/error_handler.py
======================
Centralised error-handling utilities for AURA.

Provides:
- ``handle_errors`` — decorator that catches exceptions and returns a
  configurable fallback value, keeping AURA alive on unexpected errors.
- ``safe_execute`` — functional equivalent for ad-hoc call-sites.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def handle_errors(
    fallback: Any = None,
    message: str = "An unexpected error occurred",
    reraise: bool = False,
) -> Callable[[F], F]:
    """
    Decorator that catches all exceptions and returns *fallback*.

    Parameters
    ----------
    fallback:
        Value to return when an exception is raised by the decorated
        function.  Defaults to ``None``.
    message:
        Prefix for the error log entry.
    reraise:
        If ``True``, the exception is re-raised after logging.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("%s: %s", message, exc, exc_info=True)
                if reraise:
                    raise
                return fallback

        return wrapper  # type: ignore[return-value]

    return decorator


def safe_execute(
    func: Callable[..., Any],
    *args: Any,
    fallback: Any = None,
    context: str = "",
    **kwargs: Any,
) -> Any:
    """
    Call *func* with *args* / *kwargs*, returning *fallback* on any exception.

    Parameters
    ----------
    func:
        Callable to invoke.
    fallback:
        Value to return on failure.  Defaults to ``None``.
    context:
        Human-readable description logged alongside the error message.
    """
    try:
        return func(*args, **kwargs)
    except Exception as exc:  # pylint: disable=broad-except
        ctx = f" [{context}]" if context else ""
        logger.error("safe_execute%s failed: %s", ctx, exc, exc_info=True)
        return fallback
