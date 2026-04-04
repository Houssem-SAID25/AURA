"""
core/context_engine.py
======================
Analyses the current environment state and determines what context is
missing before the assistant can execute an intent.

The engine probes:

* **OBS** – is it running / reachable on the WebSocket?
* **Twitch** – does the user have a valid access token stored?
* **Discord** – is a bot token configured?
* **Game** – is the requested game path configured and the executable present?
* **Stream config** – is the OBS password a real value (not the placeholder)?

When required context is absent the engine produces a bilingual follow-up
question so the assistant can prompt the user instead of failing silently.

Usage::

    ctx = ContextEngine(config, profile, obs)
    state = ctx.probe(intent_data)
    if state.get("follow_up"):
        tts.speak(state["follow_up"])
    else:
        # proceed to task planner
        ...

Returned state dict keys
------------------------
- ``obs_running``        – bool
- ``twitch_connected``   – bool
- ``discord_connected``  – bool
- ``game_installed``     – bool  (always True when no game in intent)
- ``stream_config_ready``– bool  (OBS password is non-placeholder)
- ``missing``            – list[str]  (names of missing items)
- ``follow_up``          – str | None  (question to ask the user, or None)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Follow-up question templates  (bilingual)
# ---------------------------------------------------------------------------
_FOLLOW_UPS: dict[str, dict[str, str]] = {
    "twitch_not_connected": {
        "fr": (
            "Tu n'as pas connecté ton compte Twitch. "
            "Tu veux streamer sur Twitch quand même, ou juste lancer le jeu ?"
        ),
        "en": (
            "Your Twitch account isn't connected. "
            "Do you still want to stream, or should I just launch the game?"
        ),
    },
    "obs_not_running": {
        "fr": (
            "OBS ne semble pas tourner. "
            "Tu veux que je le lance d'abord ?"
        ),
        "en": (
            "OBS doesn't seem to be running. "
            "Should I launch it first?"
        ),
    },
    "game_not_installed": {
        "fr": (
            "Je ne trouve pas ce jeu sur ton PC. "
            "Vérifie le chemin dans config.json."
        ),
        "en": (
            "I can't find that game on your PC. "
            "Please check the game path in config.json."
        ),
    },
    "obs_not_configured": {
        "fr": (
            "Le mot de passe OBS WebSocket n'est pas configuré. "
            "Ajoute-le dans config.json pour contrôler OBS."
        ),
        "en": (
            "The OBS WebSocket password isn't configured. "
            "Add it to config.json to enable OBS control."
        ),
    },
    "no_stream_platform": {
        "fr": "Tu veux streamer sur Twitch ou Discord ?",
        "en": "Do you want to stream on Twitch or Discord?",
    },
}


class ContextEngine:
    """
    Probes the current environment state for a given intent.

    Parameters
    ----------
    config:
        Validated application config dict.
    profile:
        User profile dict (from ``config/user_profile.json``).
        May be ``None`` or empty; all checks degrade gracefully.
    obs:
        A :class:`~integrations.obs_controller.OBSController` instance used
        to check if OBS is reachable.  Pass ``None`` to skip the OBS check.
    """

    def __init__(
        self,
        config: dict,
        profile: Optional[dict] = None,
        obs: Optional[Any] = None,
    ) -> None:
        self._config = config
        self._profile = profile or {}
        self._obs = obs

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def probe(self, intent_data: Optional[dict] = None) -> dict:
        """
        Analyse the environment and return a state dict.

        Parameters
        ----------
        intent_data:
            Structured intent dict from :class:`~core.intent_engine.IntentEngine`
            (or any dict with optional ``"intent"``, ``"game"``, ``"stream"``
            keys).  If ``None``, a generic state check is performed.

        Returns
        -------
        dict
            Environment state and an optional follow-up question.
        """
        intent_data = intent_data or {}
        intent = intent_data.get("intent", "")
        game = intent_data.get("game", "")
        wants_stream = intent_data.get("stream", False)
        language = intent_data.get("language", "en")

        # Run checks
        obs_running = self._check_obs()
        twitch_connected = self._check_twitch()
        discord_connected = self._check_discord()
        game_installed = self._check_game(game) if game else True
        stream_ready = self._check_stream_config()

        missing: list[str] = []
        if not obs_running:
            missing.append("obs_not_running")
        if not stream_ready:
            missing.append("obs_not_configured")
        if wants_stream and not twitch_connected:
            missing.append("twitch_not_connected")
        if game and not game_installed:
            missing.append("game_not_installed")

        follow_up = self._build_follow_up(missing, intent, language)

        state = {
            "obs_running": obs_running,
            "twitch_connected": twitch_connected,
            "discord_connected": discord_connected,
            "game_installed": game_installed,
            "stream_config_ready": stream_ready,
            "missing": missing,
            "follow_up": follow_up,
        }

        logger.debug("ContextEngine state: %s", state)
        return state

    def auto_detect_obs_port(self) -> Optional[int]:
        """
        Probe localhost for an active OBS WebSocket and return the port.

        Checks port 4455 (OBS 28+) first, then 4444 (legacy).
        Returns ``None`` if OBS is not reachable on either port.

        This is used by the onboarding flow to populate
        ``config/user_profile.json`` without prompting.
        """
        from core.onboarding.onboarding_storage import detect_obs_port  # noqa: PLC0415
        return detect_obs_port()

    # ------------------------------------------------------------------
    # Private check helpers
    # ------------------------------------------------------------------

    def _check_obs(self) -> bool:
        """Return True if OBS WebSocket is reachable."""
        if self._obs is None:
            return False
        try:
            return bool(self._obs.is_running())
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("OBS check failed: %s", exc)
            return False

    def _check_twitch(self) -> bool:
        """Return True if a Twitch access token is stored in the profile."""
        token = self._profile.get("twitch_access_token", "")
        return bool(token and token not in ("", "your_twitch_access_token"))

    def _check_discord(self) -> bool:
        """Return True if a Discord bot token is configured."""
        token = self._profile.get("discord_bot_token", "")
        return bool(token and token not in ("", "your_discord_bot_token"))

    def _check_game(self, game_name: str) -> bool:
        """
        Return True if the game executable path is configured and exists.

        Falls back to True when no path is configured (platform may handle
        launch differently, e.g. Steam URI).
        """
        games_cfg: dict = self._config.get("games", {})
        # Find a matching key (case-insensitive partial match)
        path = ""
        for key, val in games_cfg.items():
            if game_name.lower() in key.lower() or key.lower() in game_name.lower():
                path = val
                break

        if not path:
            # Game not in config – optimistically allow (may still launch via Steam)
            return True

        # If path starts with "steam://" it's always valid
        if path.lower().startswith("steam://"):
            return True

        return os.path.isfile(path)

    def _check_stream_config(self) -> bool:
        """Return True if OBS password looks like a real value."""
        obs_cfg = self._config.get("obs", {})
        password = obs_cfg.get("password", "")
        return bool(password and password not in ("", "your_obs_websocket_password"))

    # ------------------------------------------------------------------
    # Follow-up question builder
    # ------------------------------------------------------------------

    def _build_follow_up(
        self,
        missing: list[str],
        intent: str,
        language: str,
    ) -> Optional[str]:
        """
        Return a follow-up question for the first critical missing item,
        or ``None`` if everything is in order.

        Only items that would *block* execution trigger a follow-up.
        Informational warnings (like OBS not configured) are not surfaced
        as questions unless streaming is the intent.
        """
        blocking_intents = {
            "start_stream", "gaming_stream_session", "stop_stream",
            "switch_scene", "launch_obs", "trigger_overlay",
        }
        is_streaming_intent = intent in blocking_intents

        for item in missing:
            # Only report obs/stream issues when relevant
            if item == "obs_not_running" and not is_streaming_intent:
                continue
            if item == "obs_not_configured" and not is_streaming_intent:
                continue
            if item in _FOLLOW_UPS:
                lang = language if language in ("fr", "en") else "en"
                return _FOLLOW_UPS[item][lang]

        return None
