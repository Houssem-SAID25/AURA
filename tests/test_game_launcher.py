"""
tests/test_game_launcher.py
============================
Unit tests for integrations/game_launcher.py.

Uses tmp_path and monkeypatching to avoid touching the real filesystem or
spawning real processes.
"""

import os
import sys
from unittest.mock import patch, MagicMock

import pytest
from integrations.game_launcher import GameLauncher


@pytest.fixture()
def fake_exe(tmp_path) -> str:
    """Create a real (empty) file to satisfy os.path.isfile checks."""
    exe = tmp_path / "game.exe"
    exe.write_text("")
    return str(exe)


@pytest.fixture()
def config(fake_exe) -> dict:
    return {
        "obs": {"path": ""},  # No OBS path configured by default
        "games": {
            "counter-strike 2": fake_exe,
            "valorant": fake_exe,
        },
    }


@pytest.fixture()
def launcher(config) -> GameLauncher:
    return GameLauncher(config)


class TestListGames:
    def test_returns_configured_games(self, launcher):
        games = launcher.list_games()
        assert "counter-strike 2" in games
        assert "valorant" in games


class TestLaunchOBS:
    def test_no_path_configured_returns_false(self, launcher):
        success, msg = launcher.launch_obs()
        assert success is False
        assert "not found" in msg.lower() or "obs" in msg.lower()

    def test_configured_path_launches(self, launcher, fake_exe):
        launcher._obs_path = fake_exe
        with patch("subprocess.Popen") as mock_popen:
            success, msg = launcher.launch_obs()
        assert success is True
        mock_popen.assert_called_once()


class TestLaunchGame:
    def test_exact_match(self, launcher):
        with patch("subprocess.Popen"):
            success, msg = launcher.launch_game("counter-strike 2")
        assert success is True

    def test_fuzzy_match(self, launcher):
        with patch("subprocess.Popen"):
            success, msg = launcher.launch_game("counter strike 2")
        assert success is True

    def test_unknown_game_returns_false(self, launcher):
        success, msg = launcher.launch_game("nonexistent game xyz")
        assert success is False
        assert "not found" in msg.lower() or "configuration" in msg.lower()

    def test_empty_name_returns_false(self, launcher):
        success, msg = launcher.launch_game("")
        assert success is False

    def test_missing_executable_returns_false(self, launcher, tmp_path):
        """Configured but non-existent exe should return False."""
        launcher._games["ghost_game"] = str(tmp_path / "ghost.exe")
        success, msg = launcher.launch_game("ghost game")
        assert success is False

    def test_popen_os_error_returns_false(self, launcher):
        with patch("subprocess.Popen", side_effect=OSError("perm denied")):
            success, msg = launcher.launch_game("valorant")
        assert success is False
        assert "os error" in msg.lower() or "error" in msg.lower()
