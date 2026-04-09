"""
voice/text_to_speech.py
=======================
Converts text to spoken audio using edge-tts (Microsoft Azure neural voices)
as the primary backend, with fallback support for legacy backends (pyttsx3,
Coqui TTS, Piper TTS).

The primary `edge-tts` backend generates audio to a temporary MP3 file and
plays it via pygame.mixer.  The optional `lang` parameter controls which
neural voice is used.

Speech rate and volume can be tuned through ``config.json``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# edge-tts voice map: lang code -> Microsoft Neural voice name
# ---------------------------------------------------------------------------
VOICES: dict[str, str] = {
    "en": "en-US-JennyNeural",
    "fr": "fr-FR-DeniseNeural",
}

# ---------------------------------------------------------------------------
# WAV phrase cache helpers (used by Coqui/Piper backends)
# ---------------------------------------------------------------------------
_CACHE_DIR = os.path.join(tempfile.gettempdir(), "aura_tts_cache")


def _cache_path(text_hash: str) -> str:
    return os.path.join(_CACHE_DIR, f"{text_hash}.wav")


def _ensure_cache_dir() -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)


def _text_hash(text: str) -> str:
    import hashlib  # noqa: PLC0415
    return hashlib.md5(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# pygame mixer helpers
# ---------------------------------------------------------------------------

_mixer_initialised = False


def _ensure_mixer() -> bool:
    """Initialise pygame.mixer if not already done. Returns True on success."""
    global _mixer_initialised
    if _mixer_initialised:
        return True
    try:
        import pygame  # noqa: PLC0415
        pygame.mixer.init()
        _mixer_initialised = True
        return True
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("pygame.mixer could not be initialised: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Async edge-tts synthesis helper
# ---------------------------------------------------------------------------

async def _synthesise_edge_tts(text: str, voice: str, output_path: str) -> None:
    """Generate speech with edge-tts and write to *output_path* (MP3)."""
    import edge_tts  # noqa: PLC0415
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


# ---------------------------------------------------------------------------
# Module-level speak() – sync wrapper (public convenience function)
# ---------------------------------------------------------------------------

def speak(text: str, lang: str = "en") -> None:
    """Speak *text* using edge-tts with the voice for *lang*.

    This is a synchronous wrapper around the async ``edge_tts.Communicate``
    API.  It generates audio to a temporary MP3 file, plays it with
    ``pygame.mixer``, then removes the file.

    Parameters
    ----------
    text:
        The text to be spoken.
    lang:
        Language code.  ``"en"`` → Jenny Neural (default),
        ``"fr"`` → Denise Neural.  Falls back to English for unknown codes.
    """
    if not text:
        return

    voice = VOICES.get(lang, VOICES["en"])
    tmp_path = os.path.join(tempfile.gettempdir(), f"aura_tts_{os.getpid()}.mp3")

    try:
        # Run async synthesis in a new event loop (sync context)
        asyncio.run(_synthesise_edge_tts(text, voice, tmp_path))

        if not _ensure_mixer():
            print(f"[AURA] {text}")
            return

        import pygame  # noqa: PLC0415
        pygame.mixer.music.load(tmp_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(50)

    except Exception as exc:  # pylint: disable=broad-except
        logger.error("edge-tts speak() failed: %s", exc)
        print(f"[AURA] {text}")
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# TextToSpeech class (keeps existing public interface)
# ---------------------------------------------------------------------------

class TextToSpeech:
    """Converts text responses to audible speech.

    Supported backends (``voice.tts_backend`` in ``config.json``):

    * ``"edge-tts"`` (default) – Microsoft Azure neural TTS via edge-tts +
      pygame; requires an internet connection.
    * ``"pyttsx3"``  – offline, cross-platform, zero extra deps (legacy).
    * ``"coqui"``    – Coqui XTTS v2 neural TTS; high quality, requires the
      ``TTS`` pip package and a downloaded model.
    * ``"piper"``    – Piper TTS binary called as a subprocess; ultra-light
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
        self._backend: str = self._voice_cfg.get("tts_backend", "edge-tts").lower()
        self._lang: str = config.get("language", "en")

        # Naturalizer settings
        nat_cfg = self._voice_cfg.get("naturalizer", {})
        self._naturalizer_enabled: bool = bool(nat_cfg.get("enabled", True))
        self._hesitation_rate: float = float(nat_cfg.get("hesitation_rate", 0.15))

        self._engine = None  # pyttsx3 engine (legacy)
        self._coqui_tts = None  # lazy-loaded Coqui TTS instance
        self._piper_binary: str = self._voice_cfg.get("piper_binary", "piper")
        self._piper_model: str = self._voice_cfg.get("piper_model", "")
        self._warmup_thread: Optional[threading.Thread] = None

        if self._backend == "pyttsx3":
            self._init_pyttsx3()
        elif self._backend == "edge-tts":
            # Warm-up mixer in background
            self._warmup_thread = threading.Thread(
                target=_ensure_mixer, daemon=True, name="AURA-TTS-Warmup"
            )
            self._warmup_thread.start()
        else:
            # Warm up non-blocking in background
            self._warmup_thread = threading.Thread(
                target=self._warmup_backend, daemon=True, name="AURA-TTS-Warmup"
            )
            self._warmup_thread.start()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_pyttsx3(self) -> None:
        """Initialise the pyttsx3 engine with configured rate and volume."""
        try:
            import pyttsx3  # noqa: PLC0415

            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self._rate)
            self._engine.setProperty("volume", self._volume)
            logger.info("TTS engine initialised (rate=%d, volume=%.1f).", self._rate, self._volume)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("pyttsx3 TTS engine could not be initialised: %s", exc)

    def _warmup_backend(self) -> None:
        """Pre-load non-primary backends in a background thread."""
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

    def speak(self, text: str, lang: str = "") -> None:
        """
        Speak the given text aloud.

        The text is passed through the naturalizer pipeline first (if enabled)
        to produce more human-like speech. Falls back to printing the text to
        stdout if the TTS engine is unavailable (e.g. headless CI environment).

        Parameters
        ----------
        text:
            The text to speak.
        lang:
            Optional language override (``"en"`` / ``"fr"``).  If empty, the
            language configured at construction time is used.
        """
        if not text:
            return

        # Apply naturalizer pipeline before speaking
        if self._naturalizer_enabled:
            from voice.voice_naturalizer import naturalize_text  # noqa: PLC0415
            text = naturalize_text(text, hesitation_rate=self._hesitation_rate)

        logger.info("AURA says: %s", text)

        effective_lang = lang or self._lang

        if self._backend == "edge-tts":
            speak(text, lang=effective_lang)
            return
        if self._backend == "coqui":
            self._speak_coqui(text)
            return
        if self._backend == "piper":
            self._speak_piper(text)
            return

        # Default legacy: pyttsx3
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
        """Update the speech rate at runtime (pyttsx3 only)."""
        self._rate = rate
        if self._engine:
            self._engine.setProperty("rate", rate)

    def set_volume(self, volume: float) -> None:
        """Update the speech volume (0.0 – 1.0) at runtime (pyttsx3 only)."""
        self._volume = max(0.0, min(1.0, volume))
        if self._engine:
            self._engine.setProperty("volume", self._volume)

    def list_voices(self) -> list[str]:
        """Return the names of available TTS voices."""
        if self._engine is None:
            return list(VOICES.values())
        voices = self._engine.getProperty("voices")
        return [v.name for v in voices] if voices else []

