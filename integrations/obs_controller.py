"""
integrations/obs_controller.py
===============================
Controls OBS Studio via the OBS WebSocket API (v5) using `obsws-python`.

Features
--------
- Start streaming
- Stop streaming
- Switch scenes
- Check if OBS is running / connected

The WebSocket host, port, and password are read from ``config.json``.
All public methods return a ``(success: bool, message: str)`` tuple so
callers can provide meaningful voice feedback without crashing.
"""

from __future__ import annotations

import logging
import subprocess
import os
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Seconds to wait before retrying a failed OBS connection.
_CONNECT_COOLDOWN = 5.0


class OBSController:
    """
    Interface to OBS Studio over WebSocket.

    Connection is established lazily on the first call that needs it.
    After a failed connection attempt a short cooldown prevents hammering the
    WebSocket server; after a mid-session error the stale client is dropped so
    the next call triggers a fresh reconnect.
    """

    def __init__(self, config: dict) -> None:
        self._obs_cfg = config.get("obs", {})
        self._host: str = self._obs_cfg.get("host", "localhost")
        self._port: int = int(self._obs_cfg.get("port", 4455))
        self._password: str = self._obs_cfg.get("password", "")
        self._obs_path: str = self._obs_cfg.get("path", "")
        self._mic_input: str = self._obs_cfg.get("mic_input_name", "Mic/Aux")
        self._client = None  # obsws_python client, connected lazily
        self._last_connect_attempt: float = 0.0  # epoch seconds

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _connect(self) -> bool:
        """
        Attempt to connect to the OBS WebSocket server.

        Returns True if already connected or the connection succeeds.
        A cooldown of :data:`_CONNECT_COOLDOWN` seconds is enforced between
        failed attempts to avoid hammering the server.
        """
        if self._client is not None:
            return True

        now = time.monotonic()
        if now - self._last_connect_attempt < _CONNECT_COOLDOWN:
            return False

        self._last_connect_attempt = now
        try:
            import obsws_python as obs  # noqa: PLC0415

            self._client = obs.ReqClient(
                host=self._host,
                port=self._port,
                password=self._password,
                timeout=3,
            )
            logger.info(
                "Connected to OBS WebSocket at %s:%d", self._host, self._port
            )
            return True
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to connect to OBS WebSocket: %s", exc)
            self._client = None
            return False

    def _disconnect(self) -> None:
        """Disconnect from the OBS WebSocket server."""
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:  # pylint: disable=broad-except
                pass
            finally:
                self._client = None

    def _invalidate_client(self) -> None:
        """Drop the cached client so the next call triggers a fresh reconnect."""
        self._client = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_running(self) -> bool:
        """Return True if a connection to OBS WebSocket can be established."""
        return self._connect()

    def start_streaming(self) -> tuple[bool, str]:
        """
        Tell OBS to start streaming.

        Returns ``(True, "")`` on success or ``(False, error_message)``.
        """
        if not self._connect():
            return False, "OBS is not running or WebSocket is not reachable."
        try:
            self._client.start_stream()
            logger.info("OBS streaming started.")
            return True, ""
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("start_stream failed: %s", exc)
            self._invalidate_client()
            return False, str(exc)

    def stop_streaming(self) -> tuple[bool, str]:
        """
        Tell OBS to stop streaming.

        Returns ``(True, "")`` on success or ``(False, error_message)``.
        """
        if not self._connect():
            return False, "OBS is not running or WebSocket is not reachable."
        try:
            self._client.stop_stream()
            logger.info("OBS streaming stopped.")
            return True, ""
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("stop_stream failed: %s", exc)
            self._invalidate_client()
            return False, str(exc)

    def switch_scene(self, scene_name: str) -> tuple[bool, str]:
        """
        Switch the active OBS scene to *scene_name*.

        Returns ``(True, "")`` on success or ``(False, error_message)``.
        """
        if not scene_name:
            return False, "Scene name must not be empty."
        if not self._connect():
            return False, "OBS is not running or WebSocket is not reachable."
        try:
            self._client.set_current_program_scene(scene_name)
            logger.info("OBS scene switched to '%s'.", scene_name)
            return True, ""
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("switch_scene failed: %s", exc)
            self._invalidate_client()
            return False, str(exc)

    def get_scenes(self) -> list[str]:
        """
        Return a list of available scene names from OBS.

        Returns an empty list if OBS is not connected.
        """
        if not self._connect():
            return []
        try:
            response = self._client.get_scene_list()
            return [s["sceneName"] for s in response.scenes]
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("get_scenes failed: %s", exc)
            self._invalidate_client()
            return []

    def get_stream_status(self) -> Optional[dict]:
        """
        Return the current streaming status from OBS.

        Returns a dict with ``outputActive`` bool on success, or ``None``.
        """
        if not self._connect():
            return None
        try:
            resp = self._client.get_stream_status()
            return {"outputActive": resp.output_active}
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("get_stream_status failed: %s", exc)
            self._invalidate_client()
            return None

    def mute_microphone(self) -> tuple[bool, str]:
        """
        Mute the configured microphone input in OBS.

        The input name is taken from ``obs.mic_input_name`` in ``config.json``
        (default: ``"Mic/Aux"``).

        Returns ``(True, "")`` on success or ``(False, error_message)``.
        """
        if not self._connect():
            return False, "OBS is not running or WebSocket is not reachable."
        try:
            self._client.set_input_mute(self._mic_input, True)
            logger.info("OBS microphone '%s' muted.", self._mic_input)
            return True, ""
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("mute_microphone failed: %s", exc)
            self._invalidate_client()
            return False, str(exc)

    def unmute_microphone(self) -> tuple[bool, str]:
        """
        Unmute the configured microphone input in OBS.

        Returns ``(True, "")`` on success or ``(False, error_message)``.
        """
        if not self._connect():
            return False, "OBS is not running or WebSocket is not reachable."
        try:
            self._client.set_input_mute(self._mic_input, False)
            logger.info("OBS microphone '%s' unmuted.", self._mic_input)
            return True, ""
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("unmute_microphone failed: %s", exc)
            self._invalidate_client()
            return False, str(exc)

    def trigger_overlay(
        self, source_name: str, duration_ms: int = 3000
    ) -> tuple[bool, str]:
        """
        Show a scene-item overlay for *duration_ms* milliseconds then hide it.

        This is useful for triggering alert overlays (raids, subscriptions, etc.)
        in the current OBS scene.

        Parameters
        ----------
        source_name:
            Name of the OBS scene item / source to show briefly.
        duration_ms:
            How long to keep the item visible, in milliseconds (default 3 000).

        Returns ``(True, "")`` on success or ``(False, error_message)``.
        """
        if not source_name:
            return False, "Source name must not be empty."
        if not self._connect():
            return False, "OBS is not running or WebSocket is not reachable."
        try:
            # Retrieve the current scene to find the scene-item ID
            scene_resp = self._client.get_current_program_scene()
            scene_name: str = scene_resp.current_program_scene_name

            items_resp = self._client.get_scene_item_list(scene_name)
            item_id: Optional[int] = None
            for item in items_resp.scene_items:
                if item.get("sourceName") == source_name:
                    item_id = item.get("sceneItemId")
                    break

            if item_id is None:
                return False, f"Source '{source_name}' not found in current scene."

            # Show the item
            self._client.set_scene_item_enabled(scene_name, item_id, True)
            logger.info("OBS overlay '%s' shown for %d ms.", source_name, duration_ms)

            # Schedule hide after duration_ms in a background thread
            def _hide():
                time.sleep(duration_ms / 1000.0)
                try:
                    self._client.set_scene_item_enabled(scene_name, item_id, False)
                    logger.info("OBS overlay '%s' hidden.", source_name)
                except Exception as hide_exc:  # pylint: disable=broad-except
                    logger.warning("Could not hide overlay '%s': %s", source_name, hide_exc)

            threading.Thread(target=_hide, daemon=True, name="AURA-OverlayHide").start()
            return True, ""
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("trigger_overlay failed: %s", exc)
            self._invalidate_client()
            return False, str(exc)
