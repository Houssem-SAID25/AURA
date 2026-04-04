"""
tests/test_wake_word.py
=======================
Unit tests for voice/wake_word.py – WakeWordDetector.

Audio hardware and Whisper are mocked so tests run in any CI environment.
"""

import sys
import threading
from unittest.mock import MagicMock, patch, PropertyMock
import pytest


# ---------------------------------------------------------------------------
# Mock speech_recognition and whisper before importing the module under test
# ---------------------------------------------------------------------------
if "speech_recognition" not in sys.modules:
    _mock_sr = MagicMock()
    _mock_sr.Recognizer.return_value = MagicMock()
    _mock_sr.Microphone.return_value = MagicMock()
    sys.modules["speech_recognition"] = _mock_sr

if "whisper" not in sys.modules:
    _mock_whisper = MagicMock()
    sys.modules["whisper"] = _mock_whisper


from voice.wake_word import WakeWordDetector  # noqa: E402  (after mocks)


DUMMY_CONFIG_ENABLED = {
    "voice": {
        "wake_word": {
            "enabled": True,
            "keyword": "aura",
            "whisper_model": "tiny",
            "porcupine_model": "",
        }
    }
}

DUMMY_CONFIG_DISABLED = {
    "voice": {
        "wake_word": {
            "enabled": False,
            "keyword": "aura",
        }
    }
}

DUMMY_CONFIG_DEFAULTS = {}  # should use sensible defaults


class TestWakeWordDetectorInit:
    def test_enabled_by_default(self):
        detector = WakeWordDetector(DUMMY_CONFIG_DEFAULTS)
        assert detector.is_enabled is True

    def test_disabled_when_config_false(self):
        detector = WakeWordDetector(DUMMY_CONFIG_DISABLED)
        assert detector.is_enabled is False

    def test_keyword_defaults_to_aura(self):
        detector = WakeWordDetector(DUMMY_CONFIG_DEFAULTS)
        assert detector._keyword == "aura"

    def test_custom_keyword(self):
        config = {"voice": {"wake_word": {"keyword": "jarvis"}}}
        detector = WakeWordDetector(config)
        assert detector._keyword == "jarvis"


class TestWakeWordDetectorDisabled:
    def test_wait_returns_true_immediately_when_disabled(self):
        detector = WakeWordDetector(DUMMY_CONFIG_DISABLED)
        result = detector.wait_for_wake_word(timeout=0.1)
        assert result is True

    def test_wait_returns_true_when_no_audio(self):
        # No audio initialised (mock raises on import)
        detector = WakeWordDetector(DUMMY_CONFIG_ENABLED)
        detector._recognizer = None
        detector._microphone = None
        result = detector.wait_for_wake_word(timeout=0.1)
        assert result is True


class TestWakeWordDetectorKeywordDetection:
    def setup_method(self):
        self.detector = WakeWordDetector(DUMMY_CONFIG_ENABLED)
        self.detector._recognizer = MagicMock()
        self.detector._microphone = MagicMock()
        self.detector._microphone.__enter__ = MagicMock(
            return_value=MagicMock()
        )
        self.detector._microphone.__exit__ = MagicMock(return_value=False)

    def test_contains_keyword_true_via_google(self):
        mock_audio = MagicMock()
        self.detector._recognizer.recognize_google.return_value = "hey AURA start the stream"
        result = self.detector._contains_keyword(mock_audio)
        assert result is True

    def test_contains_keyword_false_via_google(self):
        mock_audio = MagicMock()
        self.detector._recognizer.recognize_google.return_value = "hello there how are you"
        self.detector._whisper_model = None  # Skip Whisper
        result = self.detector._contains_keyword(mock_audio)
        assert result is False

    def test_contains_keyword_google_exception_returns_false(self):
        mock_audio = MagicMock()
        self.detector._recognizer.recognize_google.side_effect = Exception("no speech")
        self.detector._whisper_model = None
        result = self.detector._contains_keyword(mock_audio)
        assert result is False


class TestWakeWordDetectorWhisperFallback:
    def setup_method(self):
        self.detector = WakeWordDetector(DUMMY_CONFIG_ENABLED)
        self.detector._recognizer = MagicMock()

    def test_transcribe_whisper_returns_none_on_error(self):
        mock_audio = MagicMock()
        mock_audio.get_wav_data.side_effect = RuntimeError("no audio")
        result = self.detector._transcribe_whisper(mock_audio, MagicMock())
        assert result is None

    def test_transcribe_google_returns_none_on_error(self):
        mock_audio = MagicMock()
        self.detector._recognizer.recognize_google.side_effect = Exception("no speech")
        result = self.detector._transcribe_google(mock_audio)
        assert result is None


class TestWakeWordDetectorBackground:
    def test_start_and_stop_background_thread(self):
        detector = WakeWordDetector(DUMMY_CONFIG_DISABLED)
        called = threading.Event()

        def on_wake():
            called.set()

        # With disabled detection, on_wake should never be called
        detector.start_background(on_wake)
        assert detector._running is True
        assert detector._thread is not None
        detector.stop_background()
        assert detector._running is False

    def test_stop_background_when_not_started(self):
        detector = WakeWordDetector(DUMMY_CONFIG_DISABLED)
        # Should not raise
        detector.stop_background()
        assert detector._running is False

    def test_start_background_idempotent(self):
        detector = WakeWordDetector(DUMMY_CONFIG_DISABLED)
        on_wake = MagicMock()
        detector.start_background(on_wake)
        thread_1 = detector._thread
        detector.start_background(on_wake)  # second call should be no-op
        thread_2 = detector._thread
        assert thread_1 is thread_2  # same thread
        detector.stop_background()


class TestWakeWordDetectorTimeout:
    def test_returns_false_on_timeout(self):
        detector = WakeWordDetector(DUMMY_CONFIG_ENABLED)
        detector._recognizer = MagicMock()
        detector._microphone = MagicMock()
        # Make capture_snippet always return None (timeout)
        detector._capture_snippet = MagicMock(return_value=None)
        result = detector.wait_for_wake_word(timeout=0.05)
        assert result is False
