"""
core/session.py
===============
Factory helpers for assembling the AURA voice-assistant components.

Centralising construction here removes the duplicated boilerplate that
previously existed in both ``main.py`` and ``gui/app.py``.  Both entry
points simply call :func:`create_session` and receive a ready-to-use
:class:`AssistantSession` without knowing about the individual classes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AssistantSession:
    """Container for the objects that together form a voice assistant."""

    stt: object           # SpeechToText
    tts: object           # TextToSpeech
    parser: object        # CommandParser
    handler: object       # ActionHandler
    events: Optional[object] = field(default=None)  # EventsManager (optional)


def create_session(
    config: dict,
    profile: Optional[dict] = None,
) -> AssistantSession:
    """
    Instantiate and return a fully-configured :class:`AssistantSession`.

    Parameters
    ----------
    config:
        Validated application config dict (from
        :func:`utils.config_loader.validate_config`).
    profile:
        User profile dict (from ``config/user_profile.json``).  When
        provided, the :class:`~streaming.events_manager.EventsManager` is
        initialised and attached to the session.  Pass ``None`` to skip.

    Returns
    -------
    AssistantSession
        Ready-to-use session.

    Raises
    ------
    Exception
        Propagates any initialisation error so callers can decide how to
        handle it (log and exit in CLI mode; display in GUI mode).
    """
    from voice.speech_to_text import SpeechToText  # noqa: PLC0415
    from voice.text_to_speech import TextToSpeech  # noqa: PLC0415
    from core.command_parser import CommandParser  # noqa: PLC0415
    from core.action_handler import ActionHandler  # noqa: PLC0415

    logger.info("Initialising AURA assistant session…")
    stt = SpeechToText(config)
    tts = TextToSpeech(config)
    parser = CommandParser(config)
    handler = ActionHandler(config)

    events = None
    if profile is not None:
        try:
            from streaming.events_manager import EventsManager  # noqa: PLC0415
            from integrations.obs_controller import OBSController  # noqa: PLC0415

            obs = handler._obs  # reuse the already-created OBS instance
            events = EventsManager(config, profile, tts, obs)
            logger.info("EventsManager attached to session.")
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Could not initialise EventsManager: %s", exc)

    logger.info("AURA assistant session ready.")
    return AssistantSession(stt=stt, tts=tts, parser=parser, handler=handler, events=events)
