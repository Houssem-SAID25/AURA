"""
tests/test_session.py
======================
Unit tests for core/session.py — the AssistantSession factory.

All heavy dependencies (STT, TTS, parser, handler) are mocked so the
factory can be exercised without audio hardware or network access.
"""

from unittest.mock import MagicMock, patch

import pytest
from core.session import create_session, AssistantSession


DUMMY_CONFIG: dict = {
    "obs": {"host": "localhost", "port": 4455, "password": "", "path": ""},
    "twitch": {"client_id": "", "client_secret": "", "channel": "", "browser_url": ""},
    "games": {},
    "voice": {
        "whisper_model": "base",
        "tts_rate": 175,
        "tts_volume": 1.0,
        "listen_timeout": 5,
        "phrase_time_limit": 10,
    },
    "logging": {"level": "INFO", "file": ""},
}

# session.py uses local imports inside create_session(); patch the source modules.
_STT_PATH = "voice.speech_to_text.SpeechToText"
_TTS_PATH = "voice.text_to_speech.TextToSpeech"
_PARSER_PATH = "core.command_parser.CommandParser"
_HANDLER_PATH = "core.action_handler.ActionHandler"


class TestCreateSession:
    def test_returns_assistant_session(self):
        with (
            patch(_STT_PATH),
            patch(_TTS_PATH),
            patch(_PARSER_PATH),
            patch(_HANDLER_PATH),
        ):
            session = create_session(DUMMY_CONFIG)

        assert isinstance(session, AssistantSession)

    def test_session_contains_correct_components(self):
        stt_instance = MagicMock()
        tts_instance = MagicMock()
        parser_instance = MagicMock()
        handler_instance = MagicMock()

        with (
            patch(_STT_PATH, return_value=stt_instance),
            patch(_TTS_PATH, return_value=tts_instance),
            patch(_PARSER_PATH, return_value=parser_instance),
            patch(_HANDLER_PATH, return_value=handler_instance),
        ):
            session = create_session(DUMMY_CONFIG)

        assert session.stt is stt_instance
        assert session.tts is tts_instance
        assert session.parser is parser_instance
        assert session.handler is handler_instance

    def test_components_receive_config(self):
        with (
            patch(_STT_PATH) as mock_stt,
            patch(_TTS_PATH) as mock_tts,
            patch(_PARSER_PATH) as mock_parser,
            patch(_HANDLER_PATH) as mock_handler,
        ):
            create_session(DUMMY_CONFIG)

        mock_stt.assert_called_once_with(DUMMY_CONFIG)
        mock_tts.assert_called_once_with(DUMMY_CONFIG)
        mock_parser.assert_called_once_with(DUMMY_CONFIG)
        mock_handler.assert_called_once_with(DUMMY_CONFIG)

    def test_propagates_init_error(self):
        with (
            patch(_STT_PATH, side_effect=RuntimeError("no mic")),
        ):
            with pytest.raises(RuntimeError, match="no mic"):
                create_session(DUMMY_CONFIG)

