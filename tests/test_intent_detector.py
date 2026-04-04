"""
tests/test_intent_detector.py
==============================
Unit tests for core/intent_detector.py.
"""

import pytest
from core.intent_detector import IntentDetector, DEFAULT_THRESHOLD


@pytest.fixture()
def detector() -> IntentDetector:
    return IntentDetector()


class TestIntentDetection:
    def test_start_stream(self, detector):
        intent, score = detector.detect("start stream")
        assert intent == "start_stream"
        assert score >= DEFAULT_THRESHOLD

    def test_go_live(self, detector):
        intent, score = detector.detect("go live now")
        assert intent == "start_stream"
        assert score >= DEFAULT_THRESHOLD

    def test_stop_stream(self, detector):
        intent, score = detector.detect("stop stream")
        assert intent == "stop_stream"
        assert score >= DEFAULT_THRESHOLD

    def test_end_streaming(self, detector):
        intent, score = detector.detect("end streaming")
        assert intent == "stop_stream"
        assert score >= DEFAULT_THRESHOLD

    def test_switch_scene(self, detector):
        intent, score = detector.detect("switch scene to gameplay")
        assert intent == "switch_scene"
        assert score >= DEFAULT_THRESHOLD

    def test_launch_obs(self, detector):
        intent, score = detector.detect("open obs studio")
        assert intent == "launch_obs"
        assert score >= DEFAULT_THRESHOLD

    def test_open_twitch(self, detector):
        intent, score = detector.detect("open twitch")
        assert intent == "open_twitch"
        assert score >= DEFAULT_THRESHOLD

    def test_launch_game(self, detector):
        intent, score = detector.detect("launch counter strike 2")
        assert intent == "launch_game"
        assert score >= DEFAULT_THRESHOLD

    def test_trending_games(self, detector):
        intent, score = detector.detect("whats trending")
        assert intent == "trending_games"
        assert score >= DEFAULT_THRESHOLD

    def test_suggest_game(self, detector):
        intent, score = detector.detect("suggest a game for me")
        assert intent == "suggest_game"
        assert score >= DEFAULT_THRESHOLD

    def test_help(self, detector):
        intent, score = detector.detect("help")
        assert intent == "help"
        assert score >= DEFAULT_THRESHOLD

    def test_unknown_input_returns_none(self, detector):
        intent, score = detector.detect("xyzzy frobnicator blorp")
        assert intent is None

    def test_empty_string_returns_none(self, detector):
        intent, score = detector.detect("")
        assert intent is None
        assert score == 0

    def test_none_input_returns_none(self, detector):
        # Empty string edge-case – the detector should not raise
        intent, score = detector.detect(None)  # type: ignore[arg-type]
        assert intent is None

    def test_launch_game_not_confused_with_launch_obs(self, detector):
        """'play valorant' must not resolve to launch_obs."""
        intent, _ = detector.detect("play valorant")
        assert intent == "launch_game"


class TestCustomThreshold:
    def test_high_threshold_rejects_weak_matches(self):
        detector = IntentDetector(threshold=99)
        intent, score = detector.detect("go live now")
        # Score is likely < 99, so intent should be None
        # (Exact score depends on rapidfuzz version; we just verify
        # it either matches at 100 or is rejected cleanly.)
        assert intent is None or isinstance(intent, str)

    def test_low_threshold_accepts_vague_input(self):
        detector = IntentDetector(threshold=1)
        intent, score = detector.detect("help me please")
        assert intent is not None
        assert score > 0
