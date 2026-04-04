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
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Repository root → two levels up from this file (core/onboarding/…)
_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_PROFILE_PATH = os.path.join(_REPO_ROOT, "config", "user_profile.json")

# Accepted Twitch URL prefixes and domain for validation
_TWITCH_DOMAIN = "twitch.tv"

# OBS WebSocket ports to probe during auto-detection
_OBS_PROBE_PORTS = (4455, 4444)


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
    *,
    streamer_name: str = "",
    twitch_access_token: str = "",
    twitch_refresh_token: str = "",
    twitch_user_id: str = "",
    twitch_login: str = "",
    youtube_channel: str = "",
    discord_bot_token: str = "",
    discord_channel_id: str = "",
    obs_host: str = "localhost",
    obs_port: int = 4455,
    obs_password: str = "",
    obs_auto_detected_port: Optional[int] = None,
    detected_apps: Optional[dict[str, Any]] = None,
    stream_config: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Construct the profile dict from wizard inputs.

    Parameters
    ----------
    language:
        Locale code (``"en"`` or ``"fr"``).
    username:
        Nickname AURA uses to address the user.
    twitch:
        Twitch channel URL or plain username (optional).
    other_links:
        Miscellaneous links — optional (kept for backwards compatibility).
    streamer_name:
        Display name shown on-stream.  Falls back to *username* if empty.
    twitch_access_token / twitch_refresh_token / twitch_user_id / twitch_login:
        OAuth credentials obtained during Twitch setup step.
    youtube_channel:
        YouTube channel URL (optional).
    discord_bot_token / discord_channel_id:
        Discord credentials obtained during Discord setup step.
    obs_host:
        OBS WebSocket host (default ``"localhost"``).
    obs_port:
        OBS WebSocket port (default ``4455``).
    obs_password:
        OBS WebSocket password (optional).
    obs_auto_detected_port:
        OBS WebSocket port found during auto-detection (``None`` if not found).
    detected_apps:
        Structured result from the app-detection step
        (see :func:`onboarding.steps.app_detection.detect_installed_apps`).
    stream_config:
        Stream configuration dict with keys ``platform``, ``resolution``,
        ``default_scene``.
    """
    effective_obs_port = obs_port if (obs_port is not None and obs_port != 0) else (obs_auto_detected_port or 4455)
    return {
        "language": language,
        "username": username.strip(),
        "streamer_name": (streamer_name.strip() or username.strip()),
        "twitch": _normalise_twitch(twitch),
        "twitch_access_token": twitch_access_token,
        "twitch_refresh_token": twitch_refresh_token,
        "twitch_user_id": twitch_user_id,
        "twitch_login": twitch_login,
        "youtube_channel": youtube_channel.strip(),
        "discord_bot_token": discord_bot_token,
        "discord_channel_id": discord_channel_id,
        "obs_host": obs_host.strip() or "localhost",
        "obs_port": effective_obs_port,
        "obs_password": obs_password,
        "obs_auto_detected_port": obs_auto_detected_port,
        "other_links": other_links.strip(),
        "detected_apps": detected_apps or {},
        "stream_config": stream_config or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "settings": {
            "voice_speed": 1.0,
            "assistant_name": "AURA",
        },
    }


def detect_obs_port() -> Optional[int]:
    """
    Probe common OBS WebSocket ports and return the first responsive one.

    Tries ports ``4455`` (OBS 28+) then ``4444`` (legacy obs-websocket plugin).
    Returns the port number as an ``int`` if found, or ``None`` if OBS is not
    running or WebSocket is not enabled.
    """
    import socket  # noqa: PLC0415

    for port in _OBS_PROBE_PORTS:
        try:
            with socket.create_connection(("localhost", port), timeout=1.0):
                logger.info("OBS WebSocket detected on port %d.", port)
                return port
        except (OSError, ConnectionRefusedError):
            continue
    logger.debug("OBS WebSocket not detected on any probe port.")
    return None


def validate_twitch(value: str) -> bool:
    """Return ``True`` if *value* is a valid Twitch URL or plain username.

    Accepts:
    - Empty string (field is optional)
    - Plain alphanumeric username (letters, digits, underscores, 1-25 chars)
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
