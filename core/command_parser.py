"""
core/command_parser.py
======================
NLP-based command classifier.

Parsing happens in two stages:

1. **Registry lookup** — the :class:`CommandRegistry` checks whether the
   input matches a compound command defined in ``config/commands.json``
   (e.g. "stream CS2" → launch OBS + launch game + open Twitch).
2. **Intent detection** — if no registry command matches, the
   :class:`IntentDetector` fuzzy-matches the input against a built-in
   set of intent phrases and returns the best single-action intent.

The parser always returns a structured dict (or ``None``) so that
:class:`~core.action_handler.ActionHandler` never has to parse raw text.

Returned dict keys
------------------
- ``type``    – intent name (e.g. ``"start_stream"``, ``"launch_game"``).
- ``actions`` – (registry commands only) ordered list of action names.
- ``game``    – game name extracted from the utterance, or ``""``.
- ``scene``   – scene name for ``switch_scene`` commands, or ``""``.
- ``raw``     – normalised input text.
- ``source``  – ``"registry"`` | ``"intent_detector"``.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from core.command_registry import CommandRegistry
from core.intent_detector import IntentDetector

logger = logging.getLogger(__name__)


class CommandParser:
    """
    Classifies a transcribed voice command into a structured command dict.

    Returns ``None`` when no registry command or intent can be matched.
    """

    def __init__(self, config: dict) -> None:  # noqa: ARG002
        self._registry = CommandRegistry()
        self._detector = IntentDetector()
        logger.info("CommandParser initialised (registry + intent detector).")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, text: str) -> Optional[dict]:
        """
        Parse *text* into a structured command dict.

        Registry commands (multi-action) are tried first; single-action
        intent detection is used as a fallback.

        Parameters
        ----------
        text:
            Raw transcribed voice input.

        Returns
        -------
        dict or None
            Structured command on success; ``None`` when nothing matches.
        """
        if not text:
            return None

        normalised = self._normalise(text)

        # --- Stage 1: registry lookup (compound / multi-action commands) ---
        registry_cmd = self._registry.match(normalised)
        if registry_cmd:
            logger.debug(
                "Registry match: '%s' for input: '%s'",
                registry_cmd.get("name"),
                normalised,
            )
            return registry_cmd

        # --- Stage 2: intent detection (single-action commands) ---
        intent, score = self._detector.detect(normalised)
        logger.debug(
            "Intent detection: '%s' (score=%d) for input: '%s'",
            intent,
            score,
            normalised,
        )

        if intent is None:
            return None

        return self._build_command(intent, normalised)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise(text: str) -> str:
        """Lower-case and strip punctuation."""
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", "", text)
        return text

    @staticmethod
    def _build_command(intent: str, text: str) -> dict:
        """Build a structured command dict for a single-action intent."""
        command: dict = {"type": intent, "raw": text, "source": "intent_detector"}

        if intent == "switch_scene":
            # Extract scene name after "to" or "scene": "switch scene to gameplay"
            match = re.search(r"(?:to|scene)\s+(.+)$", text)
            command["scene"] = match.group(1).strip() if match else ""

        elif intent == "launch_game":
            # Extract game name from: "launch <game>", "play <game>",
            # "i'm going to stream <game>", "let's play <game>"
            patterns = [
                r"(?:launch|open|play|start|run)\s+(.+)$",
                r"(?:im|i am) going to stream\s+(.+)$",
                r"lets play\s+(.+)$",
            ]
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    command["game"] = match.group(1).strip()
                    break
            else:
                command["game"] = ""

        return command
