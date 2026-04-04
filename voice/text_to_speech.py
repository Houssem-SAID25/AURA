"""
voice/text_to_speech.py
=======================
Converts text to spoken audio using pyttsx3 (offline TTS engine).

`pyttsx3` works on Windows, macOS, and Linux without an internet connection.
Speech rate and volume can be tuned through ``config.json``.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# WAV phrase cache helpers
# ---------------------------------------------------------------------------
_CACHE_DIR = os.path.join(tempfile.gettempdir(), "aura_tts_cache")


def _cache_path(text_hash: str) -> str:
    return os.path.join(_CACHE_DIR, f"{text_hash}.wav")


def _ensure_cache_dir() -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)


def _text_hash(text: str) -> str:
    import hashlib  # noqa: PLC0415
    return hashlib.md5(text.encode("utf-8")).hexdigest()


class TextToSpeech:
    """Converts text responses to audible speech.

    Supported backends (``voice.tts_backend`` in ``config.json``):

    * ``"pyttsx3"`` (default) – offline, cross-platform, zero extra deps.
    * ``"coqui"``  – Coqui XTTS v2 neural TTS; high quality, requires the
      ``TTS`` pip package and a downloaded model.
    * ``"piper"``  – Piper TTS binary called as a subprocess; ultra-light
      offline neural TTS.

    The naturalizer pipeline is applied before every utterance unless
    ``voice.naturalizer.enabled`` is ``false``.

    A simple WAV phrase cache is used for Coqui/Piper backends to avoid
    re-synthesising identical phrases.
    """

    def __init__(self, config: dict) -> None:
        self._voice_cfg = config.get("voice", {})
        self._rate: int = int(self._voice_cfg.get("tts_rate", 175))
        self._volume: float = float(self._voice_cfg.get("tts_volume", 1.0))
        self._backend: str = self._voice_cfg.get("tts_backend", "pyttsx3").lower()

        # Naturalizer settings
        nat_cfg = self._voice_cfg.get("naturalizer", {})
        self._naturalizer_enabled: bool = bool(nat_cfg.get("enabled", True))
        self._hesitation_rate: float = float(nat_cfg.get("hesitation_rate", 0.15))

        self._engine = None  # pyttsx3 engine
        self._coqui_tts = None  # lazy-loaded Coqui TTS instance
        self._piper_binary: str = self._voice_cfg.get("piper_binary", "piper")
        self._piper_model: str = self._voice_cfg.get("piper_model", "")
        self._warmup_thread: Optional[threading.Thread] = None

        if self._backend == "pyttsx3":
            self._init_engine()
        else:
            # Warm up non-blocking in background
            self._warmup_thread = threading.Thread(
                target=self._warmup_backend, daemon=True, name="AURA-TTS-Warmup"
            )
            self._warmup_thread.start()

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

    def _warmup_backend(self) -> None:
        """Pre-load non-pyttsx3 backends in a background thread."""
        try:
            if self._backend == "coqui":
                self._load_coqui()
            elif self._backend == "piper":
                logger.info("Piper TTS backend selected (binary: %s).", self._piper_binary)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("TTS backend warmup failed: %s", exc)

    def _load_coqui(self):
        """Lazy-load the Coqui TTS model (thread-safe)."""
        if self._coqui_tts is not None:
            return self._coqui_tts
        try:
            from TTS.api import TTS  # noqa: PLC0415

            model_name = self._voice_cfg.get("coqui_model", "tts_models/multilingual/multi-dataset/xtts_v2")
            logger.info("Loading Coqui TTS model '%s'…", model_name)
            self._coqui_tts = TTS(model_name=model_name, progress_bar=False)
            logger.info("Coqui TTS model loaded.")
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Coqui TTS not available: %s", exc)
        return self._coqui_tts

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def speak(self, text: str) -> None:
        """
        Speak the given text aloud.

        The text is passed through the naturalizer pipeline first (if enabled)
        to produce more human-like speech. Falls back to printing the text to
        stdout if the TTS engine is unavailable (e.g. headless CI environment).
        """
        if not text:
            return

        # Apply naturalizer pipeline before speaking
        if self._naturalizer_enabled:
            from voice.voice_naturalizer import naturalize_text  # noqa: PLC0415
            text = naturalize_text(text, hesitation_rate=self._hesitation_rate)

        logger.info("AURA says: %s", text)

        if self._backend == "coqui":
            self._speak_coqui(text)
            return
        if self._backend == "piper":
            self._speak_piper(text)
            return

        # Default: pyttsx3
        if self._engine is None:
            print(f"[AURA] {text}")
            return

        try:
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("TTS speak failed: %s", exc)
            print(f"[AURA] {text}")

    # ------------------------------------------------------------------
    # Backend-specific synthesis
    # ------------------------------------------------------------------

    def _speak_coqui(self, text: str) -> None:
        """Synthesise and play using Coqui TTS."""
        tts_model = self._load_coqui()
        if tts_model is None:
            print(f"[AURA] {text}")
            return
        try:
            _ensure_cache_dir()
            cache_file = _cache_path(_text_hash(text))
            if not os.path.exists(cache_file):
                speaker_wav = self._voice_cfg.get("coqui_speaker_wav", None)
                language = self._voice_cfg.get("coqui_language", "en")
                tts_model.tts_to_file(
                    text=text,
                    file_path=cache_file,
                    speaker_wav=speaker_wav,
                    language=language,
                )
            self._play_wav(cache_file)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Coqui TTS speak failed: %s", exc)
            print(f"[AURA] {text}")

    def _speak_piper(self, text: str) -> None:
        """Synthesise and play using the Piper TTS binary."""
        if not self._piper_model:
            logger.warning("Piper model path not configured (voice.piper_model).")
            print(f"[AURA] {text}")
            return
        try:
            _ensure_cache_dir()
            cache_file = _cache_path(_text_hash(text))
            if not os.path.exists(cache_file):
                proc = subprocess.run(
                    [self._piper_binary, "--model", self._piper_model, "--output_file", cache_file],
                    input=text.encode("utf-8"),
                    capture_output=True,
                    timeout=30,
                )
                if proc.returncode != 0:
                    raise RuntimeError(proc.stderr.decode("utf-8", errors="replace"))
            self._play_wav(cache_file)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Piper TTS speak failed: %s", exc)
            print(f"[AURA] {text}")

    @staticmethod
    def _play_wav(path: str) -> None:
        """Play a WAV file using sounddevice+soundfile, or playsound as fallback."""
        try:
            import sounddevice as sd  # noqa: PLC0415
            import soundfile as sf  # noqa: PLC0415

            data, samplerate = sf.read(path, dtype="float32")
            sd.play(data, samplerate)
            sd.wait()
        except Exception:  # pylint: disable=broad-except
            try:
                from playsound import playsound  # noqa: PLC0415
                playsound(path)
            except Exception as exc2:  # pylint: disable=broad-except
                logger.error("Could not play WAV file '%s': %s", path, exc2)

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
