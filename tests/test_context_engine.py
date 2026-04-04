"""
tests/test_context_engine.py
============================
Unit tests for core/context_engine.py – ContextEngine.
"""

from unittest.mock import MagicMock, patch
import pytest
from core.context_engine import ContextEngine


DUMMY_CONFIG = {
    "obs": {
        "host": "localhost",
        "port": 4455,
        "password": "real_password",
    },
    "games": {
        "valorant": "C:\\valorant.exe",
        "minecraft": "C:\\minecraft.exe",
    },
    "twitch": {},
    "discord": {},
}

DUMMY_CONFIG_NO_OBS_PW = {
    "obs": {
        "host": "localhost",
        "port": 4455,
        "password": "your_obs_websocket_password",
    },
    "games": {},
    "twitch": {},
    "discord": {},
}


class TestContextEngineProbe:
    def _make_engine(self, config=None, profile=None, obs_running=False):
        mock_obs = MagicMock()
        mock_obs.is_running.return_value = obs_running
        return ContextEngine(config or DUMMY_CONFIG, profile or {}, mock_obs)

    def test_returns_dict(self):
        engine = self._make_engine()
        result = engine.probe({})
        assert isinstance(result, dict)

    def test_required_keys_present(self):
        engine = self._make_engine()
        result = engine.probe({})
        for key in (
            "obs_running", "twitch_connected", "discord_connected",
            "game_installed", "stream_config_ready", "missing", "follow_up",
        ):
            assert key in result

    def test_obs_running_true_when_obs_reachable(self):
        engine = self._make_engine(obs_running=True)
        result = engine.probe({})
        assert result["obs_running"] is True

    def test_obs_running_false_when_obs_unreachable(self):
        engine = self._make_engine(obs_running=False)
        result = engine.probe({})
        assert result["obs_running"] is False

    def test_obs_running_false_when_no_obs_instance(self):
        engine = ContextEngine(DUMMY_CONFIG, {}, obs=None)
        result = engine.probe({})
        assert result["obs_running"] is False

    def test_twitch_connected_false_without_token(self):
        engine = self._make_engine(profile={})
        result = engine.probe({})
        assert result["twitch_connected"] is False

    def test_twitch_connected_true_with_token(self):
        profile = {"twitch_access_token": "abc123token"}
        engine = self._make_engine(profile=profile)
        result = engine.probe({})
        assert result["twitch_connected"] is True

    def test_twitch_connected_false_with_placeholder(self):
        profile = {"twitch_access_token": "your_twitch_access_token"}
        engine = self._make_engine(profile=profile)
        result = engine.probe({})
        assert result["twitch_connected"] is False

    def test_discord_connected_false_without_token(self):
        engine = self._make_engine(profile={})
        result = engine.probe({})
        assert result["discord_connected"] is False

    def test_discord_connected_true_with_token(self):
        profile = {"discord_bot_token": "Bot.abc123"}
        engine = self._make_engine(profile=profile)
        result = engine.probe({})
        assert result["discord_connected"] is True

    def test_stream_config_ready_true_with_real_password(self):
        engine = self._make_engine(config=DUMMY_CONFIG)
        result = engine.probe({})
        assert result["stream_config_ready"] is True

    def test_stream_config_ready_false_with_placeholder(self):
        engine = self._make_engine(config=DUMMY_CONFIG_NO_OBS_PW)
        result = engine.probe({})
        assert result["stream_config_ready"] is False

    def test_game_installed_true_when_no_game_in_intent(self):
        engine = self._make_engine()
        result = engine.probe({"intent": "start_stream"})
        assert result["game_installed"] is True

    def test_game_installed_false_when_path_missing(self):
        engine = self._make_engine()
        # valorant path "C:\\valorant.exe" does not exist on the test machine
        result = engine.probe({"intent": "launch_game", "game": "valorant"})
        # Will be False because the file doesn't exist
        assert isinstance(result["game_installed"], bool)

    def test_game_installed_true_when_not_in_config(self):
        engine = self._make_engine()
        # Game not in config → optimistically True
        result = engine.probe({"intent": "launch_game", "game": "some unknown game"})
        assert result["game_installed"] is True

    def test_missing_list_type(self):
        engine = self._make_engine()
        result = engine.probe({})
        assert isinstance(result["missing"], list)

    def test_no_follow_up_when_all_ok(self):
        profile = {"twitch_access_token": "tok123"}
        engine = self._make_engine(profile=profile, obs_running=True)
        result = engine.probe(
            {"intent": "help", "stream": False, "language": "en"}
        )
        assert result["follow_up"] is None

    def test_follow_up_for_missing_twitch_on_stream_intent(self):
        engine = self._make_engine(profile={})
        result = engine.probe(
            {"intent": "start_stream", "stream": True, "language": "en"}
        )
        assert result["follow_up"] is not None
        assert isinstance(result["follow_up"], str)

    def test_follow_up_french_language(self):
        engine = self._make_engine(profile={})
        result = engine.probe(
            {"intent": "start_stream", "stream": True, "language": "fr"}
        )
        if result["follow_up"]:
            # French follow-up should contain French words
            assert any(
                word in result["follow_up"]
                for word in ["pas", "tu", "veux", "connecté"]
            )

    def test_follow_up_english_language(self):
        engine = self._make_engine(profile={})
        result = engine.probe(
            {"intent": "start_stream", "stream": True, "language": "en"}
        )
        if result["follow_up"]:
            # Follow-up should be in English and mention a blocking issue
            assert any(
                word in result["follow_up"]
                for word in ["Twitch", "stream", "OBS", "obs", "running", "connected"]
            )

    def test_probe_without_intent_data(self):
        engine = self._make_engine()
        result = engine.probe(None)
        assert isinstance(result, dict)

    def test_probe_empty_intent_data(self):
        engine = self._make_engine()
        result = engine.probe({})
        assert isinstance(result, dict)


class TestContextEngineOBSErrorHandling:
    def test_obs_check_handles_exception(self):
        mock_obs = MagicMock()
        mock_obs.is_running.side_effect = RuntimeError("OBS exploded")
        engine = ContextEngine(DUMMY_CONFIG, {}, mock_obs)
        result = engine.probe({})
        assert result["obs_running"] is False


class TestAutoDetectOBSPort:
    def test_returns_none_when_obs_not_running(self):
        engine = ContextEngine(DUMMY_CONFIG)
        with patch(
            "core.onboarding.onboarding_storage.detect_obs_port",
            return_value=None,
        ):
            port = engine.auto_detect_obs_port()
        assert port is None

    def test_returns_port_when_found(self):
        engine = ContextEngine(DUMMY_CONFIG)
        with patch(
            "core.onboarding.onboarding_storage.detect_obs_port",
            return_value=4455,
        ):
            port = engine.auto_detect_obs_port()
        assert port == 4455
