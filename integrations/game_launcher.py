"""
integrations/game_launcher.py
==============================
Launches games and streaming tools (OBS Studio, browser) using subprocess.

Game paths are read from the ``games`` section of ``config.json``.
The OBS executable path is read from ``obs.path``.

Fuzzy matching (via `rapidfuzz`) is used so that voice commands like
"counter strike two" still match the "counter-strike 2" config key.

All public methods return a ``(success: bool, message: str)`` tuple.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from typing import Optional

logger = logging.getLogger(__name__)


class GameLauncher:
    """Launches games and applications via subprocess."""

    def __init__(self, config: dict) -> None:
        self._games: dict[str, str] = {
            k.lower(): v for k, v in config.get("games", {}).items()
        }
        self._obs_path: str = config.get("obs", {}).get("path", "")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def launch_obs(self) -> tuple[bool, str]:
        """
        Launch OBS Studio.

        Tries the configured path first; falls back to searching ``PATH``.
        """
        # Try the configured path
        if self._obs_path and os.path.isfile(self._obs_path):
            return self._launch_executable(self._obs_path, "OBS Studio")

        # Fallback: search PATH for common executable names
        for candidate in ("obs", "obs64", "obs-studio", "obs.exe"):
            found = shutil.which(candidate)
            if found:
                return self._launch_executable(found, "OBS Studio")

        msg = (
            "OBS Studio executable not found. "
            "Please update 'obs.path' in config.json."
        )
        logger.error(msg)
        return False, msg

    def launch_game(self, game_name: str) -> tuple[bool, str]:
        """
        Launch a game by name.

        *game_name* is matched against the keys in ``config.json`` using
        fuzzy matching so minor speech-recognition errors are tolerated.
        """
        if not game_name:
            return False, "No game name provided."

        matched_path, matched_key = self._find_game_path(game_name.lower())

        if matched_path is None:
            msg = (
                f"Game '{game_name}' not found in configuration. "
                "Please add its path to config.json."
            )
            logger.error(msg)
            return False, msg

        logger.info("Matched '%s' → '%s'", game_name, matched_key)
        return self._launch_executable(matched_path, matched_key)

    def launch_url(self, url: str) -> tuple[bool, str]:
        """Open a URL in the default browser."""
        try:
            import webbrowser  # noqa: PLC0415

            webbrowser.open(url)
            logger.info("Opened URL: %s", url)
            return True, ""
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Could not open URL '%s': %s", url, exc)
            return False, str(exc)

    def list_games(self) -> list[str]:
        """Return the list of game names available in the configuration."""
        return list(self._games.keys())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_game_path(self, name: str) -> tuple[Optional[str], str]:
        """
        Find the best matching game path for *name*.

        Returns ``(path, matched_key)`` or ``(None, "")`` if not found.
        """
        # Exact match first
        if name in self._games:
            return self._games[name], name

        # Fuzzy match via rapidfuzz
        try:
            from rapidfuzz import process, fuzz  # noqa: PLC0415

            result = process.extractOne(
                name,
                list(self._games.keys()),
                scorer=fuzz.token_set_ratio,
                score_cutoff=60,
            )
            if result:
                matched_key = result[0]
                return self._games[matched_key], matched_key
        except ImportError:
            # Fallback: simple substring matching
            for key in self._games:
                if key in name or name in key:
                    return self._games[key], key

        return None, ""

    @staticmethod
    def _launch_executable(path: str, display_name: str) -> tuple[bool, str]:
        """
        Launch an executable at *path* as a detached process.

        On Windows uses ``DETACHED_PROCESS`` creation flag.
        On Unix uses ``start_new_session=True``.
        """
        if not os.path.isfile(path):
            msg = f"Executable not found: {path}"
            logger.error(msg)
            return False, msg

        try:
            kwargs: dict = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.DETACHED_PROCESS
            else:
                kwargs["start_new_session"] = True

            subprocess.Popen([path], **kwargs)  # noqa: S603
            logger.info("Launched '%s' from '%s'.", display_name, path)
            return True, ""
        except PermissionError:
            msg = f"Permission denied when launching '{display_name}'."
            logger.error(msg)
            return False, msg
        except OSError as exc:
            msg = f"OS error launching '{display_name}': {exc}"
            logger.error(msg)
            return False, msg
        except Exception as exc:  # pylint: disable=broad-except
            msg = f"Unexpected error launching '{display_name}': {exc}"
            logger.error(msg)
            return False, msg
