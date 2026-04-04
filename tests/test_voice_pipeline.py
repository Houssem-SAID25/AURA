"""
tests/test_voice_pipeline.py
=============================
Integration tests for the full AURA voice pipeline:

    SpeechToText  ->  CommandParser  ->  ActionHandler  ->  TextToSpeech

All external I/O (microphone, Whisper model, OBS, Twitch, game launcher,
pyttsx3 engine) is mocked so the tests are fast, offline, and reproducible.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Inject lightweight mocks for optional runtime packages that are not
# installed in the test environment (audio drivers, etc.)
# ---------------------------------------------------------------------------
if "speech_recognition" not in sys.modules:
    _sr_mock = MagicMock()
    _sr_mock.Recognizer.return_value = MagicMock()
    _sr_mock.Microphone.return_value = MagicMock()
    sys.modules["speech_recognition"] = _sr_mock

if "pyttsx3" not in sys.modules:
    _pyttsx3_mock = MagicMock()
    sys.modules["pyttsx3"] = _pyttsx3_mock

# Now safe to import the AURA modules
from core.action_handler import ActionHandler  # noqa: E402
from core.command_parser import CommandParser  # noqa: E402
from voice.speech_to_text import SpeechToText  # noqa: E402
from voice.text_to_speech import TextToSpeech  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def config() -> dict:
    return {
        "obs": {"host": "localhost", "port": 4455, "password": "pw", "path": ""},
        "twitch": {
            "client_id": "cid",
            "client_secret": "csec",
            "channel": "mychan",
            "browser_url": "https://www.twitch.tv",
        },
        "games": {"valorant": "C:\\valorant.exe"},
        "voice": {
            "whisper_model": "base",
            "tts_rate": 175,
            "tts_volume": 1.0,
            "listen_timeout": 5,
            "phrase_time_limit": 10,
        },
        "logging": {"level": "DEBUG", "file": ""},
    }


@pytest.fixture()
def parser(config) -> CommandParser:
    return CommandParser(config)


@pytest.fixture()
def handler(config) -> ActionHandler:
    return ActionHandler(config)


# ---------------------------------------------------------------------------
# SpeechToText unit tests (microphone mocked)
# ---------------------------------------------------------------------------


class TestSpeechToText:
    """Test STT with mocked speech_recognition and Whisper."""

    def test_listen_returns_none_when_recogniser_not_initialised(self, config):
        """When the recogniser fails to initialise, listen() returns None."""
        stt = SpeechToText(config)
        stt._recognizer = None  # simulate failed init
        stt._microphone = None
        result = stt.listen()
        assert result is None

    def test_whisper_transcription_success(self, config):
        """Whisper path: _transcribe_whisper returns the text from the model."""
        stt = SpeechToText.__new__(SpeechToText)
        stt._whisper_model = None

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "start stream"}

        mock_audio = MagicMock()
        mock_audio.get_wav_data.return_value = b"\x00" * 100

        with patch("tempfile.NamedTemporaryFile") as mock_tmp, patch(
            "os.path.exists", return_value=True
        ), patch("os.remove"):
            mock_tmp.return_value.__enter__.return_value.name = "/tmp/test.wav"
            result = stt._transcribe_whisper(mock_audio, mock_model)

        assert result == "start stream"

    def test_whisper_transcription_empty_returns_none(self, config):
        """An empty Whisper result returns None instead of an empty string."""
        stt = SpeechToText.__new__(SpeechToText)
        stt._whisper_model = None

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "   "}

        mock_audio = MagicMock()
        mock_audio.get_wav_data.return_value = b"\x00" * 100

        with patch("tempfile.NamedTemporaryFile") as mock_tmp, patch(
            "os.path.exists", return_value=True
        ), patch("os.remove"):
            mock_tmp.return_value.__enter__.return_value.name = "/tmp/test.wav"
            result = stt._transcribe_whisper(mock_audio, mock_model)

        assert result is None

    def test_google_fallback_on_whisper_failure(self, config):
        """When Whisper raises, _transcribe falls back to Google STT."""
        stt = SpeechToText.__new__(SpeechToText)
        stt._model_name = "base"
        stt._whisper_model = None

        mock_audio = MagicMock()

        # Make Whisper load raise so the model is unavailable
        with patch.object(stt, "_load_whisper", return_value=None), patch.object(
            stt, "_transcribe_google", return_value="stop stream"
        ) as mock_google:
            result = stt._transcribe(mock_audio)

        mock_google.assert_called_once_with(mock_audio)
        assert result == "stop stream"

    def test_transcribe_google_success(self, config):
        """Google fallback returns the recognised text."""
        stt = SpeechToText.__new__(SpeechToText)

        mock_audio = MagicMock()
        mock_recognizer = MagicMock()
        mock_recognizer.recognize_google.return_value = "open twitch"
        stt._recognizer = mock_recognizer

        result = stt._transcribe_google(mock_audio)

        assert result == "open twitch"

    def test_transcribe_google_failure_returns_none(self, config):
        """Google fallback returns None when recognition raises."""
        stt = SpeechToText.__new__(SpeechToText)

        mock_audio = MagicMock()
        mock_recognizer = MagicMock()
        mock_recognizer.recognize_google.side_effect = Exception("API error")
        stt._recognizer = mock_recognizer

        result = stt._transcribe_google(mock_audio)
        assert result is None


# ---------------------------------------------------------------------------
# TextToSpeech unit tests (pyttsx3 mocked)
# ---------------------------------------------------------------------------


class TestTextToSpeech:
    """Test TTS with mocked pyttsx3 engine."""

    def test_speak_calls_engine(self, config):
        """speak() calls pyttsx3 say() and runAndWait()."""
        mock_engine = MagicMock()
        sys.modules["pyttsx3"].init.return_value = mock_engine

        tts = TextToSpeech(config)
        tts.speak("Hello, AURA is online.")

        mock_engine.say.assert_called_once_with("Hello, AURA is online.")
        mock_engine.runAndWait.assert_called_once()

    def test_speak_graceful_when_engine_none(self, config):
        """speak() does not raise when the TTS engine failed to initialise."""
        sys.modules["pyttsx3"].init.side_effect = Exception("no audio")
        try:
            tts = TextToSpeech(config)
            # Should not raise
            tts.speak("test")
        finally:
            sys.modules["pyttsx3"].init.side_effect = None

    def test_speak_graceful_on_runtime_error(self, config):
        """speak() catches exceptions from pyttsx3 at runtime."""
        mock_engine = MagicMock()
        mock_engine.say.side_effect = RuntimeError("driver crash")
        sys.modules["pyttsx3"].init.return_value = mock_engine

        tts = TextToSpeech(config)
        # Should not raise
        tts.speak("crash test")


# ---------------------------------------------------------------------------
# Full pipeline integration: STT text -> parser -> handler -> TTS response
# ---------------------------------------------------------------------------


class TestVoicePipelineIntegration:
    """
    End-to-end pipeline tests: transcribed text -> parsed command -> response.

    All integration dependencies (OBS, Twitch, launcher, TTS) are mocked.
    """

    def _run_pipeline(
        self,
        transcribed: str,
        config: dict,
        *,
        obs_start: tuple = (True, "ok"),
        obs_stop: tuple = (True, "ok"),
    ) -> tuple[str | None, str]:
        """
        Run the parser + handler for a single transcribed utterance.

        Returns (command_type_or_none, response_string).
        """
        parser = CommandParser(config)
        handler = ActionHandler(config)

        with patch.object(handler._obs, "start_streaming", return_value=obs_start), \
             patch.object(handler._obs, "stop_streaming", return_value=obs_stop), \
             patch.object(handler._launcher, "launch_obs", return_value=(True, "ok")), \
             patch.object(handler._launcher, "launch_game", return_value=(True, "ok")), \
             patch.object(handler._twitch, "get_top_games", return_value=[
                 {"name": "Fortnite"}, {"name": "Minecraft"}, {"name": "CS2"},
                 {"name": "Valorant"}, {"name": "LoL"},
             ]), \
             patch.object(handler._twitch, "suggest_game", return_value="Rust"), \
             patch("webbrowser.open"):
            cmd = parser.parse(transcribed)
            if cmd is None:
                return None, ""
            response = handler.execute(cmd, raw_text=transcribed)
            return cmd.get("type"), response

    def test_start_stream_pipeline(self, config):
        cmd_type, response = self._run_pipeline("start stream", config)
        assert cmd_type == "start_stream"
        assert "live" in response.lower() or "started" in response.lower()

    def test_stop_stream_pipeline(self, config):
        cmd_type, response = self._run_pipeline("stop stream", config)
        assert cmd_type == "stop_stream"
        assert "stopped" in response.lower() or "offline" in response.lower()

    def test_start_stream_obs_failure_pipeline(self, config):
        cmd_type, response = self._run_pipeline(
            "go live", config, obs_start=(False, "OBS not running")
        )
        assert cmd_type == "start_stream"
        assert "could not" in response.lower()

    def test_switch_scene_pipeline(self, config):
        parser = CommandParser(config)
        handler = ActionHandler(config)

        with patch.object(
            handler._obs, "switch_scene", return_value=(True, "ok")
        ) as mock_switch:
            cmd = parser.parse("switch scene to gameplay")
            assert cmd is not None
            response = handler.execute(cmd)

        # The parser extracts the scene from after the keyword "to" or "scene";
        # "gameplay" must appear in the extracted scene name.
        call_args = mock_switch.call_args[0][0]
        assert "gameplay" in call_args

    def test_launch_game_pipeline(self, config):
        parser = CommandParser(config)
        handler = ActionHandler(config)

        with patch.object(
            handler._launcher, "launch_game", return_value=(True, "launched")
        ) as mock_launch:
            cmd = parser.parse("launch valorant")
            assert cmd is not None
            response = handler.execute(cmd)

        mock_launch.assert_called_once()
        assert "valorant" in response.lower() or "launching" in response.lower()

    def test_trending_games_pipeline(self, config):
        cmd_type, response = self._run_pipeline("what's trending", config)
        assert cmd_type == "trending_games"
        assert "fortnite" in response.lower() or "trending" in response.lower()

    def test_suggest_game_pipeline(self, config):
        cmd_type, response = self._run_pipeline("suggest a game", config)
        assert cmd_type == "suggest_game"
        assert "rust" in response.lower()

    def test_help_pipeline(self, config):
        cmd_type, response = self._run_pipeline("help", config)
        assert cmd_type == "help"
        assert len(response) > 10

    def test_unknown_command_returns_none(self, config):
        cmd_type, _ = self._run_pipeline("xyzzy frobnicator blorp", config)
        assert cmd_type is None

    def test_compound_stream_command_pipeline(self, config):
        """'stream cs2' triggers the registry multi-action command."""
        parser = CommandParser(config)
        handler = ActionHandler(config)

        with patch.object(handler._obs, "start_streaming", return_value=(True, "ok")), \
             patch.object(handler._launcher, "launch_obs", return_value=(True, "ok")), \
             patch.object(handler._launcher, "launch_game", return_value=(True, "ok")), \
             patch("webbrowser.open"):
            cmd = parser.parse("stream cs2")
            # compound commands use type "stream" (from registry)
            assert cmd is not None
            response = handler.execute(cmd, raw_text="stream cs2")

        assert isinstance(response, str) and len(response) > 0
