"""
core/task_planner.py
====================
Converts a structured intent dict into an ordered list of action names
that :class:`~core.action_handler.ActionHandler` can execute.

The planner consults two data sources in order:

1. **Built-in intent map** – default mappings from intent name to action
   sequence, covering all intents recognised by
   :class:`~core.intent_engine.IntentEngine`.
2. **Command registry** (``config/commands.json``) – overrides and extends
   the built-in map with user-defined compound commands.

Context-aware planning
----------------------
When a :class:`~core.context_engine.ContextEngine` state dict is passed the
planner skips redundant actions:

* If OBS is already running, ``launch_obs`` is removed from the plan.

Usage::

    planner = TaskPlanner(config)
    actions = planner.plan(intent_data, context_state)
    # actions = ["launch_obs", "launch_game", "open_twitch", "start_stream"]
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in intent → action mappings
# ---------------------------------------------------------------------------
# Order matters: actions execute left-to-right.

_INTENT_TO_ACTIONS: dict[str, list[str]] = {
    # Combined gaming + stream session
    "gaming_stream_session": ["launch_obs", "launch_game", "open_twitch", "start_stream"],
    # Streaming control
    "start_stream":   ["start_stream"],
    "stop_stream":    ["stop_stream"],
    # OBS
    "switch_scene":   ["switch_scene"],
    "launch_obs":     ["launch_obs"],
    "trigger_overlay": ["trigger_overlay"],
    # Platforms
    "open_twitch":    ["open_twitch"],
    # Game
    "launch_game":    ["launch_game"],
    # Discovery
    "trending_games": ["trending_games"],
    "suggest_game":   ["suggest_game"],
    # Audio
    "mute_mic":       ["mute_mic"],
    "unmute_mic":     ["unmute_mic"],
    # Meta
    "help":           ["help"],
    # Legacy registry intent names (pass-through)
    "stream":         ["launch_obs", "launch_game", "open_twitch", "start_stream"],
    "mute_brb":       ["mute_mic", "switch_scene"],
}


class TaskPlanner:
    """
    Translates intent data into an executable action sequence.

    Parameters
    ----------
    config:
        Validated application config dict.  The ``games`` key is consulted
        to validate game names; the ``commands.json`` path is used to load
        the registry.
    """

    def __init__(self, config: Optional[dict] = None) -> None:
        self._config = config or {}
        self._registry_map = self._load_registry()
        logger.debug(
            "TaskPlanner initialised (%d built-in + %d registry intents).",
            len(_INTENT_TO_ACTIONS),
            len(self._registry_map),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def plan(
        self,
        intent_data: dict,
        context: Optional[dict] = None,
    ) -> list[str]:
        """
        Return an ordered list of action names for *intent_data*.

        Parameters
        ----------
        intent_data:
            Structured intent dict from
            :class:`~core.intent_engine.IntentEngine`.  Must have at least
            an ``"intent"`` key.
        context:
            Optional environment-state dict from
            :class:`~core.context_engine.ContextEngine`.  Used to remove
            actions that are unnecessary given the current state.

        Returns
        -------
        list[str]
            Ordered action names.  Returns ``["help"]`` as a safe fallback
            when nothing can be planned.
        """
        intent = intent_data.get("intent", "")
        game = intent_data.get("game", "")
        stream = intent_data.get("stream", False)
        context = context or {}

        # 1. Look up actions from registry (user-defined) then built-in
        actions = self._lookup(intent, game, stream)

        if not actions:
            logger.warning("TaskPlanner: no actions for intent '%s'.", intent)
            return ["help"]

        # 2. Context-aware pruning
        actions = self._prune(actions, context)

        logger.debug("TaskPlanner: intent=%s -> actions=%s", intent, actions)
        return actions

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _lookup(self, intent: str, game: str, stream: bool) -> list[str]:
        """
        Find the action list for *intent*, consulting registry first.

        **Stream-flag upgrade**: when the intent is ``"launch_game"`` and the
        stream flag is True (the user mentioned streaming), the plan is
        automatically upgraded to a full ``"gaming_stream_session"`` sequence
        (launch OBS, launch game, open Twitch, start stream).  This makes
        natural utterances like "let's play valorant on stream" produce the
        most useful multi-action response without requiring the intent engine
        to perfectly distinguish ``launch_game`` from ``gaming_stream_session``.
        """
        # Registry overrides built-ins
        if intent in self._registry_map:
            return list(self._registry_map[intent])

        # Built-in map
        if intent in _INTENT_TO_ACTIONS:
            base = list(_INTENT_TO_ACTIONS[intent])
            # If the intent is launch_game but stream flag is set, upgrade
            if intent == "launch_game" and stream:
                base = list(_INTENT_TO_ACTIONS["gaming_stream_session"])
            return base

        return []

    def _prune(self, actions: list[str], context: dict) -> list[str]:
        """
        Remove actions that are unnecessary given the current context.

        Currently prunes:
        - ``launch_obs`` when OBS is already running.
        """
        pruned = list(actions)

        if context.get("obs_running") and "launch_obs" in pruned:
            pruned.remove("launch_obs")
            logger.debug("TaskPlanner: skipped launch_obs (OBS already running).")

        return pruned

    def _load_registry(self) -> dict[str, list[str]]:
        """
        Load intent → action mappings from ``config/commands.json``.

        Keys in the registry are the ``"intent"`` field of each command
        entry (e.g. ``"stream"``).  If two commands share the same intent
        the last one wins.

        Returns an empty dict on any error.
        """
        try:
            from core.command_registry import CommandRegistry  # noqa: PLC0415
            registry = CommandRegistry()
            result: dict[str, list[str]] = {}
            for name in registry.list_commands():
                cmd = registry.get_command(name)
                if cmd and cmd.get("intent") and cmd.get("actions"):
                    result[cmd["intent"]] = list(cmd["actions"])
            return result
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("TaskPlanner: could not load registry: %s", exc)
            return {}
