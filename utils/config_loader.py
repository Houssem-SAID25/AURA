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

logger = logging.getLogger(__name__)

# Repository root: two levels up from this file (utils/config_loader.py)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
