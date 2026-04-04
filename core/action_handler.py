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

logger = logging.getLogger(__name__)

# Help text shown when the user says "help"
HELP_TEXT = (
    "I can start or stop your stream, switch OBS scenes, launch games, "
    "open Twitch, show trending games, or suggest a game for you."
)


class ActionHandler:
    """Executes commands and returns voice-response strings."""

    def __init__(self, config: dict) -> None:
        self._config = config
        self._obs = OBSController(config)
        self._twitch = TwitchAPI(config)
        self._launcher = GameLauncher(config)

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
            "help": self._handle_help,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, command: dict, raw_text: str = "") -> str:
        """
        Execute a command dict and return a spoken response.

        Parameters
        ----------
        command:  Structured command from ``CommandParser.parse()``.
        raw_text: Original transcribed text (for logging / fallback).
        """
        cmd_type: str = command.get("type", "")
        handler = self._handlers.get(cmd_type)

        if handler is None:
            logger.warning("No handler for command type: '%s'", cmd_type)
            return f"I don't know how to handle the command: {cmd_type}."

        try:
            return handler(command)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Error executing '%s': %s", cmd_type, exc, exc_info=True)
            return f"Something went wrong while executing {cmd_type}. Please check the logs."

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    def _handle_start_stream(self, command: dict) -> str:  # noqa: ARG002
        logger.info("Executing: start stream")
        success, message = self._obs.start_streaming()
        if success:
            return "Stream started! You are now live."
        return f"Could not start stream: {message}"

    def _handle_stop_stream(self, command: dict) -> str:  # noqa: ARG002
        logger.info("Executing: stop stream")
        success, message = self._obs.stop_streaming()
        if success:
            return "Stream stopped. You are now offline."
        return f"Could not stop stream: {message}"

    def _handle_switch_scene(self, command: dict) -> str:
        scene_name: str = command.get("scene", "")
        if not scene_name:
            return "Please specify a scene name, for example: switch scene to gameplay."
        logger.info("Executing: switch scene to '%s'", scene_name)
        success, message = self._obs.switch_scene(scene_name)
        if success:
            return f"Switched to scene: {scene_name}."
        return f"Could not switch scene: {message}"

    def _handle_launch_obs(self, command: dict) -> str:  # noqa: ARG002
        logger.info("Executing: launch OBS")
        success, message = self._launcher.launch_obs()
        if success:
            return "OBS Studio is launching."
        return f"Could not launch OBS: {message}"

    def _handle_open_twitch(self, command: dict) -> str:  # noqa: ARG002
        logger.info("Executing: open Twitch")
        twitch_cfg = self._config.get("twitch", {})
        channel = twitch_cfg.get("channel", "")
        url = twitch_cfg.get("browser_url", "https://www.twitch.tv")
        if channel:
            url = f"{url}/{channel}"
        try:
            webbrowser.open(url)
            return f"Opening Twitch at {url}."
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Could not open browser: %s", exc)
            return "Could not open Twitch in the browser."

    def _handle_launch_game(self, command: dict) -> str:
        game_name: str = command.get("game", "")
        if not game_name:
            return "Please tell me which game you want to play."
        logger.info("Executing: launch game '%s'", game_name)
        success, message = self._launcher.launch_game(game_name)
        if success:
            return f"Launching {game_name}. Have fun streaming!"
        return f"Could not launch {game_name}: {message}"

    def _handle_trending_games(self, command: dict) -> str:  # noqa: ARG002
        logger.info("Executing: fetch trending games")
        games = self._twitch.get_top_games(limit=5)
        if not games:
            return "Could not fetch trending games right now."
        names = ", ".join(g["name"] for g in games)
        logger.info("Top 5 trending games: %s", names)
        return f"The top 5 trending games on Twitch are: {names}."

    def _handle_suggest_game(self, command: dict) -> str:  # noqa: ARG002
        logger.info("Executing: suggest game")
        suggestion = self._twitch.suggest_game()
        if not suggestion:
            return "I couldn't find a game suggestion right now."
        return (
            f"Based on current trends, you might want to try streaming "
            f"{suggestion}. It has good viewership but isn't overly saturated."
        )

    def _handle_help(self, command: dict) -> str:  # noqa: ARG002
        return HELP_TEXT
