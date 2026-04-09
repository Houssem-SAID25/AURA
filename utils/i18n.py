"""
utils/i18n.py
=============
Lightweight internationalisation (i18n) helper for the AURA GUI and utilities.

Provides an ``I18n`` class that loads flat JSON translation files from the
``locales/`` directory at the repository root, and a module-level singleton
``i18n`` for convenience.

Usage
-----
    from utils.i18n import i18n

    i18n.set_language("fr")
    print(i18n.t("greeting"))
    print(i18n.t("game_launching", game="Valorant"))
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Resolve the locales directory relative to the repository root
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOCALES_DIR = os.path.join(_REPO_ROOT, "locales")
_SUPPORTED = ("en", "fr")


class I18n:
    """Simple JSON-backed translation helper.

    Parameters
    ----------
    lang:
        Initial language code (``"en"`` or ``"fr"``).  Defaults to ``"en"``.
    """

    def __init__(self, lang: str = "en") -> None:
        self._lang: str = lang
        self._strings: dict[str, Any] = {}
        self.set_language(lang)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_language(self, lang: str) -> None:
        """Load translation strings for *lang*.

        Falls back to English if the requested language file is unavailable.
        """
        if lang not in _SUPPORTED:
            logger.warning("Language '%s' not supported; falling back to 'en'.", lang)
            lang = "en"

        path = os.path.join(_LOCALES_DIR, f"{lang}.json")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                self._strings = json.load(fh)
            self._lang = lang
            logger.debug("Loaded locale '%s' from '%s'.", lang, path)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            logger.error("Could not load locale '%s': %s", lang, exc)
            if lang != "en":
                self.set_language("en")

    def get_language(self) -> str:
        """Return the currently active language code."""
        return self._lang

    def t(self, key: str, **kwargs: Any) -> str:
        """Return the translated string for *key*, formatted with *kwargs*.

        Falls back to returning the key itself if the key is missing.

        Parameters
        ----------
        key:
            Flat string key, e.g. ``"greeting"`` or ``"game_launching"``.
        **kwargs:
            Named format arguments applied via :meth:`str.format`.
        """
        value = self._strings.get(key)
        if value is None:
            logger.warning("Missing translation key '%s' for language '%s'.", key, self._lang)
            return key

        if kwargs and isinstance(value, str):
            try:
                return value.format(**kwargs)
            except KeyError:
                return value

        return str(value)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

i18n = I18n()
