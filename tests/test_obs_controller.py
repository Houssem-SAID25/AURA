"""
tests/test_obs_controller.py
=============================
Unit tests for integrations/obs_controller.py.

All tests patch `obsws_python` so no real OBS instance is required.
"""

from unittest.mock import MagicMock, patch

import pytest
from integrations.obs_controller import OBSController, _CONNECT_COOLDOWN


DUMMY_CONFIG: dict = {
    "obs": {
        "host": "localhost",
        "port": 4455,
        "password": "secret",
        "path": "",
    }
}


@pytest.fixture()
def controller() -> OBSController:
    return OBSController(DUMMY_CONFIG)


def _mock_obs_client():
    """Return a fully-spec'd mock OBS ReqClient."""
    client = MagicMock()
    client.start_stream.return_value = None
    client.stop_stream.return_value = None
    client.set_current_program_scene.return_value = None
    # get_scene_list returns an object whose .scenes is a list of dicts
    scene_list = MagicMock()
    scene_list.scenes = [{"sceneName": "Gameplay"}, {"sceneName": "BRB"}]
    client.get_scene_list.return_value = scene_list
    # get_stream_status returns an object with .output_active
    status = MagicMock()
    status.output_active = True
    client.get_stream_status.return_value = status
    return client


class TestConnection:
    def test_connect_success(self, controller):
        mock_client = _mock_obs_client()
        with patch("obsws_python.ReqClient", return_value=mock_client):
            result = controller._connect()
        assert result is True
        assert controller._client is not None

    def test_connect_failure(self, controller):
        with patch("obsws_python.ReqClient", side_effect=ConnectionRefusedError("refused")):
            result = controller._connect()
        assert result is False
        assert controller._client is None

    def test_is_running_true(self, controller):
        mock_client = _mock_obs_client()
        with patch("obsws_python.ReqClient", return_value=mock_client):
            assert controller.is_running() is True

    def test_is_running_false(self, controller):
        with patch("obsws_python.ReqClient", side_effect=OSError):
            assert controller.is_running() is False

    def test_connect_cooldown_prevents_hammering(self, controller):
        """A second failed connect attempt within the cooldown returns False immediately."""
        with patch("obsws_python.ReqClient", side_effect=ConnectionRefusedError):
            controller._connect()  # first attempt — records timestamp
            result = controller._connect()  # within cooldown — should be False
        assert result is False

    def test_connect_retries_after_cooldown(self, controller, monkeypatch):
        """After the cooldown expires, a new connection attempt is made."""
        connection_error = ConnectionRefusedError

        with patch("obsws_python.ReqClient", side_effect=connection_error):
            controller._connect()

        # Force the cooldown to have already passed
        monkeypatch.setattr(
            controller, "_last_connect_attempt", 0.0
        )
        mock_client = _mock_obs_client()
        with patch("obsws_python.ReqClient", return_value=mock_client):
            result = controller._connect()
        assert result is True


class TestReconnectOnError:
    """Stale clients are invalidated when operations raise mid-session errors."""

    def test_start_stream_error_invalidates_client(self, controller):
        mock_client = _mock_obs_client()
        mock_client.start_stream.side_effect = OSError("pipe broken")
        controller._client = mock_client
        success, _ = controller.start_streaming()
        assert success is False
        assert controller._client is None

    def test_stop_stream_error_invalidates_client(self, controller):
        mock_client = _mock_obs_client()
        mock_client.stop_stream.side_effect = OSError("pipe broken")
        controller._client = mock_client
        success, _ = controller.stop_streaming()
        assert success is False
        assert controller._client is None

    def test_switch_scene_error_invalidates_client(self, controller):
        mock_client = _mock_obs_client()
        mock_client.set_current_program_scene.side_effect = OSError("pipe broken")
        controller._client = mock_client
        success, _ = controller.switch_scene("Gameplay")
        assert success is False
        assert controller._client is None

    def test_get_scenes_error_invalidates_client(self, controller):
        mock_client = _mock_obs_client()
        mock_client.get_scene_list.side_effect = OSError("pipe broken")
        controller._client = mock_client
        scenes = controller.get_scenes()
        assert scenes == []
        assert controller._client is None

    def test_get_stream_status_error_invalidates_client(self, controller):
        mock_client = _mock_obs_client()
        mock_client.get_stream_status.side_effect = OSError("pipe broken")
        controller._client = mock_client
        status = controller.get_stream_status()
        assert status is None
        assert controller._client is None


class TestStreamControl:
    def test_start_streaming_success(self, controller):
        mock_client = _mock_obs_client()
        with patch("obsws_python.ReqClient", return_value=mock_client):
            success, msg = controller.start_streaming()
        assert success is True
        assert msg == ""

    def test_start_streaming_no_obs(self, controller):
        with patch("obsws_python.ReqClient", side_effect=ConnectionRefusedError):
            success, msg = controller.start_streaming()
        assert success is False
        assert len(msg) > 0

    def test_stop_streaming_success(self, controller):
        mock_client = _mock_obs_client()
        with patch("obsws_python.ReqClient", return_value=mock_client):
            success, msg = controller.stop_streaming()
        assert success is True

    def test_stop_streaming_no_obs(self, controller):
        with patch("obsws_python.ReqClient", side_effect=ConnectionRefusedError):
            success, msg = controller.stop_streaming()
        assert success is False


class TestSceneManagement:
    def test_switch_scene_success(self, controller):
        mock_client = _mock_obs_client()
        with patch("obsws_python.ReqClient", return_value=mock_client):
            success, msg = controller.switch_scene("Gameplay")
        assert success is True
        mock_client.set_current_program_scene.assert_called_once_with("Gameplay")

    def test_switch_scene_empty_name(self, controller):
        success, msg = controller.switch_scene("")
        assert success is False

    def test_get_scenes(self, controller):
        mock_client = _mock_obs_client()
        with patch("obsws_python.ReqClient", return_value=mock_client):
            scenes = controller.get_scenes()
        assert "Gameplay" in scenes
        assert "BRB" in scenes

    def test_get_scenes_no_obs(self, controller):
        with patch("obsws_python.ReqClient", side_effect=ConnectionRefusedError):
            scenes = controller.get_scenes()
        assert scenes == []


class TestStreamStatus:
    def test_get_stream_status(self, controller):
        mock_client = _mock_obs_client()
        with patch("obsws_python.ReqClient", return_value=mock_client):
            status = controller.get_stream_status()
        assert status is not None
        assert status["outputActive"] is True

    def test_get_stream_status_no_obs(self, controller):
        with patch("obsws_python.ReqClient", side_effect=ConnectionRefusedError):
            status = controller.get_stream_status()
        assert status is None


# ---------------------------------------------------------------------------
# Mute / Unmute microphone
# ---------------------------------------------------------------------------

DUMMY_CONFIG_MIC: dict = {
    "obs": {
        "host": "localhost",
        "port": 4455,
        "password": "secret",
        "path": "",
        "mic_input_name": "Desktop Mic",
    }
}


@pytest.fixture()
def controller_mic() -> OBSController:
    return OBSController(DUMMY_CONFIG_MIC)


class TestMuteUnmute:
    def test_mute_microphone_success(self, controller_mic):
        mock_client = _mock_obs_client()
        controller_mic._client = mock_client
        success, msg = controller_mic.mute_microphone()
        assert success is True
        assert msg == ""
        mock_client.set_input_mute.assert_called_once_with("Desktop Mic", True)

    def test_unmute_microphone_success(self, controller_mic):
        mock_client = _mock_obs_client()
        controller_mic._client = mock_client
        success, msg = controller_mic.unmute_microphone()
        assert success is True
        assert msg == ""
        mock_client.set_input_mute.assert_called_once_with("Desktop Mic", False)

    def test_mute_no_obs(self, controller):
        with patch("obsws_python.ReqClient", side_effect=ConnectionRefusedError):
            success, msg = controller.mute_microphone()
        assert success is False
        assert len(msg) > 0

    def test_unmute_no_obs(self, controller):
        with patch("obsws_python.ReqClient", side_effect=ConnectionRefusedError):
            success, msg = controller.unmute_microphone()
        assert success is False

    def test_mute_error_invalidates_client(self, controller):
        mock_client = _mock_obs_client()
        mock_client.set_input_mute.side_effect = OSError("pipe broken")
        controller._client = mock_client
        success, _ = controller.mute_microphone()
        assert success is False
        assert controller._client is None

    def test_unmute_error_invalidates_client(self, controller):
        mock_client = _mock_obs_client()
        mock_client.set_input_mute.side_effect = OSError("pipe broken")
        controller._client = mock_client
        success, _ = controller.unmute_microphone()
        assert success is False
        assert controller._client is None


# ---------------------------------------------------------------------------
# Overlay triggering
# ---------------------------------------------------------------------------

class TestTriggerOverlay:
    def _mock_client_with_scene(self, scene_name="Gaming", source_name="AlertOverlay", item_id=7):
        mock_client = _mock_obs_client()
        # get_current_program_scene
        scene_resp = MagicMock()
        scene_resp.current_program_scene_name = scene_name
        mock_client.get_current_program_scene.return_value = scene_resp
        # get_scene_item_list
        items_resp = MagicMock()
        items_resp.scene_items = [
            {"sourceName": source_name, "sceneItemId": item_id},
            {"sourceName": "Background", "sceneItemId": 1},
        ]
        mock_client.get_scene_item_list.return_value = items_resp
        return mock_client

    def test_trigger_overlay_success(self, controller):
        mock_client = self._mock_client_with_scene()
        controller._client = mock_client
        success, msg = controller.trigger_overlay("AlertOverlay", duration_ms=100)
        assert success is True
        assert msg == ""
        mock_client.set_scene_item_enabled.assert_called_once_with("Gaming", 7, True)

    def test_trigger_overlay_empty_source_fails(self, controller):
        success, msg = controller.trigger_overlay("")
        assert success is False
        assert "empty" in msg.lower()

    def test_trigger_overlay_source_not_found(self, controller):
        mock_client = self._mock_client_with_scene()
        controller._client = mock_client
        success, msg = controller.trigger_overlay("NonExistentSource")
        assert success is False
        assert "not found" in msg.lower()

    def test_trigger_overlay_no_obs(self, controller):
        with patch("obsws_python.ReqClient", side_effect=ConnectionRefusedError):
            success, msg = controller.trigger_overlay("AlertOverlay")
        assert success is False

    def test_trigger_overlay_error_invalidates_client(self, controller):
        mock_client = _mock_obs_client()
        mock_client.get_current_program_scene.side_effect = OSError("pipe broken")
        controller._client = mock_client
        success, _ = controller.trigger_overlay("AlertOverlay")
        assert success is False
        assert controller._client is None

