"""
core/onboarding/onboarding_storage.py
======================================
Persistent storage for AURA's user-profile / onboarding data.

Profile is stored as JSON in ``config/user_profile.json`` (relative to the
repository root).  The presence of this file is the single source-of-truth
for whether onboarding has been completed.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Repository root → two levels up from this file (core/onboarding/…)
_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_PROFILE_PATH = os.path.join(_REPO_ROOT, "config", "user_profile.json")

# Accepted Twitch URL prefixes and domain for validation
_TWITCH_DOMAIN = "twitch.tv"


def profile_exists() -> bool:
    """Return ``True`` if a user profile has already been saved."""
    return os.path.isfile(_PROFILE_PATH)


def load_profile() -> dict[str, Any]:
    """Load and return the saved user profile dict.

    Returns an empty dict if the file is missing or unreadable.
    """
    if not os.path.isfile(_PROFILE_PATH):
        return {}
    try:
        with open(_PROFILE_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Could not load user profile from '%s': %s", _PROFILE_PATH, exc)
        return {}


def save_profile(profile: dict[str, Any]) -> bool:
    """Persist *profile* to ``config/user_profile.json``.

    Ensures the ``config/`` directory exists first.

    Returns
    -------
    bool
        ``True`` on success, ``False`` on any I/O failure.
    """
    config_dir = os.path.dirname(_PROFILE_PATH)
    try:
        os.makedirs(config_dir, exist_ok=True)
        with open(_PROFILE_PATH, "w", encoding="utf-8") as fh:
            json.dump(profile, fh, indent=2, ensure_ascii=False)
        logger.info("User profile saved to '%s'.", _PROFILE_PATH)
        return True
    except OSError as exc:
        logger.error("Could not save user profile to '%s': %s", _PROFILE_PATH, exc)
        return False


def build_profile(
    language: str,
    username: str,
    twitch: str = "",
    other_links: str = "",
) -> dict[str, Any]:
    """Construct the profile dict from wizard inputs."""
    return {
        "language": language,
        "username": username.strip(),
        "twitch": _normalise_twitch(twitch),
        "other_links": other_links.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "settings": {
            "voice_speed": 1.0,
            "assistant_name": "AURA",
        },
    }


def validate_twitch(value: str) -> bool:
    """Return ``True`` if *value* is a valid Twitch URL or plain username.

    Accepts:
    - Empty string (field is optional)
    - Plain alphanumeric username (letters, digits, underscores, 4-25 chars)
    - ``https://twitch.tv/<username>`` or ``https://www.twitch.tv/<username>``
    - ``http://`` variants of the above
    """
    value = value.strip()
    if not value:
        return True

    # Plain username: 4-25 alphanumeric/underscore chars
    import re  # noqa: PLC0415
    if re.fullmatch(r"[A-Za-z0-9_]{1,25}", value):
        return True

    # URL form
    lower = value.lower()
    if _TWITCH_DOMAIN in lower:
        pattern = r"^https?://(www\.)?twitch\.tv/[A-Za-z0-9_]{1,25}(/?)$"
        return bool(re.match(pattern, value, re.IGNORECASE))

    return False


def _normalise_twitch(value: str) -> str:
    """Normalise a Twitch username to a full URL, or return as-is if already a URL."""
    value = value.strip()
    if not value:
        return ""
    if value.lower().startswith("http"):
        return value
    # Plain username → full URL
    import re  # noqa: PLC0415
    if re.fullmatch(r"[A-Za-z0-9_]{1,25}", value):
        return f"https://twitch.tv/{value}"
    return value
