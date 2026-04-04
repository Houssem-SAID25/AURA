"""
tests/test_action_handler.py
=============================
Unit tests for core/action_handler.py.

Uses unittest.mock to patch integration dependencies so tests run without
OBS, Twitch credentials, or real game executables.
"""

from unittest.mock import MagicMock, patch

import pytest
from core.action_handler import ActionHandler

DUMMY_CONFIG: dict = {
    "obs": {"host": "localhost", "port": 4455, "password": "", "path": ""},
    "twitch": {"client_id": "", "client_secret": "", "channel": "test", "browser_url": "https://www.twitch.tv"},
    "games": {},
    "voice": {},
    "logging": {},
}


@pytest.fixture()
def handler():
    with (
        patch("integrations.obs_controller.OBSController.__init__", return_value=None),
        patch("integrations.twitch_api.TwitchAPI.__init__", return_value=None),
        patch("integrations.game_launcher.GameLauncher.__init__", return_value=None),
    ):
        h = ActionHandler.__new__(ActionHandler)
        h._config = DUMMY_CONFIG
        h._obs = MagicMock()
        h._twitch = MagicMock()
        h._launcher = MagicMock()
        # Rebuild dispatch table referencing patched attributes
        h._handlers = {
            "start_stream": h._handle_start_stream,
            "stop_stream": h._handle_stop_stream,
            "switch_scene": h._handle_switch_scene,
            "launch_obs": h._handle_launch_obs,
            "open_twitch": h._handle_open_twitch,
            "launch_game": h._handle_launch_game,
            "trending_games": h._handle_trending_games,
            "suggest_game": h._handle_suggest_game,
            "help": h._handle_help,
        }
        return h


class TestActionHandlerDispatch:
    def test_unknown_command_type(self, handler):
        response = handler.execute({"type": "nonexistent_cmd"})
        assert "don't know how to handle" in response.lower()

    def test_start_stream_success(self, handler):
        handler._obs.start_streaming.return_value = (True, "")
        response = handler.execute({"type": "start_stream"})
        assert "live" in response.lower() or "started" in response.lower()

    def test_start_stream_failure(self, handler):
        handler._obs.start_streaming.return_value = (False, "OBS not reachable")
        response = handler.execute({"type": "start_stream"})
        assert "could not" in response.lower()

    def test_stop_stream_success(self, handler):
        handler._obs.stop_streaming.return_value = (True, "")
        response = handler.execute({"type": "stop_stream"})
        assert "stopped" in response.lower() or "offline" in response.lower()

    def test_switch_scene_no_scene_name(self, handler):
        response = handler.execute({"type": "switch_scene", "scene": ""})
        assert "specify" in response.lower() or "scene name" in response.lower()

    def test_switch_scene_success(self, handler):
        handler._obs.switch_scene.return_value = (True, "")
        response = handler.execute({"type": "switch_scene", "scene": "Gameplay"})
        assert "gameplay" in response.lower() or "switched" in response.lower()

    def test_launch_game_no_name(self, handler):
        response = handler.execute({"type": "launch_game", "game": ""})
        assert "which game" in response.lower() or "tell me" in response.lower()

    def test_launch_game_success(self, handler):
        handler._launcher.launch_game.return_value = (True, "")
        response = handler.execute({"type": "launch_game", "game": "Valorant"})
        assert "launching" in response.lower() or "valorant" in response.lower()

    def test_launch_game_failure(self, handler):
        handler._launcher.launch_game.return_value = (False, "not found")
        response = handler.execute({"type": "launch_game", "game": "UnknownGame"})
        assert "could not" in response.lower() or "not found" in response.lower()

    def test_trending_games_success(self, handler):
        handler._twitch.get_top_games.return_value = [
            {"name": "Game A"}, {"name": "Game B"}, {"name": "Game C"},
            {"name": "Game D"}, {"name": "Game E"},
        ]
        response = handler.execute({"type": "trending_games"})
        assert "game a" in response.lower()
        assert "top 5" in response.lower() or "trending" in response.lower()

    def test_trending_games_empty(self, handler):
        handler._twitch.get_top_games.return_value = []
        response = handler.execute({"type": "trending_games"})
        assert "could not" in response.lower()

    def test_suggest_game_success(self, handler):
        handler._twitch.suggest_game.return_value = "Minecraft"
        response = handler.execute({"type": "suggest_game"})
        assert "minecraft" in response.lower()

    def test_suggest_game_none(self, handler):
        handler._twitch.suggest_game.return_value = None
        response = handler.execute({"type": "suggest_game"})
        assert "couldn't" in response.lower() or "could not" in response.lower()

    def test_help(self, handler):
        response = handler.execute({"type": "help"})
        assert len(response) > 0
        assert "stream" in response.lower() or "can" in response.lower()

    def test_exception_in_handler_returns_error_string(self, handler):
        handler._obs.start_streaming.side_effect = RuntimeError("boom")
        response = handler.execute({"type": "start_stream"})
        assert "wrong" in response.lower() or "error" in response.lower()
