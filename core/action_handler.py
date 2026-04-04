"""
core/action_handler.py
======================
Executes structured commands produced by `CommandParser`.

Each command type maps to a handler method that delegates to the relevant
integration module (OBS, Twitch, GameLauncher).  All handlers return a
human-readable string that will be spoken back to the user via TTS.
"""

from __future__ import annotations

import logging
import webbrowser
from typing import Optional

from integrations.obs_controller import OBSController
from integrations.twitch_api import TwitchAPI
from integrations.game_launcher import GameLauncher
from integrations.discord_bot import DiscordNotifier
from core.i18n import t

logger = logging.getLogger(__name__)


class ActionHandler:
    """Executes commands and returns voice-response strings."""

    def __init__(self, config: dict) -> None:
        self._config = config
        self._obs = OBSController(config)
        self._twitch = TwitchAPI(config)
        self._launcher = GameLauncher(config)
        self._discord = DiscordNotifier(config)

        # Dispatch table: command type → handler method
        self._handlers: dict = {
            "start_stream": self._handle_start_stream,
            "stop_stream": self._handle_stop_stream,
            "switch_scene": self._handle_switch_scene,
            "launch_obs": self._handle_launch_obs,
            "open_twitch": self._handle_open_twitch,
            "launch_game": self._handle_launch_game,
            "trending_games": self._handle_trending_games,
            "suggest_game": self._handle_suggest_game,
            "mute_mic": self._handle_mute_mic,
            "unmute_mic": self._handle_unmute_mic,
            "trigger_overlay": self._handle_trigger_overlay,
            "help": self._handle_help,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def obs(self) -> OBSController:
        """Return the shared OBSController instance."""
        return self._obs

    def execute(self, command: dict, raw_text: str = "") -> str:
        """
        Execute a command dict and return a spoken response.

        If the command contains an ``"actions"`` list (produced by the
        :class:`~core.command_registry.CommandRegistry` for compound
        commands), each action is executed in sequence and the responses
        are joined.  Otherwise the single ``"type"`` key is dispatched.

        Parameters
        ----------
        command:  Structured command from ``CommandParser.parse()``.
        raw_text: Original transcribed text (for logging / fallback).
        """
        actions: list = command.get("actions", [])
        if actions:
            return self._execute_action_list(command, actions)

        cmd_type: str = command.get("type", "")
        handler = self._handlers.get(cmd_type)

        if handler is None:
            logger.warning("No handler for command type: '%s'", cmd_type)
            return t("responses.unknown_command", cmd_type=cmd_type)

        try:
            return handler(command)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Error executing '%s': %s", cmd_type, exc, exc_info=True)
            return t("responses.exec_failed", cmd_type=cmd_type)

    def _execute_action_list(self, command: dict, actions: list[str]) -> str:
        """
        Execute a sequence of actions from a registry command.

        Each action name must correspond to a key in the dispatch table.
        Actions that fail are logged but do not abort the sequence.

        Parameters
        ----------
        command: Full command dict (passed to each individual handler).
        actions: Ordered list of action name strings to execute.
        """
        responses: list[str] = []
        for action_name in actions:
            handler = self._handlers.get(action_name)
            if handler is None:
                logger.warning("No handler for action: '%s'", action_name)
                continue
            try:
                response = handler(command)
                responses.append(response)
                logger.debug("Action '%s' completed: %s", action_name, response)
            except Exception as exc:  # pylint: disable=broad-except
                logger.error(
                    "Error executing action '%s': %s", action_name, exc, exc_info=True
                )
        return " ".join(responses) if responses else t("responses.no_actions")

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    def _handle_start_stream(self, command: dict) -> str:  # noqa: ARG002
        logger.info("Executing: start stream")
        success, message = self._obs.start_streaming()
        if success:
            self._discord.announce_stream_live()
            return t("responses.stream_started")
        return t("responses.stream_start_failed", message=message)

    def _handle_stop_stream(self, command: dict) -> str:  # noqa: ARG002
        logger.info("Executing: stop stream")
        success, message = self._obs.stop_streaming()
        if success:
            self._discord.announce_stream_offline()
            return t("responses.stream_stopped")
        return t("responses.stream_stop_failed", message=message)

    def _handle_switch_scene(self, command: dict) -> str:
        scene_name: str = command.get("scene", "")
        if not scene_name:
            return t("responses.scene_missing")
        logger.info("Executing: switch scene to '%s'", scene_name)
        success, message = self._obs.switch_scene(scene_name)
        if success:
            return t("responses.scene_switched", scene_name=scene_name)
        return t("responses.scene_switch_failed", message=message)

    def _handle_launch_obs(self, command: dict) -> str:  # noqa: ARG002
        logger.info("Executing: launch OBS")
        success, message = self._launcher.launch_obs()
        if success:
            return t("responses.obs_launching")
        return t("responses.obs_launch_failed", message=message)

    def _handle_open_twitch(self, command: dict) -> str:  # noqa: ARG002
        logger.info("Executing: open Twitch")
        twitch_cfg = self._config.get("twitch", {})
        channel = twitch_cfg.get("channel", "")
        url = twitch_cfg.get("browser_url", "https://www.twitch.tv")
        if channel:
            url = f"{url}/{channel}"
        try:
            webbrowser.open(url)
            return t("responses.twitch_opening", url=url)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Could not open browser: %s", exc)
            return t("responses.twitch_open_failed")

    def _handle_launch_game(self, command: dict) -> str:
        game_name: str = command.get("game", "")
        if not game_name:
            return t("responses.game_missing")
        logger.info("Executing: launch game '%s'", game_name)
        success, message = self._launcher.launch_game(game_name)
        if success:
            return t("responses.game_launching", game_name=game_name)
        return t("responses.game_launch_failed", game_name=game_name, message=message)

    def _handle_trending_games(self, command: dict) -> str:  # noqa: ARG002
        logger.info("Executing: fetch trending games")
        games = self._twitch.get_top_games(limit=5)
        if not games:
            return t("responses.trending_failed")
        names = ", ".join(g["name"] for g in games)
        logger.info("Top 5 trending games: %s", names)
        return t("responses.trending_list", names=names)

    def _handle_suggest_game(self, command: dict) -> str:  # noqa: ARG002
        logger.info("Executing: suggest game")
        suggestion = self._twitch.suggest_game()
        if not suggestion:
            return t("responses.suggest_failed")
        return t("responses.suggest_game", game=suggestion)

    def _handle_help(self, command: dict) -> str:  # noqa: ARG002
        return t("responses.help")

    def _handle_mute_mic(self, command: dict) -> str:  # noqa: ARG002
        logger.info("Executing: mute microphone")
        success, message = self._obs.mute_microphone()
        if success:
            return t("responses.mic_muted")
        return t("responses.mic_mute_failed", message=message)

    def _handle_unmute_mic(self, command: dict) -> str:  # noqa: ARG002
        logger.info("Executing: unmute microphone")
        success, message = self._obs.unmute_microphone()
        if success:
            return t("responses.mic_unmuted")
        return t("responses.mic_unmute_failed", message=message)

    def _handle_trigger_overlay(self, command: dict) -> str:
        source_name: str = command.get("source", "")
        duration_ms: int = int(command.get("duration_ms", 3000))
        if not source_name:
            return t("responses.overlay_missing")
        logger.info("Executing: trigger overlay '%s' for %d ms", source_name, duration_ms)
        success, message = self._obs.trigger_overlay(source_name, duration_ms)
        if success:
            return t("responses.overlay_triggered", source_name=source_name)
        return t("responses.overlay_failed", message=message)
