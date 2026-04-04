"""
core/command_parser.py
======================
NLP-based command classifier.

Instead of rigid if/else matching, the parser uses fuzzy string matching
(via `rapidfuzz`) against a flexible set of intent patterns.  Each intent
maps to a canonical command type that `ActionHandler` knows how to execute.

Supported commands
------------------
- ``start_stream``     – "start stream", "go live", "begin streaming", …
- ``stop_stream``      – "stop stream", "end stream", "stop streaming", …
- ``switch_scene``     – "switch scene", "change scene to …", …
- ``launch_game``      – "launch …", "open …", "play …", "I'm going to stream …"
- ``launch_obs``       – "launch obs", "open obs", "start obs"
- ``open_twitch``      – "open twitch", "go to twitch"
- ``trending_games``   – "trending games", "what's popular", …
- ``suggest_game``     – "suggest a game", "what should I play", …
- ``help``             – "help", "what can you do", …
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Intent definitions
# ---------------------------------------------------------------------------
# Each entry: (intent_name, list_of_example_phrases)
# The parser fuzzy-matches user input against ALL example phrases and picks
# the highest-scoring intent above the threshold.

INTENTS: list[tuple[str, list[str]]] = [
    (
        "start_stream",
        [
            "start stream",
            "start streaming",
            "go live",
            "begin stream",
            "begin streaming",
            "start broadcast",
            "go on air",
        ],
    ),
    (
        "stop_stream",
        [
            "stop stream",
            "stop streaming",
            "end stream",
            "end streaming",
            "stop broadcast",
            "go offline",
            "stop live",
        ],
    ),
    (
        "switch_scene",
        [
            "switch scene",
            "change scene",
            "switch to scene",
            "change to scene",
            "select scene",
        ],
    ),
    (
        "launch_obs",
        [
            "launch obs studio",
            "open obs studio",
            "start obs studio",
            "launch obs",
            "open obs",
            "start obs",
            "run obs",
        ],
    ),
    (
        "open_twitch",
        [
            "open twitch",
            "go to twitch",
            "open twitch channel",
            "navigate to twitch",
        ],
    ),
    (
        "launch_game",
        [
            "launch game",
            "open game",
            "play game",
            "start game",
            "run game",
            "i'm going to stream",
            "i am going to stream",
            "let's play",
            "lets play",
        ],
    ),
    (
        "trending_games",
        [
            "trending games",
            "what is trending",
            "what's trending",
            "popular games",
            "top games",
            "most watched games",
            "what games are popular",
        ],
    ),
    (
        "suggest_game",
        [
            "suggest a game",
            "recommend a game",
            "what should i play",
            "which game should i stream",
            "game suggestion",
        ],
    ),
    (
        "help",
        [
            "help",
            "what can you do",
            "list commands",
            "show commands",
            "available commands",
        ],
    ),
]

# Minimum fuzzy-match score (0–100) required to accept an intent.
MATCH_THRESHOLD = 60


class CommandParser:
    """
    Classifies a transcribed voice command into a structured intent dict.

    Returns ``None`` when no intent scores above ``MATCH_THRESHOLD``.
    """

    def __init__(self, config: dict) -> None:  # noqa: ARG002
        self._intents = INTENTS
        self._threshold = MATCH_THRESHOLD
        logger.info("CommandParser initialised with %d intents.", len(self._intents))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, text: str) -> Optional[dict]:
        """
        Parse *text* into a command dict.

        Returns a dict with at least a ``"type"`` key on success, or
        ``None`` when the input does not match any known intent.
        """
        if not text:
            return None

        normalised = self._normalise(text)
        best_intent, best_score = self._match_intent(normalised)

        logger.debug(
            "Best intent: '%s' (score=%d) for input: '%s'",
            best_intent,
            best_score,
            normalised,
        )

        if best_intent is None or best_score < self._threshold:
            return None

        # Disambiguate: if the top match is launch_obs but "obs" is not
        # present in the text, it is more likely a launch_game command.
        if best_intent == "launch_obs" and "obs" not in text:
            best_intent = "launch_game"

        return self._build_command(best_intent, normalised)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise(text: str) -> str:
        """Lower-case and strip punctuation."""
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", "", text)
        return text

    def _match_intent(self, text: str) -> tuple[Optional[str], int]:
        """
        Return the best-matching intent name and its fuzzy score.

        Uses token_set_ratio so that word order doesn't matter as much.
        Falls back gracefully if `rapidfuzz` is not installed.
        """
        try:
            from rapidfuzz import fuzz  # noqa: PLC0415
        except ImportError:
            logger.warning("rapidfuzz not installed; using simple substring matching.")
            return self._substring_match(text)

        best_intent: Optional[str] = None
        best_score = 0

        for intent_name, examples in self._intents:
            for example in examples:
                score = fuzz.token_set_ratio(text, example)
                if score > best_score:
                    best_score = score
                    best_intent = intent_name

        return best_intent, best_score

    def _substring_match(self, text: str) -> tuple[Optional[str], int]:
        """Simple substring fallback when rapidfuzz is unavailable."""
        for intent_name, examples in self._intents:
            for example in examples:
                if example in text or text in example:
                    return intent_name, 100
        return None, 0

    def _build_command(self, intent: str, text: str) -> dict:
        """Build a structured command dict from the matched intent and raw text."""
        command: dict = {"type": intent, "raw": text}

        if intent == "switch_scene":
            # Extract scene name: "switch scene to <name>"
            match = re.search(r"(?:to|scene)\s+(.+)$", text)
            command["scene"] = match.group(1).strip() if match else ""

        elif intent == "launch_game":
            # Extract game name from patterns like "launch <game>" / "play <game>" /
            # "i'm going to stream <game>"
            patterns = [
                r"(?:launch|open|play|start|run)\s+(.+)$",
                r"(?:i(?:m|'m| am) going to stream)\s+(.+)$",
                r"(?:let(?:s|'s) play)\s+(.+)$",
            ]
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    command["game"] = match.group(1).strip()
                    break
            else:
                command["game"] = ""

        return command
