"""
tests/test_command_parser.py
============================
Unit tests for core/command_parser.py.

Tests verify that the CommandParser correctly classifies voice commands
into the expected intent types and extracts entity fields.
"""

import pytest
from core.command_parser import CommandParser

DUMMY_CONFIG: dict = {}


@pytest.fixture()
def parser() -> CommandParser:
    return CommandParser(DUMMY_CONFIG)


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

class TestIntentClassification:
    def test_start_stream_exact(self, parser):
        cmd = parser.parse("start stream")
        assert cmd is not None
        assert cmd["type"] == "start_stream"

    def test_start_stream_synonym(self, parser):
        cmd = parser.parse("go live now")
        assert cmd is not None
        assert cmd["type"] == "start_stream"

    def test_stop_stream_exact(self, parser):
        cmd = parser.parse("stop stream")
        assert cmd is not None
        assert cmd["type"] == "stop_stream"

    def test_stop_stream_synonym(self, parser):
        cmd = parser.parse("end streaming")
        assert cmd is not None
        assert cmd["type"] == "stop_stream"

    def test_switch_scene(self, parser):
        cmd = parser.parse("switch scene to gameplay")
        assert cmd is not None
        assert cmd["type"] == "switch_scene"

    def test_launch_obs(self, parser):
        cmd = parser.parse("open obs studio")
        assert cmd is not None
        assert cmd["type"] == "launch_obs"

    def test_open_twitch(self, parser):
        cmd = parser.parse("open twitch")
        assert cmd is not None
        assert cmd["type"] == "open_twitch"

    def test_launch_game(self, parser):
        cmd = parser.parse("launch counter-strike 2")
        assert cmd is not None
        assert cmd["type"] == "launch_game"

    def test_launch_game_going_to_stream(self, parser):
        cmd = parser.parse("I'm going to stream Valorant")
        assert cmd is not None
        assert cmd["type"] == "launch_game"

    def test_trending_games(self, parser):
        cmd = parser.parse("what's trending")
        assert cmd is not None
        assert cmd["type"] == "trending_games"

    def test_suggest_game(self, parser):
        cmd = parser.parse("suggest a game for me")
        assert cmd is not None
        assert cmd["type"] == "suggest_game"

    def test_help(self, parser):
        cmd = parser.parse("help")
        assert cmd is not None
        assert cmd["type"] == "help"

    def test_unknown_returns_none(self, parser):
        # Very unrelated text should return None
        cmd = parser.parse("xyzzy frobnicator blorp")
        assert cmd is None

    def test_empty_string_returns_none(self, parser):
        cmd = parser.parse("")
        assert cmd is None

    def test_none_input_returns_none(self, parser):
        cmd = parser.parse(None)  # type: ignore[arg-type]
        assert cmd is None


# ---------------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------------

class TestEntityExtraction:
    def test_switch_scene_extracts_scene_name(self, parser):
        cmd = parser.parse("switch scene to gameplay")
        assert cmd is not None
        assert "scene" in cmd
        assert "gameplay" in cmd["scene"]

    def test_launch_game_extracts_game_name_launch(self, parser):
        cmd = parser.parse("launch Valorant")
        assert cmd is not None
        assert "game" in cmd
        assert "valorant" in cmd["game"].lower()

    def test_launch_game_extracts_game_name_stream(self, parser):
        cmd = parser.parse("i'm going to stream counter strike 2")
        assert cmd is not None
        assert "game" in cmd
        assert "counter strike 2" in cmd["game"]

    def test_raw_field_present(self, parser):
        cmd = parser.parse("start stream")
        assert cmd is not None
        assert "raw" in cmd
