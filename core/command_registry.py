"""
core/command_registry.py
========================
Dynamic command registry for AURA.

Commands are defined in ``config/commands.json`` and loaded at startup.
Each registry entry maps a set of trigger keywords to a sequence of
actions, enabling compound voice automations — e.g. "stream CS2" can
trigger ``launch_obs``, ``launch_game``, and ``open_twitch`` in one
utterance.

Registry schema
---------------
.. code-block:: json

    {
        "stream_cs2": {
            "description": "Launch full streaming setup for CS2",
            "keywords": ["stream cs2", "stream counter strike 2"],
            "intent": "stream",
            "game": "counter-strike 2",
            "actions": ["launch_obs", "launch_game", "open_twitch"]
        }
    }

When a command is matched, the registry returns a structured dict that
``ActionHandler`` can execute directly.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Default path to the commands JSON file, relative to the repo root.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_REGISTRY_PATH = os.path.join(_REPO_ROOT, "config", "commands.json")


class CommandRegistry:
    """
    Loads and queries the dynamic command registry.

    The registry is loaded once at construction time.  Call
    :meth:`reload` to pick up changes to the JSON file at runtime.
    """

    def __init__(self, registry_path: str = DEFAULT_REGISTRY_PATH) -> None:
        self._path = registry_path
        self._commands: dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reload(self) -> None:
        """Reload the registry from disk."""
        self._load()

    def match(self, text: Optional[str]) -> Optional[dict]:
        """
        Return the best matching command dict for *text*, or ``None``.

        Matching uses substring containment: the longest keyword that
        appears in *text* wins, so more-specific phrases take priority
        over shorter ones.

        Parameters
        ----------
        text:
            Normalised (lower-case, punctuation-stripped) user input.

        Returns
        -------
        dict or None
            Structured command dict with ``type``, ``actions``, ``game``,
            ``scene``, ``raw``, and ``source`` keys; or ``None`` if no
            keyword matched.
        """
        if not text or not self._commands:
            return None

        best_command: Optional[dict] = None
        best_length = 0

        for cmd_name, cmd_def in self._commands.items():
            if cmd_name.startswith("_"):
                # Skip metadata/comment keys
                continue
            for keyword in cmd_def.get("keywords", []):
                kw = keyword.lower()
                if kw in text and len(kw) > best_length:
                    best_length = len(kw)
                    best_command = {
                        "name": cmd_name,
                        "type": cmd_def.get("intent", ""),
                        "actions": list(cmd_def.get("actions", [])),
                        "game": cmd_def.get("game", ""),
                        "scene": cmd_def.get("scene", ""),
                        "raw": text,
                        "source": "registry",
                    }

        if best_command:
            logger.debug(
                "Registry matched command '%s' for input: '%s'.",
                best_command["name"],
                text,
            )
        return best_command

    def list_commands(self) -> list[str]:
        """Return the names of all registered (non-metadata) commands."""
        return [k for k in self._commands if not k.startswith("_")]

    def get_command(self, name: str) -> Optional[dict]:
        """Return the raw definition dict for *name*, or ``None``."""
        return self._commands.get(name)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load the registry from the JSON file, ignoring errors gracefully."""
        if not os.path.isfile(self._path):
            logger.debug(
                "Command registry file not found at '%s'; using empty registry.",
                self._path,
            )
            self._commands = {}
            return

        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                self._commands = json.load(fh)
            logger.info(
                "Loaded %d command(s) from registry '%s'.",
                len(self.list_commands()),
                self._path,
            )
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(
                "Failed to load command registry from '%s': %s", self._path, exc
            )
            self._commands = {}
