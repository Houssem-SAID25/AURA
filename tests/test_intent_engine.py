"""
tests/test_intent_engine.py
===========================
Unit tests for core/intent_engine.py – IntentEngine.
"""

import pytest
from core.intent_engine import IntentEngine


DUMMY_CONFIG = {
    "games": {
        "counter-strike 2": "C:\\cs2.exe",
        "valorant": "C:\\valorant.exe",
        "minecraft": "C:\\minecraft.exe",
    }
}


class TestIntentEngineAnalyze:
    def setup_method(self):
        self.engine = IntentEngine(DUMMY_CONFIG)

    def test_returns_none_for_empty(self):
        assert self.engine.analyze("") is None
        assert self.engine.analyze("   ") is None
        assert self.engine.analyze(None) is None  # type: ignore[arg-type]

    def test_returns_dict(self):
        result = self.engine.analyze("start stream")
        assert isinstance(result, dict)

    def test_start_stream_en(self):
        result = self.engine.analyze("start streaming")
        assert result is not None
        assert result["intent"] == "start_stream"

    def test_go_live_en(self):
        result = self.engine.analyze("go live")
        assert result is not None
        assert result["intent"] == "start_stream"

    def test_stop_stream_en(self):
        result = self.engine.analyze("stop stream")
        assert result is not None
        assert result["intent"] == "stop_stream"

    def test_gaming_session_with_game_and_stream_flag(self):
        result = self.engine.analyze("i'm going to stream valorant")
        assert result is not None
        assert result["intent"] in ("gaming_stream_session", "launch_game", "start_stream")
        assert result["game"] == "valorant"
        assert result["stream"] is True

    def test_french_start_stream(self):
        result = self.engine.analyze("je vais lancer le stream")
        assert result is not None
        assert result["intent"] in ("start_stream", "gaming_stream_session")

    def test_french_gaming_session(self):
        result = self.engine.analyze("je vais streamer valorant")
        assert result is not None
        assert result["stream"] is True

    def test_help_en(self):
        result = self.engine.analyze("help")
        assert result is not None
        assert result["intent"] == "help"

    def test_trending_games_en(self):
        result = self.engine.analyze("what's trending")
        assert result is not None
        assert result["intent"] == "trending_games"

    def test_suggest_game_en(self):
        result = self.engine.analyze("suggest a game")
        assert result is not None
        assert result["intent"] == "suggest_game"

    def test_mute_mic_en(self):
        result = self.engine.analyze("mute microphone")
        assert result is not None
        assert result["intent"] == "mute_mic"

    def test_unmute_mic_en(self):
        result = self.engine.analyze("unmute mic")
        assert result is not None
        assert result["intent"] == "unmute_mic"

    def test_wake_word_stripped(self):
        r1 = self.engine.analyze("AURA start stream")
        r2 = self.engine.analyze("start stream")
        # Both should detect the same intent
        assert r1 is not None
        assert r2 is not None
        assert r1["intent"] == r2["intent"]

    def test_confidence_between_0_and_1(self):
        result = self.engine.analyze("start streaming")
        assert result is not None
        assert 0.0 <= result["confidence"] <= 1.0

    def test_language_detected_fr(self):
        result = self.engine.analyze("je vais streamer")
        assert result is not None
        assert result["language"] == "fr"

    def test_language_detected_en(self):
        result = self.engine.analyze("start streaming")
        assert result is not None
        assert result["language"] == "en"

    def test_result_contains_required_keys(self):
        result = self.engine.analyze("start stream")
        assert result is not None
        for key in ("intent", "game", "scene", "stream", "confidence", "raw", "language"):
            assert key in result

    def test_game_extraction_valorant(self):
        result = self.engine.analyze("let's play valorant")
        assert result is not None
        assert result["game"] == "valorant"

    def test_game_extraction_minecraft(self):
        result = self.engine.analyze("play minecraft")
        assert result is not None
        assert result["game"] == "minecraft"

    def test_no_game_returns_empty_string(self):
        result = self.engine.analyze("start streaming")
        assert result is not None
        assert result["game"] == ""

    def test_stream_flag_false_without_stream_keyword(self):
        result = self.engine.analyze("launch game")
        # stream flag should be False if no stream keyword present
        if result:
            assert result["stream"] is False

    def test_stream_flag_true_with_stream_keyword(self):
        result = self.engine.analyze("i want to stream")
        if result:
            assert result["stream"] is True


class TestIntentEngineNoConfig:
    def test_works_without_config(self):
        engine = IntentEngine()
        result = engine.analyze("start streaming")
        assert result is not None
        assert result["intent"] == "start_stream"

    def test_works_with_empty_config(self):
        engine = IntentEngine({})
        result = engine.analyze("help")
        assert result is not None


class TestIntentEngineNormalisation:
    def setup_method(self):
        self.engine = IntentEngine()

    def test_raw_field_is_lowercase(self):
        result = self.engine.analyze("START STREAMING")
        if result:
            assert result["raw"] == result["raw"].lower()

    def test_wake_word_removed_from_raw(self):
        result = self.engine.analyze("AURA, start streaming")
        if result:
            assert "aura" not in result["raw"].split()[0]
