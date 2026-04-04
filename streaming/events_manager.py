"""
streaming/events_manager.py
============================
Alert system for AURA – bridges Twitch events to TTS announcements and
optional OBS overlays.

``EventsManager`` owns a :class:`~streaming.twitch_integration.TwitchEventPoller`
instance and wires the four supported event types to built-in handler methods
that call TTS and optionally trigger OBS scene-item overlays.

Alert behaviour is configurable per-event via ``config.json`` under the
``alerts`` key::

    "alerts": {
        "raid":      {"tts": true,  "overlay": true,  "overlay_source": "RaidAlert"},
        "follow":    {"tts": true,  "overlay": false, "overlay_source": ""},
        "subscribe": {"tts": true,  "overlay": true,  "overlay_source": "SubAlert"},
        "cheer":     {"tts": true,  "overlay": false, "overlay_source": ""}
    }

Usage::

    manager = EventsManager(config, profile, tts, obs)
    manager.start()
    ...
    manager.stop()
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from streaming.twitch_integration import (
    TwitchEventPoller,
    EVENT_RAID,
    EVENT_FOLLOW,
    EVENT_SUBSCRIBE,
    EVENT_CHEER,
)

logger = logging.getLogger(__name__)


class EventsManager:
    """
    Dispatches Twitch channel events to TTS and OBS overlay actions.

    Parameters
    ----------
    config:
        Validated application config dict.
    profile:
        User profile dict (from ``config/user_profile.json``).
        May be ``None`` or empty – all features degrade gracefully.
    tts:
        A :class:`~voice.text_to_speech.TextToSpeech` instance used for
        voice announcements.
    obs:
        A :class:`~integrations.obs_controller.OBSController` instance used
        to trigger overlays.  May be ``None`` to skip overlay actions.
    """

    def __init__(
        self,
        config: dict,
        profile: Optional[dict],
        tts: Any,
        obs: Optional[Any] = None,
    ) -> None:
        self._config = config
        self._alerts_cfg: dict = config.get("alerts", {})
        self._tts = tts
        self._obs = obs

        self._poller = TwitchEventPoller(config, profile)

        # Register handlers
        self._poller.on(EVENT_RAID, self._on_raid)
        self._poller.on(EVENT_FOLLOW, self._on_follow)
        self._poller.on(EVENT_SUBSCRIBE, self._on_subscribe)
        self._poller.on(EVENT_CHEER, self._on_cheer)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start background event polling."""
        self._poller.start()

    def stop(self) -> None:
        """Stop background event polling."""
        self._poller.stop()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_raid(self, data: dict) -> None:
        raider = data.get("from_broadcaster_user_name") or data.get("user_name", "someone")
        viewer_count = data.get("viewers", 0)
        msg = (
            f"We're being raided by {raider} with {viewer_count} viewers! "
            "Welcome everyone, thanks for joining the stream!"
        )
        self._announce("raid", msg)

    def _on_follow(self, data: dict) -> None:
        user = data.get("user_name") or data.get("user_login", "someone")
        msg = f"Thanks for the follow, {user}! Welcome to the community!"
        self._announce("follow", msg)

    def _on_subscribe(self, data: dict) -> None:
        user = data.get("user_name") or data.get("user_login", "someone")
        tier_raw = data.get("tier", "1000")
        try:
            tier = int(tier_raw) // 1000
        except (ValueError, TypeError):
            tier = 1
        is_gift = data.get("is_gift", False)
        if is_gift:
            msg = f"Someone gifted a tier {tier} subscription to {user}! Big love!"
        else:
            msg = f"Big thanks to {user} for subscribing at tier {tier}! You're awesome!"
        self._announce("subscribe", msg)

    def _on_cheer(self, data: dict) -> None:
        user = data.get("user_name") or data.get("user_login", "someone")
        bits = data.get("bits", 0)
        msg = f"Thank you {user} for cheering {bits} bits! You rock!"
        self._announce("cheer", msg)

    # ------------------------------------------------------------------
    # Announce helper
    # ------------------------------------------------------------------

    def _announce(self, event_key: str, message: str) -> None:
        """Speak *message* via TTS and optionally trigger an OBS overlay."""
        alert_cfg: dict = self._alerts_cfg.get(event_key, {})

        # TTS announcement
        if alert_cfg.get("tts", True):
            try:
                self._tts.speak(message)
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("EventsManager TTS failed for '%s': %s", event_key, exc)

        # OBS overlay
        if alert_cfg.get("overlay", False) and self._obs is not None:
            source = alert_cfg.get("overlay_source", "")
            if source:
                try:
                    self._obs.trigger_overlay(source)
                except Exception as exc:  # pylint: disable=broad-except
                    logger.error(
                        "EventsManager overlay failed for '%s': %s", event_key, exc
                    )
