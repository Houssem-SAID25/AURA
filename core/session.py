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
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AssistantSession:
    """Container for the four objects that together form a voice assistant."""

    stt: object   # SpeechToText
    tts: object   # TextToSpeech
    parser: object   # CommandParser
    handler: object  # ActionHandler


def create_session(config: dict) -> AssistantSession:
    """
    Instantiate and return a fully-configured :class:`AssistantSession`.

    Parameters
    ----------
    config:
        Validated application config dict (from
        :func:`utils.config_loader.validate_config`).

    Returns
    -------
    AssistantSession
        Ready-to-use session containing STT, TTS, parser, and handler.

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
    logger.info("AURA assistant session ready.")
    return AssistantSession(stt=stt, tts=tts, parser=parser, handler=handler)
