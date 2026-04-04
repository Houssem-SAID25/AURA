"""
voice/speech_to_text.py
=======================
Converts microphone audio to text using OpenAI Whisper.

The `SpeechToText` class uses the `speech_recognition` library to capture
audio from the default microphone and then feeds it to a local Whisper model
for transcription.  A fallback to Google Web Speech API is provided for
environments where Whisper cannot be loaded.
"""

from __future__ import annotations

import logging
import tempfile
import os
from typing import Optional

logger = logging.getLogger(__name__)


class SpeechToText:
    """Captures microphone audio and transcribes it to text using Whisper."""

    def __init__(self, config: dict) -> None:
        self._voice_cfg = config.get("voice", {})
        self._model_name: str = self._voice_cfg.get("whisper_model", "base")
        self._listen_timeout: int = int(self._voice_cfg.get("listen_timeout", 5))
        self._phrase_time_limit: int = int(
            self._voice_cfg.get("phrase_time_limit", 10)
        )
        self._whisper_model = None  # lazy-loaded on first use
        self._recognizer = None
        self._microphone = None
        self._init_recognizer()

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _init_recognizer(self) -> None:
        """Initialise the SpeechRecognition recogniser and microphone."""
        try:
            import speech_recognition as sr  # noqa: PLC0415

            self._recognizer = sr.Recognizer()
            self._microphone = sr.Microphone()
            # Calibrate ambient noise on startup
            with self._microphone as source:
                logger.info("Calibrating ambient noise… please wait.")
                self._recognizer.adjust_for_ambient_noise(source, duration=1)
            logger.info("Microphone initialised successfully.")
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Could not initialise microphone: %s", exc)

    def _load_whisper(self):
        """Lazy-load the Whisper model to avoid slow startup."""
        if self._whisper_model is None:
            try:
                import whisper  # noqa: PLC0415

                logger.info("Loading Whisper model '%s'…", self._model_name)
                self._whisper_model = whisper.load_model(self._model_name)
                logger.info("Whisper model loaded.")
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("Whisper not available: %s", exc)
        return self._whisper_model

    def preload(self) -> None:
        """
        Eagerly load the Whisper model in a background thread.

        Call this immediately after construction to overlap model loading
        with other startup tasks and eliminate the first-transcription delay.
        The model is stored on ``self._whisper_model`` and reused by
        :meth:`_load_whisper`.
        """
        import threading  # noqa: PLC0415

        t = threading.Thread(
            target=self._load_whisper,
            daemon=True,
            name="AURA-WhisperPreload",
        )
        t.start()
        logger.info("Whisper model preload started in background thread.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def listen(self) -> Optional[str]:
        """
        Listen for a single voice command and return its transcription.

        Returns ``None`` if nothing was heard or transcription failed.
        """
        if self._recognizer is None or self._microphone is None:
            logger.error("Recogniser/microphone not initialised.")
            return None

        try:
            import speech_recognition as sr  # noqa: PLC0415

            with self._microphone as source:
                logger.debug("Waiting for speech…")
                audio = self._recognizer.listen(
                    source,
                    timeout=self._listen_timeout,
                    phrase_time_limit=self._phrase_time_limit,
                )

            return self._transcribe(audio)

        except Exception as exc:  # pylint: disable=broad-except
            # sr.WaitTimeoutError is common – log at debug level
            logger.debug("Listen timeout or error: %s", exc)
            return None

    def _transcribe(self, audio) -> Optional[str]:
        """
        Transcribe captured audio.

        Attempts Whisper first; falls back to Google Web Speech API if
        Whisper is unavailable.
        """
        model = self._load_whisper()
        if model is not None:
            return self._transcribe_whisper(audio, model)
        return self._transcribe_google(audio)

    def _transcribe_whisper(self, audio, model) -> Optional[str]:
        """Transcribe using a local Whisper model."""
        try:
            # Write audio to a temporary WAV file for Whisper
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
                tmp.write(audio.get_wav_data())

            result = model.transcribe(tmp_path, fp16=False)
            text: str = result.get("text", "").strip()
            logger.debug("Whisper transcription: %s", text)
            return text if text else None
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Whisper transcription failed: %s", exc)
            return None
        finally:
            if "tmp_path" in locals() and os.path.exists(tmp_path):
                os.remove(tmp_path)

    def _transcribe_google(self, audio) -> Optional[str]:
        """Fallback transcription using Google Web Speech API."""
        try:
            import speech_recognition as sr  # noqa: PLC0415

            text = self._recognizer.recognize_google(audio)
            logger.debug("Google transcription: %s", text)
            return text.strip() if text else None
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Google transcription failed: %s", exc)
            return None
