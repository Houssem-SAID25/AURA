"""
tests/test_events_manager.py
=============================
Unit tests for streaming/events_manager.py and streaming/twitch_integration.py.
"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from streaming.twitch_integration import (
    TwitchEventPoller,
    EVENT_RAID,
    EVENT_FOLLOW,
    EVENT_SUBSCRIBE,
    EVENT_CHEER,
)
from streaming.events_manager import EventsManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DUMMY_CONFIG = {
    "twitch": {
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
    },
    "alerts": {
        "raid": {"tts": True, "overlay": True, "overlay_source": "RaidAlert"},
        "follow": {"tts": True, "overlay": False, "overlay_source": ""},
        "subscribe": {"tts": True, "overlay": False, "overlay_source": ""},
        "cheer": {"tts": True, "overlay": False, "overlay_source": ""},
    },
}

DUMMY_PROFILE = {
    "twitch_access_token": "mock_token",
    "twitch_refresh_token": "mock_refresh",
    "twitch_user_id": "123456",
}


@pytest.fixture()
def tts_mock():
    return MagicMock()


@pytest.fixture()
def obs_mock():
    obs = MagicMock()
    obs.trigger_overlay.return_value = (True, "")
    return obs


@pytest.fixture()
def poller():
    return TwitchEventPoller(DUMMY_CONFIG, DUMMY_PROFILE)


@pytest.fixture()
def manager(tts_mock, obs_mock):
    return EventsManager(DUMMY_CONFIG, DUMMY_PROFILE, tts_mock, obs_mock)


# ---------------------------------------------------------------------------
# TwitchEventPoller – callback registration & dispatch
# ---------------------------------------------------------------------------

class TestTwitchEventPollerCallbacks:
    def test_on_registers_callback(self, poller):
        cb = MagicMock()
        poller.on(EVENT_FOLLOW, cb)
        assert cb in poller._callbacks[EVENT_FOLLOW]

    def test_fire_calls_registered_callback(self, poller):
        cb = MagicMock()
        poller.on(EVENT_FOLLOW, cb)
        poller._fire(EVENT_FOLLOW, {"user_name": "testuser"})
        cb.assert_called_once_with({"user_name": "testuser"})

    def test_fire_multiple_callbacks(self, poller):
        cb1, cb2 = MagicMock(), MagicMock()
        poller.on(EVENT_RAID, cb1)
        poller.on(EVENT_RAID, cb2)
        poller._fire(EVENT_RAID, {"from_broadcaster_user_name": "raider"})
        cb1.assert_called_once()
        cb2.assert_called_once()

    def test_fire_no_callbacks_no_error(self, poller):
        # Should not raise even when no callbacks registered
        poller._fire(EVENT_SUBSCRIBE, {"user_name": "nobody"})

    def test_callback_exception_does_not_stop_others(self, poller):
        bad_cb = MagicMock(side_effect=RuntimeError("boom"))
        good_cb = MagicMock()
        poller.on(EVENT_CHEER, bad_cb)
        poller.on(EVENT_CHEER, good_cb)
        poller._fire(EVENT_CHEER, {"user_name": "cheerer", "bits": 100})
        good_cb.assert_called_once()


class TestTwitchEventPollerStartStop:
    def test_start_requires_access_token(self):
        poller = TwitchEventPoller(DUMMY_CONFIG, {})
        poller.start()
        assert poller._thread is None  # no thread started

    def test_start_creates_thread(self, poller):
        with patch.object(poller, "_poll_loop", return_value=None):
            poller.start()
            assert poller._running is True
            assert poller._thread is not None
            poller.stop()

    def test_stop_sets_running_false(self, poller):
        with patch.object(poller, "_poll_loop", return_value=None):
            poller.start()
            poller.stop()
        assert poller._running is False

    def test_double_start_is_idempotent(self, poller):
        with patch.object(poller, "_poll_loop", return_value=None):
            poller.start()
            first_thread = poller._thread
            poller.start()
            assert poller._thread is first_thread
            poller.stop()


class TestTwitchEventPollerTokenRefresh:
    def test_refresh_returns_false_when_no_secret(self):
        poller = TwitchEventPoller({"twitch": {"client_id": "id", "client_secret": ""}}, DUMMY_PROFILE)
        assert poller._refresh_access_token() is False

    def test_refresh_updates_token_on_success(self, poller):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "new_access",
            "refresh_token": "new_refresh",
        }
        with patch.object(poller._session, "post", return_value=mock_resp):
            result = poller._refresh_access_token()
        assert result is True
        assert poller._access_token == "new_access"
        assert poller._refresh_token == "new_refresh"

    def test_refresh_returns_false_on_bad_status(self, poller):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        with patch.object(poller._session, "post", return_value=mock_resp):
            result = poller._refresh_access_token()
        assert result is False


class TestTwitchEventPollerHelixGet:
    def test_helix_get_returns_none_with_no_credentials(self):
        poller = TwitchEventPoller({"twitch": {}}, {})
        result = poller._helix_get("/test")
        assert result is None

    def test_helix_get_returns_parsed_json(self, poller):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": "1"}]}
        with patch.object(poller._session, "get", return_value=mock_resp):
            result = poller._helix_get("/channels/followers", {"broadcaster_id": "123"})
        assert result == {"data": [{"id": "1"}]}

    def test_helix_get_retries_on_401(self, poller):
        resp_401 = MagicMock()
        resp_401.status_code = 401

        resp_ok = MagicMock()
        resp_ok.status_code = 200
        resp_ok.json.return_value = {"data": []}

        with patch.object(poller._session, "get", side_effect=[resp_401, resp_ok]), \
             patch.object(poller, "_refresh_access_token", return_value=True):
            result = poller._helix_get("/test")
        assert result == {"data": []}

    def test_helix_get_returns_none_on_non_200(self, poller):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        with patch.object(poller._session, "get", return_value=mock_resp):
            result = poller._helix_get("/test")
        assert result is None

    def test_helix_get_returns_none_on_network_error(self, poller):
        with patch.object(poller._session, "get", side_effect=ConnectionError("timeout")):
            result = poller._helix_get("/test")
        assert result is None


class TestTwitchEventPollerDeduplication:
    def test_follow_fires_only_once_per_user(self, poller):
        cb = MagicMock()
        poller.on(EVENT_FOLLOW, cb)

        follow_data = {"data": [{"user_id": "999", "user_name": "fan", "user_login": "fan"}]}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = follow_data

        with patch.object(poller._session, "get", return_value=mock_resp):
            poller._poll_follows()
            poller._poll_follows()  # second poll – same user, should not re-fire

        assert cb.call_count == 1


# ---------------------------------------------------------------------------
# EventsManager – announcement logic
# ---------------------------------------------------------------------------

class TestEventsManagerAnnouncements:
    def test_on_follow_speaks(self, manager, tts_mock):
        manager._on_follow({"user_name": "CoolFan"})
        tts_mock.speak.assert_called_once()
        spoken = tts_mock.speak.call_args[0][0]
        assert "CoolFan" in spoken

    def test_on_raid_speaks(self, manager, tts_mock):
        manager._on_raid({"from_broadcaster_user_name": "BigRaider", "viewers": 150})
        tts_mock.speak.assert_called_once()
        spoken = tts_mock.speak.call_args[0][0]
        assert "BigRaider" in spoken

    def test_on_subscribe_speaks(self, manager, tts_mock):
        manager._on_subscribe({"user_name": "SubGuy", "tier": "1000", "is_gift": False})
        tts_mock.speak.assert_called_once()
        spoken = tts_mock.speak.call_args[0][0]
        assert "SubGuy" in spoken

    def test_on_cheer_speaks(self, manager, tts_mock):
        manager._on_cheer({"user_name": "BitsKing", "bits": 500})
        tts_mock.speak.assert_called_once()
        spoken = tts_mock.speak.call_args[0][0]
        assert "BitsKing" in spoken
        assert "500" in spoken

    def test_on_raid_triggers_overlay(self, manager, tts_mock, obs_mock):
        manager._on_raid({"from_broadcaster_user_name": "Raider", "viewers": 50})
        obs_mock.trigger_overlay.assert_called_once_with("RaidAlert")

    def test_follow_no_overlay_when_disabled(self, manager, tts_mock, obs_mock):
        manager._on_follow({"user_name": "Fan"})
        obs_mock.trigger_overlay.assert_not_called()

    def test_tts_exception_does_not_crash(self, manager, tts_mock):
        tts_mock.speak.side_effect = RuntimeError("engine down")
        manager._on_follow({"user_name": "Fan"})  # must not raise

    def test_overlay_exception_does_not_crash(self, manager, tts_mock, obs_mock):
        obs_mock.trigger_overlay.side_effect = RuntimeError("OBS gone")
        manager._on_raid({"from_broadcaster_user_name": "Raider", "viewers": 10})  # must not raise

    def test_no_tts_when_disabled(self, tts_mock, obs_mock):
        config = dict(DUMMY_CONFIG)
        config["alerts"] = {"follow": {"tts": False, "overlay": False}}
        mgr = EventsManager(config, DUMMY_PROFILE, tts_mock, obs_mock)
        mgr._on_follow({"user_name": "Fan"})
        tts_mock.speak.assert_not_called()


class TestEventsManagerLifecycle:
    def test_start_stop(self, manager):
        with patch.object(manager._poller, "start") as mock_start, \
             patch.object(manager._poller, "stop") as mock_stop:
            manager.start()
            mock_start.assert_called_once()
            manager.stop()
            mock_stop.assert_called_once()
