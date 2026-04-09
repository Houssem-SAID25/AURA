"""
utils/config_loader.py
======================
Configuration loading utility for AURA.

Loads ``config.json`` (or any JSON file) relative to the repository root
and returns the parsed dict.  Errors are handled gracefully — a missing
or malformed file returns an empty dict instead of crashing.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Repository root: two levels up from this file (utils/config_loader.py)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Keys that AURA expects and their default values.
# A missing key triggers a WARNING so users know what to configure.
_DEFAULTS: dict[str, Any] = {
    "obs": {
        "host": "localhost",
        "port": 4455,
        "password": "",
        "path": "",
        "mic_input_name": "Mic/Aux",
    },
    "twitch": {
        "client_id": "",
        "client_secret": "",
        "channel": "",
        "browser_url": "https://www.twitch.tv",
        "access_token": "",
        "refresh_token": "",
    },
    "discord": {
        "bot_token": "",
        "channel_id": "",
        "announce_stream": False,
    },
    "alerts": {
        "raid": {"tts": True, "overlay": False, "overlay_source": ""},
        "follow": {"tts": True, "overlay": False, "overlay_source": ""},
        "subscribe": {"tts": True, "overlay": False, "overlay_source": ""},
        "cheer": {"tts": True, "overlay": False, "overlay_source": ""},
    },
    "games": {},
    "voice": {
        "whisper_model": "base",
        "tts_rate": 175,
        "tts_volume": 1.0,
        "tts_backend": "edge-tts",
        "listen_timeout": 5,
        "phrase_time_limit": 10,
        "naturalizer": {
            "enabled": True,
            "hesitation_rate": 0.15,
        },
    },
    "logging": {
        "level": "INFO",
        "file": "aura.log",
    },
}

# Substrings that indicate a value is still an unconfigured template placeholder.
# Checked case-insensitively against string config values.
_PLACEHOLDER_HINTS = (
    "your_",
    "your ",
    "<your",
    "changeme",
    "replace_me",
    "todo",
    "xxxx",
)


def load_config(path: str = "config.json") -> dict:
    """
    Load a JSON configuration file and return its contents as a dict.

    *path* is resolved relative to the repository root so callers do not
    need to worry about the current working directory.

    Parameters
    ----------
    path:
        Path to the JSON file, relative to the repository root.
        Defaults to ``config.json``.

    Returns
    -------
    dict
        Parsed configuration.  Returns an empty dict if the file is
        missing or contains invalid JSON.
    """
    config_path = os.path.join(_REPO_ROOT, path)

    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            config = json.load(fh)
        logger.debug("Loaded config from '%s'.", config_path)
        return config
    except FileNotFoundError:
        logger.warning("Config file not found: %s", config_path)
        return {}
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in config file '%s': %s", config_path, exc)
        return {}


def _deep_merge(base: dict, override: dict) -> dict:
    """Return a new dict that deep-merges *override* on top of *base*.

    Nested dicts are merged recursively; all other values from *override*
    take precedence over *base*.
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def validate_config(config: dict) -> dict:
    """
    Validate the configuration dict against expected keys and fill defaults.

    Missing top-level sections or individual keys are filled from
    :data:`_DEFAULTS` and a ``WARNING`` is emitted for each so that users
    know exactly what to configure.

    Values that still contain obvious template placeholders (e.g.
    ``"your_obs_websocket_password"``) are also flagged with a ``WARNING``.

    Parameters
    ----------
    config:
        Raw configuration dict (usually from :func:`load_config`).

    Returns
    -------
    dict
        Configuration dict guaranteed to contain all expected keys.
    """
    validated = {}
    for section, defaults in _DEFAULTS.items():
        user_section = config.get(section, {})
        if not isinstance(user_section, dict):
            logger.warning(
                "Config section '%s' is not a dict; using defaults.", section
            )
            user_section = {}
        merged = _deep_merge(defaults, user_section)
        # Warn about keys that still hold the empty placeholder value
        for key, default_val in defaults.items():
            value = merged.get(key)
            if default_val == "" and value == "":
                logger.warning(
                    "config.json: '%s.%s' is not set. "
                    "Some features may not work.",
                    section,
                    key,
                )
            elif isinstance(value, str) and _is_placeholder(value):
                logger.warning(
                    "config.json: '%s.%s' looks like an unconfigured placeholder (%r). "
                    "Please replace it with a real value.",
                    section,
                    key,
                    value,
                )
        validated[section] = merged

    # Preserve any extra top-level keys the user may have added
    for key, value in config.items():
        if key not in validated:
            validated[key] = value

    # Apply language setting if present
    lang = validated.get("language") or config.get("language", "en")
    if lang:
        try:
            from utils.i18n import i18n  # noqa: PLC0415
            i18n.set_language(str(lang))
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Could not set language '%s': %s", lang, exc)

    return validated


def _is_placeholder(value: str) -> bool:
    """Return True if *value* looks like an unfilled template placeholder."""
    lower = value.lower()
    return any(hint in lower for hint in _PLACEHOLDER_HINTS)
