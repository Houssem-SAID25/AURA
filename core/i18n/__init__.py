"""
core/i18n/__init__.py
=====================
Minimal internationalisation helper for AURA.

Usage
-----
    from core.i18n import set_language, t

    set_language("fr")
    print(t("onboarding.welcome"))        # Bienvenue sur AURA
    print(t("onboarding.done_message", username="Houssem"))
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_LOCALE_DIR = os.path.dirname(os.path.abspath(__file__))
_SUPPORTED_LANGUAGES = ("en", "fr")
_DEFAULT_LANGUAGE = "en"

# Currently loaded translations {key: value}
_translations: dict[str, Any] = {}
_current_language: str = _DEFAULT_LANGUAGE


def set_language(lang: str) -> None:
    """Load the translation file for *lang* (``"en"`` or ``"fr"``).

    Falls back to English if the requested language file is unavailable.
    """
    global _translations, _current_language

    if lang not in _SUPPORTED_LANGUAGES:
        logger.warning("Language '%s' is not supported; falling back to 'en'.", lang)
        lang = _DEFAULT_LANGUAGE

    path = os.path.join(_LOCALE_DIR, f"{lang}.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            _translations = json.load(fh)
        _current_language = lang
        logger.debug("Loaded translations for language '%s'.", lang)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.error("Could not load translations for '%s': %s", lang, exc)
        if lang != _DEFAULT_LANGUAGE:
            set_language(_DEFAULT_LANGUAGE)


def get_language() -> str:
    """Return the currently active language code."""
    return _current_language


def t(key: str, **kwargs: Any) -> str:
    """Return the translated string for *key*, formatted with *kwargs*.

    Keys use dot-notation to navigate nested JSON objects, e.g.
    ``"onboarding.welcome"``.  Returns the key itself if not found.
    """
    if not _translations:
        # Lazy-load English on first use
        set_language(_DEFAULT_LANGUAGE)

    parts = key.split(".")
    node: Any = _translations
    for part in parts:
        if isinstance(node, dict):
            node = node.get(part)
        else:
            node = None
            break

    if node is None:
        logger.warning("Missing translation key: '%s'", key)
        return key

    if kwargs and isinstance(node, str):
        try:
            return node.format(**kwargs)
        except KeyError:
            return node

    return str(node)


# Load default language at import time
set_language(_DEFAULT_LANGUAGE)
