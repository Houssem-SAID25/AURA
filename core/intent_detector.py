"""
core/intent_detector.py
=======================
Lightweight intent detection for AURA voice commands.

Extracts the user's *intent* (what they want to do) from a normalised
text string using fuzzy matching (``rapidfuzz``).  Intent recognition
is intentionally decoupled from entity extraction and action resolution
so each concern can evolve independently.

Supported intents
-----------------
- ``start_stream``   – user wants to start streaming
- ``stop_stream``    – user wants to stop streaming
- ``switch_scene``   – user wants to change the active OBS scene
- ``launch_obs``     – user wants to open OBS Studio
- ``open_twitch``    – user wants to navigate to Twitch
- ``launch_game``    – user wants to launch a game
- ``trending_games`` – user wants to know what games are trending
- ``suggest_game``   – user wants a game recommendation
- ``help``           – user wants to list available commands
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Intent definitions
# ---------------------------------------------------------------------------
# Each tuple: (intent_name, list_of_example_phrases).
# The detector fuzzy-matches input against ALL phrases and picks the
# highest-scoring intent above the threshold.

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
DEFAULT_THRESHOLD = 60


class IntentDetector:
    """
    Detects user intent from normalised voice-command text.

    Uses ``rapidfuzz`` for fuzzy string matching with a simple substring
    fallback for environments where the library is unavailable.

    Parameters
    ----------
    threshold:
        Minimum match score (0–100) to accept a detected intent.
        Defaults to :data:`DEFAULT_THRESHOLD`.
    """

    def __init__(self, threshold: int = DEFAULT_THRESHOLD) -> None:
        self._intents = INTENTS
        self._threshold = threshold
        logger.debug(
            "IntentDetector initialised with %d intents (threshold=%d).",
            len(self._intents),
            self._threshold,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, text: Optional[str]) -> tuple[Optional[str], int]:
        """
        Detect the best-matching intent for *text*.

        Parameters
        ----------
        text:
            Normalised (lower-case, punctuation-stripped) input string.

        Returns
        -------
        tuple[str | None, int]
            ``(intent_name, score)`` where *score* is 0–100.
            Returns ``(None, 0)`` when no intent scores above the threshold.
        """
        if not text:
            return None, 0

        intent, score = self._match(text)
        if score < self._threshold:
            return None, score

        # Disambiguation: fuzzy matching sometimes maps "play <game>" to
        # "launch_obs" because of shared tokens.  Guard against that.
        if intent == "launch_obs" and "obs" not in text:
            intent = "launch_game"

        return intent, score

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _match(self, text: str) -> tuple[Optional[str], int]:
        """Return the best-matching intent and its fuzzy score."""
        try:
            from rapidfuzz import fuzz  # noqa: PLC0415

            best_intent: Optional[str] = None
            best_score = 0

            for intent_name, examples in self._intents:
                for example in examples:
                    score = fuzz.token_set_ratio(text, example)
                    if score > best_score:
                        best_score = score
                        best_intent = intent_name

            return best_intent, best_score

        except ImportError:
            logger.warning(
                "rapidfuzz not installed; falling back to substring matching."
            )
            return self._substring_match(text)

    def _substring_match(self, text: str) -> tuple[Optional[str], int]:
        """Simple substring fallback when ``rapidfuzz`` is unavailable."""
        for intent_name, examples in self._intents:
            for example in examples:
                if example in text or text in example:
                    return intent_name, 100
        return None, 0
