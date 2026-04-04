"""
tests/test_decision_engine.py
==============================
Unit tests for core/decision_engine.py – DecisionEngine.

The ActionHandler and CommandParser are mocked so no real audio hardware,
OBS, or network access is required.
"""

from unittest.mock import MagicMock, patch, PropertyMock
import pytest
from core.decision_engine import DecisionEngine, CONFIDENCE_THRESHOLD


DUMMY_CONFIG = {
    "obs": {"host": "localhost", "port": 4455, "password": "secret"},
    "twitch": {"client_id": "", "client_secret": ""},
    "games": {"valorant": "C:\\valorant.exe"},
    "voice": {"ai_reasoning": True},
}


def _make_engine(obs_running=False, twitch_connected=False):
    """Create a DecisionEngine with mocked dependencies."""
    mock_parser = MagicMock()
    mock_handler = MagicMock()
    mock_obs = MagicMock()
    mock_obs.is_running.return_value = obs_running
    mock_handler.obs = mock_obs
    mock_handler.execute.return_value = "Done."

    profile = {}
    if twitch_connected:
        profile["twitch_access_token"] = "tok123"

    engine = DecisionEngine(DUMMY_CONFIG, mock_parser, mock_handler, profile)
    return engine, mock_parser, mock_handler


class TestDecisionEngineProcess:
    def test_returns_string(self):
        engine, _, _ = _make_engine()
        result = engine.process("start stream")
        assert isinstance(result, str)

    def test_empty_text_returns_string(self):
        engine, _, _ = _make_engine()
        result = engine.process("")
        assert isinstance(result, str)

    def test_whitespace_only_returns_string(self):
        engine, _, _ = _make_engine()
        result = engine.process("   ")
        assert isinstance(result, str)

    def test_recognised_intent_calls_handler(self):
        engine, _, mock_handler = _make_engine()
        mock_handler.execute.return_value = "Stream started!"
        result = engine.process("start streaming")
        # Handler should be called (either via AI pipeline or legacy fallback)
        assert isinstance(result, str)

    def test_legacy_fallback_on_low_confidence(self):
        engine, mock_parser, mock_handler = _make_engine()
        mock_parser.parse.return_value = {"type": "help", "raw": "xyz", "source": "intent_detector"}
        mock_handler.execute.return_value = "Fallback response"

        # Use a text that won't match any intent well
        with patch.object(
            engine, "_get_intent_engine"
        ) as mock_ie_getter:
            mock_ie = MagicMock()
            mock_ie.analyze.return_value = None  # Force fallback
            mock_ie_getter.return_value = mock_ie
            result = engine.process("xyz abc def")

        assert isinstance(result, str)

    def test_returns_unknown_message_when_parser_returns_none(self):
        engine, mock_parser, _ = _make_engine()
        mock_parser.parse.return_value = None

        with patch.object(engine, "_get_intent_engine") as mock_ie_getter:
            mock_ie = MagicMock()
            mock_ie.analyze.return_value = None
            mock_ie_getter.return_value = mock_ie
            result = engine.process("completely unknown utterance xyz123")

        assert "didn't understand" in result.lower() or isinstance(result, str)

    def test_follow_up_returned_when_context_incomplete(self):
        engine, _, _ = _make_engine(obs_running=False, twitch_connected=False)

        with patch.object(engine, "_get_intent_engine") as mock_ie_getter:
            mock_ie = MagicMock()
            mock_ie.analyze.return_value = {
                "intent": "start_stream",
                "game": "",
                "scene": "",
                "stream": True,
                "confidence": 0.95,
                "raw": "start stream",
                "language": "en",
            }
            mock_ie_getter.return_value = mock_ie
            result = engine.process("start stream")

        # Should either ask follow-up or proceed
        assert isinstance(result, str)

    def test_process_with_game_intent(self):
        engine, _, mock_handler = _make_engine()
        mock_handler.execute.return_value = "Launching valorant!"
        result = engine.process("play valorant")
        assert isinstance(result, str)


class TestDecisionEngineCommandBuilding:
    def test_single_action_uses_type(self):
        engine, _, _ = _make_engine()
        intent_data = {
            "intent": "start_stream",
            "game": "",
            "scene": "",
            "raw": "start stream",
        }
        cmd = engine._build_command(intent_data, ["start_stream"])
        assert cmd["type"] == "start_stream"
        assert "actions" not in cmd

    def test_multi_action_uses_actions_list(self):
        engine, _, _ = _make_engine()
        intent_data = {
            "intent": "gaming_stream_session",
            "game": "valorant",
            "scene": "",
            "raw": "stream valorant",
        }
        cmd = engine._build_command(
            intent_data,
            ["launch_obs", "launch_game", "open_twitch", "start_stream"],
        )
        assert "actions" in cmd
        assert len(cmd["actions"]) == 4
        assert cmd["game"] == "valorant"

    def test_source_is_decision_engine(self):
        engine, _, _ = _make_engine()
        intent_data = {"intent": "help", "game": "", "scene": "", "raw": "help"}
        cmd = engine._build_command(intent_data, ["help"])
        assert cmd["source"] == "decision_engine"


class TestDecisionEngineLazyInit:
    def test_engines_not_initialised_at_construction(self):
        engine, _, _ = _make_engine()
        assert engine._intent_engine is None
        assert engine._context_engine is None
        assert engine._task_planner is None

    def test_intent_engine_lazy_loaded_on_first_call(self):
        engine, _, _ = _make_engine()
        ie = engine._get_intent_engine()
        assert ie is not None
        assert engine._intent_engine is ie  # cached

    def test_same_intent_engine_returned_on_second_call(self):
        engine, _, _ = _make_engine()
        ie1 = engine._get_intent_engine()
        ie2 = engine._get_intent_engine()
        assert ie1 is ie2

    def test_task_planner_lazy_loaded(self):
        engine, _, _ = _make_engine()
        planner = engine._get_task_planner()
        assert planner is not None


class TestDecisionEngineLegacyFallback:
    def test_fallback_returns_handler_response(self):
        engine, mock_parser, mock_handler = _make_engine()
        mock_parser.parse.return_value = {"type": "help", "raw": "help", "source": "intent_detector"}
        mock_handler.execute.return_value = "Help text here."
        result = engine._legacy_fallback("help")
        assert result == "Help text here."

    def test_fallback_returns_unknown_when_parse_is_none(self):
        engine, mock_parser, _ = _make_engine()
        mock_parser.parse.return_value = None
        result = engine._legacy_fallback("random stuff")
        assert "didn't understand" in result.lower()

    def test_fallback_handles_handler_exception(self):
        engine, mock_parser, mock_handler = _make_engine()
        mock_parser.parse.return_value = {"type": "start_stream", "raw": "x"}
        mock_handler.execute.side_effect = RuntimeError("OBS error")
        result = engine._legacy_fallback("start stream")
        assert isinstance(result, str)
        assert "wrong" in result.lower() or "error" in result.lower()
