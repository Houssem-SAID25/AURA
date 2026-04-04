"""
core/intent_engine.py
=====================
Converts raw speech text into a structured intent JSON dict.

This is an enriched NLP layer that sits above the existing
:class:`~core.command_parser.CommandParser`.  It adds:

* Language-aware matching (fr/en)
* Game name extraction via a configurable game list
* Stream flag detection
* Confidence scoring

The engine is intentionally self-contained — it does not call
``CommandParser`` internally; it is called *before* the parser by
:class:`~core.decision_engine.DecisionEngine` when ``voice.ai_reasoning``
is enabled in ``config.json``.

Example output
--------------
Input : "AURA je vais tryhard Valorant et lancer un stream"

Output::

    {
        "intent": "gaming_stream_session",
        "game": "valorant",
        "stream": True,
        "confidence": 0.95,
        "raw": "aura je vais tryhard valorant et lancer un stream",
        "language": "fr",
    }
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Intent phrase banks  (en + fr)
# ---------------------------------------------------------------------------
# Each entry: (intent_name, language, list_of_trigger_phrases)
# Phrases are matched case-insensitively using token_set_ratio (rapidfuzz).

_INTENT_PHRASES: list[tuple[str, str, list[str]]] = [
    # ── gaming_stream_session ─────────────────────────────────────────────
    # Combined "play a game AND stream" intent
    (
        "gaming_stream_session",
        "en",
        [
            "i'm going to stream",
            "i am going to stream",
            "let me stream",
            "going to play and stream",
            "stream the game",
            "stream and play",
            "tryhard and stream",
            "play while streaming",
            "launch a game and stream",
        ],
    ),
    (
        "gaming_stream_session",
        "fr",
        [
            "je vais streamer",
            "je vais jouer et streamer",
            "je vais tryhard",
            "lancer un stream",
            "lancer le stream",
            "je veux streamer",
            "jouer en direct",
            "on va streamer",
            "aller en live",
        ],
    ),
    # ── start_stream ─────────────────────────────────────────────────────
    (
        "start_stream",
        "en",
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
        "start_stream",
        "fr",
        [
            "commencer le stream",
            "démarrer le stream",
            "partir en live",
            "aller en live",
            "lancer le stream",
            "commencer le direct",
        ],
    ),
    # ── stop_stream ──────────────────────────────────────────────────────
    (
        "stop_stream",
        "en",
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
        "stop_stream",
        "fr",
        [
            "arrêter le stream",
            "stopper le stream",
            "finir le stream",
            "fin du stream",
            "couper le stream",
            "passer offline",
        ],
    ),
    # ── switch_scene ─────────────────────────────────────────────────────
    (
        "switch_scene",
        "en",
        [
            "switch scene",
            "change scene",
            "switch to scene",
            "change to scene",
            "select scene",
        ],
    ),
    (
        "switch_scene",
        "fr",
        [
            "changer de scène",
            "changer la scène",
            "passer à la scène",
            "changer scène",
        ],
    ),
    # ── launch_obs ───────────────────────────────────────────────────────
    (
        "launch_obs",
        "en",
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
        "launch_obs",
        "fr",
        [
            "lancer obs",
            "ouvrir obs",
            "démarrer obs",
            "lancer obs studio",
        ],
    ),
    # ── open_twitch ──────────────────────────────────────────────────────
    (
        "open_twitch",
        "en",
        [
            "open twitch",
            "go to twitch",
            "open twitch channel",
            "navigate to twitch",
        ],
    ),
    (
        "open_twitch",
        "fr",
        [
            "ouvrir twitch",
            "aller sur twitch",
            "ouvrir la chaîne twitch",
        ],
    ),
    # ── launch_game ──────────────────────────────────────────────────────
    (
        "launch_game",
        "en",
        [
            "launch game",
            "open game",
            "play game",
            "start game",
            "run game",
            "let's play",
            "lets play",
        ],
    ),
    (
        "launch_game",
        "fr",
        [
            "lancer le jeu",
            "ouvrir le jeu",
            "jouer à",
            "démarrer le jeu",
        ],
    ),
    # ── trending_games ───────────────────────────────────────────────────
    (
        "trending_games",
        "en",
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
        "trending_games",
        "fr",
        [
            "jeux tendance",
            "jeux populaires",
            "jeux les plus regardés",
            "quels jeux sont populaires",
            "les meilleurs jeux",
        ],
    ),
    # ── suggest_game ─────────────────────────────────────────────────────
    (
        "suggest_game",
        "en",
        [
            "suggest a game",
            "recommend a game",
            "what should i play",
            "which game should i stream",
            "game suggestion",
        ],
    ),
    (
        "suggest_game",
        "fr",
        [
            "suggère un jeu",
            "recommande un jeu",
            "quel jeu jouer",
            "propose un jeu",
            "donne moi une idée de jeu",
        ],
    ),
    # ── mute_mic ─────────────────────────────────────────────────────────
    (
        "mute_mic",
        "en",
        ["mute mic", "mute microphone", "mute audio"],
    ),
    (
        "mute_mic",
        "fr",
        ["couper le micro", "couper micro", "désactiver le micro"],
    ),
    # ── unmute_mic ───────────────────────────────────────────────────────
    (
        "unmute_mic",
        "en",
        ["unmute mic", "unmute microphone", "unmute audio"],
    ),
    (
        "unmute_mic",
        "fr",
        ["activer le micro", "réactiver le micro", "unmute micro"],
    ),
    # ── help ─────────────────────────────────────────────────────────────
    (
        "help",
        "en",
        ["help", "what can you do", "list commands", "show commands", "available commands"],
    ),
    (
        "help",
        "fr",
        ["aide", "qu'est-ce que tu peux faire", "liste des commandes", "commandes disponibles"],
    ),
]

# Minimum rapidfuzz score (0–100) to accept an intent match.
_DEFAULT_THRESHOLD = 60

# Score (0–100) at which confidence reaches 1.0
_PERFECT_SCORE = 100

# ---------------------------------------------------------------------------
# Stream-flag keywords (checking if user wants to stream)
# ---------------------------------------------------------------------------
_STREAM_KEYWORDS_EN = frozenset([
    "stream", "streaming", "live", "broadcast", "twitch", "go live",
])
_STREAM_KEYWORDS_FR = frozenset([
    "stream", "streamer", "direct", "live", "en direct", "twitch",
])

# ---------------------------------------------------------------------------
# Known games (lowercase, used for entity extraction)
# ---------------------------------------------------------------------------
_DEFAULT_GAMES: list[str] = [
    "counter-strike 2", "cs2", "cs 2",
    "valorant",
    "minecraft",
    "fortnite",
    "league of legends", "lol",
    "apex legends", "apex",
    "overwatch 2", "overwatch",
    "call of duty", "warzone",
    "gta 5", "gta v", "grand theft auto",
    "rocket league",
    "among us",
    "fall guys",
    "hades",
    "cyberpunk 2077",
    "elden ring",
    "dota 2",
    "pubg",
    "terraria",
    "stardew valley",
]


class IntentEngine:
    """
    Converts raw speech text into a structured intent JSON dict.

    Parameters
    ----------
    config:
        Validated application config dict.  The ``games`` section is used
        to extend the built-in game name list.
    threshold:
        Minimum fuzzy-match score (0–100) to accept an intent.
    """

    def __init__(
        self,
        config: Optional[dict] = None,
        threshold: int = _DEFAULT_THRESHOLD,
    ) -> None:
        self._threshold = threshold
        self._config = config or {}

        # Build game list from config + defaults
        config_games = list(self._config.get("games", {}).keys())
        self._games: list[str] = sorted(
            set(_DEFAULT_GAMES + [g.lower() for g in config_games]),
            key=len,
            reverse=True,  # longest first so "counter-strike 2" beats "cs2"
        )

        logger.debug(
            "IntentEngine initialised (%d intents, %d games, threshold=%d).",
            len({t[0] for t in _INTENT_PHRASES}),
            len(self._games),
            threshold,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, text: str) -> Optional[dict]:
        """
        Analyze *text* and return a structured intent dict, or ``None``.

        Parameters
        ----------
        text:
            Raw transcribed speech (may contain wake word "AURA").

        Returns
        -------
        dict or None
            Keys:
            - ``intent``     – detected intent name (str)
            - ``game``       – extracted game name, or ``""``
            - ``scene``      – extracted scene name, or ``""``
            - ``stream``     – True if user wants to stream (bool)
            - ``confidence`` – 0.0 – 1.0 float
            - ``raw``        – normalised input text
            - ``language``   – detected language (``"fr"`` or ``"en"``)
        """
        if not text or not text.strip():
            return None

        normalised = self._normalise(text)
        lang = self._detect_language(normalised)

        intent_name, score = self._match_intent(normalised, lang)
        if intent_name is None or score < self._threshold:
            return None

        confidence = round(min(1.0, score / _PERFECT_SCORE), 3)
        game = self._extract_game(normalised)
        scene = self._extract_scene(normalised)
        stream_flag = self._has_stream_flag(normalised, lang)

        result = {
            "intent": intent_name,
            "game": game,
            "scene": scene,
            "stream": stream_flag,
            "confidence": confidence,
            "raw": normalised,
            "language": lang,
        }

        logger.debug(
            "IntentEngine: intent=%s game=%r stream=%s confidence=%.2f lang=%s",
            intent_name,
            game,
            stream_flag,
            confidence,
            lang,
        )
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise(text: str) -> str:
        """Lower-case, strip wake word prefix and extra punctuation."""
        text = text.lower().strip()
        # Remove leading "aura" wake word if present
        text = re.sub(r"^aura[,\s]+", "", text)
        text = re.sub(r"[^\w\s\-']", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _detect_language(text: str) -> str:
        """Heuristically detect whether text is French or English.

        Requires at least 2 French marker words (or 1 unambiguous marker) to
        avoid false-positives from French loanwords in English text.
        """
        fr_markers = {"je", "vais", "veux", "jouer", "lancer", "streamer",
                      "jeu", "jeux", "arrêter", "ouvrir", "aide", "bonjour",
                      "salut", "aller", "direct"}
        # Strong single-word indicators (unambiguous French)
        fr_strong = {"arrêter", "jouer", "lancer", "streamer", "veux", "bonjour",
                     "salut", "jeux", "ouvrir"}
        words = set(text.split())
        common = words & fr_markers
        strong = words & fr_strong
        # Require ≥2 French markers OR ≥1 unambiguous/strong marker
        return "fr" if len(common) >= 2 or bool(strong) else "en"

    def _match_intent(self, text: str, lang: str) -> tuple[Optional[str], int]:
        """Return (best_intent, score) for *text*."""
        try:
            from rapidfuzz import fuzz  # noqa: PLC0415

            best_intent: Optional[str] = None
            best_score = 0

            for intent_name, phrase_lang, phrases in _INTENT_PHRASES:
                # Include both language-specific and "any" phrases
                if phrase_lang not in (lang, "any"):
                    continue
                for phrase in phrases:
                    score = fuzz.token_set_ratio(text, phrase)
                    if score > best_score:
                        best_score = score
                        best_intent = intent_name

            return best_intent, best_score

        except ImportError:
            logger.warning("rapidfuzz not installed; using substring fallback.")
            return self._substring_match(text, lang)

    def _substring_match(self, text: str, lang: str) -> tuple[Optional[str], int]:
        """Substring fallback when rapidfuzz is unavailable."""
        for intent_name, phrase_lang, phrases in _INTENT_PHRASES:
            if phrase_lang not in (lang, "any"):
                continue
            for phrase in phrases:
                if phrase in text or text in phrase:
                    return intent_name, 100
        return None, 0

    def _extract_game(self, text: str) -> str:
        """
        Extract a game name from *text*.

        Checks known game names (longest first to prefer full names).
        """
        for game in self._games:
            if game in text:
                return game
        return ""

    @staticmethod
    def _extract_scene(text: str) -> str:
        """Extract a scene name from *text* (for switch_scene intents)."""
        # "switch/change/passer/changer (to/à/de) <scene>"
        match = re.search(
            r"(?:to|à|de|la scène|scene)\s+([a-zA-Z0-9_\- ]+)$",
            text,
            re.IGNORECASE,
        )
        return match.group(1).strip() if match else ""

    def _has_stream_flag(self, text: str, lang: str) -> bool:
        """Return True if the text indicates the user wants to stream."""
        words = set(text.split())
        if lang == "fr":
            return bool(words & _STREAM_KEYWORDS_FR)
        return bool(words & _STREAM_KEYWORDS_EN)
