"""
voice/wake_word.py
==================
Lightweight "AURA" wake-word detector.

The detector runs in **low-CPU idle mode**, listening for very short audio
snippets and checking whether the word "AURA" was spoken before activating
the full STT pipeline.

Detection strategy
------------------
1. **pvporcupine** (optional) – Picovoice Porcupine offline wake-word engine.
   Free tier supports a set of built-in keywords.  If the user provides a
   custom AURA model file (``voice.wake_word.porcupine_model``) it is
   preferred.  Falls through to the soft detector when unavailable.
2. **Soft detector** (default) – records a short audio snippet (≈1–2 s),
   transcribes it with the configured STT backend (Whisper ``tiny`` or
   Google), and checks whether the keyword appears in the text.  Higher
   latency than Porcupine but requires zero extra dependencies.

Configuration (``config.json``)::

    "voice": {
        "wake_word": {
            "enabled": true,
            "keyword": "aura",
            "whisper_model": "tiny",
            "porcupine_model": ""
        }
    }

Pipeline::

    Microphone (low-power snippet)
        ↓ WakeWordDetector.wait_for_wake_word()
    True / False
        ↓
    main.py activates full SpeechToText.listen()

Usage::

    detector = WakeWordDetector(config)
    while True:
        if detector.wait_for_wake_word():
            text = stt.listen()
            ...

    # Or background mode:
    detector.start_background(on_wake=lambda: print("Wake word!"))
    ...
    detector.stop_background()
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class WakeWordDetector:
    """
    Detects the "AURA" wake word with minimal CPU usage.

    Parameters
    ----------
    config:
        Validated application config dict.  Wake-word options are read from
        ``config["voice"]["wake_word"]``.
    """

    def __init__(self, config: dict) -> None:
        self._config = config
        wake_cfg: dict = config.get("voice", {}).get("wake_word", {})

        self._enabled: bool = bool(wake_cfg.get("enabled", True))
        self._keyword: str = wake_cfg.get("keyword", "aura").lower()
        self._whisper_model_name: str = wake_cfg.get("whisper_model", "tiny")
        self._porcupine_model: str = wake_cfg.get("porcupine_model", "")

        self._recognizer = None
        self._microphone = None
        self._whisper_model = None  # lazy-loaded

        self._running = False
        self._thread: Optional[threading.Thread] = None

        if self._enabled:
            self._init_audio()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_audio(self) -> None:
        """Initialise the SpeechRecognition recogniser and microphone."""
        try:
            import speech_recognition as sr  # noqa: PLC0415
            self._recognizer = sr.Recognizer()
            self._microphone = sr.Microphone()
            logger.info(
                "WakeWordDetector ready (keyword=%r, model=%s).",
                self._keyword,
                self._whisper_model_name,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("WakeWordDetector: could not init audio: %s", exc)

    def _load_whisper(self):
        """Lazy-load a small Whisper model for wake word transcription."""
        if self._whisper_model is None:
            try:
                import whisper  # noqa: PLC0415
                logger.info(
                    "WakeWordDetector: loading Whisper model '%s'…",
                    self._whisper_model_name,
                )
                self._whisper_model = whisper.load_model(self._whisper_model_name)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("WakeWordDetector: Whisper unavailable: %s", exc)
        return self._whisper_model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_enabled(self) -> bool:
        """Return True if wake word detection is enabled in config."""
        return self._enabled

    def wait_for_wake_word(self, timeout: Optional[float] = None) -> bool:
        """
        Block until the wake word is detected or *timeout* seconds elapse.

        Parameters
        ----------
        timeout:
            Maximum seconds to wait.  ``None`` means wait indefinitely.

        Returns
        -------
        bool
            ``True`` when the wake word is detected, ``False`` on timeout.
            Always returns ``True`` immediately when detection is disabled.
        """
        if not self._enabled:
            return True
        if self._recognizer is None or self._microphone is None:
            # Audio unavailable – pass through to avoid blocking forever
            return True

        deadline = (time.monotonic() + timeout) if timeout is not None else None

        while True:
            if deadline is not None and time.monotonic() >= deadline:
                return False
            try:
                audio = self._capture_snippet()
                if audio is not None and self._contains_keyword(audio):
                    logger.info("Wake word '%s' detected.", self._keyword)
                    return True
            except Exception as exc:  # pylint: disable=broad-except
                logger.debug("WakeWordDetector: listen error: %s", exc)

    def start_background(self, on_wake: Callable[[], None]) -> None:
        """
        Start a daemon thread that calls *on_wake* each time the wake word
        is detected.

        Parameters
        ----------
        on_wake:
            Callable invoked (in the background thread) whenever "AURA" is heard.
        """
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._background_loop,
            args=(on_wake,),
            daemon=True,
            name="AURA-WakeWord",
        )
        self._thread.start()
        logger.info("WakeWordDetector background thread started.")

    def stop_background(self) -> None:
        """Stop the background wake-word thread."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        logger.info("WakeWordDetector stopped.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _background_loop(self, on_wake: Callable[[], None]) -> None:
        """Continuously listen for the wake word and invoke *on_wake*."""
        while self._running:
            detected = self.wait_for_wake_word(timeout=5.0)
            if detected and self._running:
                try:
                    on_wake()
                except Exception as exc:  # pylint: disable=broad-except
                    logger.error("WakeWordDetector: on_wake callback error: %s", exc)

    def _capture_snippet(self):
        """
        Capture a short audio snippet from the microphone.

        Returns a ``speech_recognition.AudioData`` object, or ``None`` on
        timeout / error.
        """
        try:
            import speech_recognition as sr  # noqa: PLC0415
            with self._microphone as source:
                return self._recognizer.listen(
                    source,
                    timeout=2.0,
                    phrase_time_limit=2.5,
                )
        except Exception:  # pylint: disable=broad-except
            return None

    def _contains_keyword(self, audio) -> bool:
        """
        Return True if *audio* contains the wake keyword.

        Tries Porcupine first (if a model is configured), then Whisper,
        then Google STT as a final fallback.
        """
        # ── Porcupine (optional) ─────────────────────────────────────────
        if self._porcupine_model and os.path.isfile(self._porcupine_model):
            result = self._check_porcupine(audio)
            if result is not None:
                return result

        # ── Whisper (primary soft detector) ─────────────────────────────
        model = self._load_whisper()
        if model is not None:
            text = self._transcribe_whisper(audio, model)
            if text is not None:
                return self._keyword in text.lower()

        # ── Google STT fallback ──────────────────────────────────────────
        text = self._transcribe_google(audio)
        return text is not None and self._keyword in text.lower()

    def _transcribe_whisper(self, audio, model) -> Optional[str]:
        """Transcribe *audio* with Whisper and return the text."""
        tmp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
                tmp.write(audio.get_wav_data())
            result = model.transcribe(tmp_path, fp16=False)
            return result.get("text", "").strip()
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("WakeWord Whisper transcription error: %s", exc)
            return None
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    def _transcribe_google(self, audio) -> Optional[str]:
        """Transcribe *audio* with Google Web Speech API."""
        try:
            return self._recognizer.recognize_google(audio)
        except Exception:  # pylint: disable=broad-except
            return None

    def _check_porcupine(self, audio) -> Optional[bool]:
        """
        Run Porcupine on *audio*.

        Returns ``True`` if keyword detected, ``False`` if not, or ``None``
        if Porcupine is unavailable / errors out.
        """
        try:
            import pvporcupine  # noqa: PLC0415
            import struct

            porcupine = pvporcupine.create(
                keyword_paths=[self._porcupine_model],
                sensitivities=[0.7],
            )
            pcm = audio.get_raw_data(
                convert_rate=porcupine.sample_rate,
                convert_width=2,
            )
            # Process in chunks of frame_length
            frame_length = porcupine.frame_length
            num_frames = len(pcm) // (frame_length * 2)
            for i in range(num_frames):
                start = i * frame_length * 2
                frame = struct.unpack_from(f"{frame_length}h", pcm, start)
                result = porcupine.process(list(frame))
                if result >= 0:
                    porcupine.delete()
                    return True
            porcupine.delete()
            return False
        except ImportError:
            return None
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("Porcupine error: %s", exc)
            return None
