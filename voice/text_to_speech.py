"""
voice/text_to_speech.py
=======================
Converts text to spoken audio using pyttsx3 (offline TTS engine).

`pyttsx3` works on Windows, macOS, and Linux without an internet connection.
Speech rate and volume can be tuned through ``config.json``.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TextToSpeech:
    """Converts text responses to audible speech using pyttsx3."""

    def __init__(self, config: dict) -> None:
        self._voice_cfg = config.get("voice", {})
        self._rate: int = int(self._voice_cfg.get("tts_rate", 175))
        self._volume: float = float(self._voice_cfg.get("tts_volume", 1.0))
        self._engine = None
        self._init_engine()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_engine(self) -> None:
        """Initialise the pyttsx3 engine with configured rate and volume."""
        try:
            import pyttsx3  # noqa: PLC0415

            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self._rate)
            self._engine.setProperty("volume", self._volume)
            logger.info("TTS engine initialised (rate=%d, volume=%.1f).", self._rate, self._volume)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("TTS engine could not be initialised: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def speak(self, text: str) -> None:
        """
        Speak the given text aloud.

        Falls back to printing the text to stdout if the TTS engine is
        unavailable (e.g. headless CI environment).
        """
        if not text:
            return

        logger.info("AURA says: %s", text)

        if self._engine is None:
            # Graceful degradation – print instead of crash
            print(f"[AURA] {text}")
            return

        try:
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("TTS speak failed: %s", exc)
            print(f"[AURA] {text}")

    def set_rate(self, rate: int) -> None:
        """Update the speech rate at runtime."""
        self._rate = rate
        if self._engine:
            self._engine.setProperty("rate", rate)

    def set_volume(self, volume: float) -> None:
        """Update the speech volume (0.0 – 1.0) at runtime."""
        self._volume = max(0.0, min(1.0, volume))
        if self._engine:
            self._engine.setProperty("volume", self._volume)

    def list_voices(self) -> list[str]:
        """Return the names of available TTS voices."""
        if self._engine is None:
            return []
        voices = self._engine.getProperty("voices")
        return [v.name for v in voices] if voices else []
