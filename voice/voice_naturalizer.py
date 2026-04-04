"""
voice/voice_naturalizer.py
==========================
Transforms raw assistant text into natural, conversational speech before
it is handed to the TTS engine.

The pipeline applies four stages in order:

1. **Formal-to-casual substitutions** – replaces stiff phrases with friendlier
   equivalents (e.g. "I can assist you with" → "I can help you with").
2. **Prosody punctuation** – adds breathing pauses (commas, ellipses) to long
   sentences so the TTS engine produces more natural rhythm.
3. **Hesitation injection** – occasionally prepends a thinking sound ("hmm,"
   or "let me see…") to vary the rhythm and avoid a robotic feel.
4. **Bullet/list cleanup** – converts numbered/bulleted lists into flowing
   prose so they are read naturally aloud.

Configuration
-------------
All behaviour can be tuned or disabled via ``config.json``::

    "voice": {
        "naturalizer": {
            "enabled": true,
            "hesitation_rate": 0.15
        }
    }
"""

from __future__ import annotations

import random
import re
from typing import Optional

# ---------------------------------------------------------------------------
# Formal-to-casual phrase map
# ---------------------------------------------------------------------------
# Each entry is (old_pattern, replacement).  Patterns are plain strings;
# matching is case-insensitive and whole-word aware.
_SUBSTITUTIONS: list[tuple[str, str]] = [
    (r"\bI can assist you with\b", "I can help you with"),
    (r"\bI am able to\b", "I can"),
    (r"\bCertainly\b", "Sure"),
    (r"\bcertainly\b", "sure"),
    (r"\bAbsolutely\b", "Of course"),
    (r"\babsolutely\b", "of course"),
    (r"\bAffirmative\b", "Yes"),
    (r"\baffirmative\b", "yes"),
    (r"\bI would like to inform you\b", "Just so you know"),
    (r"\bPlease be advised\b", "Heads up"),
    (r"\bplease be advised\b", "heads up"),
    (r"\bAt this point in time\b", "Right now"),
    (r"\bat this point in time\b", "right now"),
    (r"\bIn order to\b", "To"),
    (r"\bin order to\b", "to"),
    (r"\bIs not available\b", "isn't available"),
    (r"\bis not available\b", "isn't available"),
    (r"\bDo not\b", "Don't"),
    (r"\bdo not\b", "don't"),
    (r"\bCannot\b", "Can't"),
    (r"\bcannot\b", "can't"),
    (r"\bWill not\b", "Won't"),
    (r"\bwill not\b", "won't"),
    (r"\bI am\b", "I'm"),
    (r"\bYou are\b", "You're"),
    (r"\byou are\b", "you're"),
    (r"\bIt is\b", "It's"),
    (r"\bit is\b", "it's"),
    (r"\bThere is\b", "There's"),
    (r"\bthere is\b", "there's"),
]

# Compiled once at import time for performance
_COMPILED_SUBSTITUTIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(pattern), replacement)
    for pattern, replacement in _SUBSTITUTIONS
]

# ---------------------------------------------------------------------------
# Hesitation phrases prepended at random
# ---------------------------------------------------------------------------
_HESITATIONS: list[str] = [
    "Hmm, ",
    "Let me see… ",
    "Ok so, ",
    "Alright, ",
    "So, ",
]

# Conjunctions after which we may insert a breathing pause
_SPLIT_CONJUNCTIONS = re.compile(
    r",?\s+(and|but|so|because|however|although|while|since|though)\s+",
    re.IGNORECASE,
)

# Match numbered / bulleted list items, e.g. "1. ", "- ", "• "
_LIST_ITEM = re.compile(r"^\s*(?:\d+[\.\)]\s+|[-•*]\s+)", re.MULTILINE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def naturalize_text(
    text: str,
    hesitation_rate: float = 0.15,
    *,
    rng: Optional[random.Random] = None,
) -> str:
    """Return a more natural, conversational version of *text*.

    Parameters
    ----------
    text:
        The raw assistant response to transform.
    hesitation_rate:
        Probability (0.0 – 1.0) of prepending a hesitation phrase.
        Defaults to 0.15 (15%).
    rng:
        Optional :class:`random.Random` instance for reproducible tests.
        Uses the global RNG by default.

    Returns
    -------
    str
        The transformed text.  Returns the original string unchanged if
        it is empty or only whitespace.
    """
    if not text or not text.strip():
        return text

    _rng = rng or random

    result = _apply_substitutions(text)
    result = _cleanup_lists(result)
    result = _add_prosody(result)
    result = _maybe_add_hesitation(result, hesitation_rate, _rng)

    return result.strip()


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------

def _apply_substitutions(text: str) -> str:
    """Replace formal phrases with casual equivalents."""
    for pattern, replacement in _COMPILED_SUBSTITUTIONS:
        text = pattern.sub(replacement, text)
    return text


def _cleanup_lists(text: str) -> str:
    """Convert simple bullet/numbered lists into flowing prose."""
    # Only act when we detect actual list items
    if not _LIST_ITEM.search(text):
        return text

    lines = text.splitlines()
    cleaned: list[str] = []
    list_items: list[str] = []

    for line in lines:
        m = _LIST_ITEM.match(line)
        if m:
            # Strip the bullet/number prefix
            item = line[m.end():].strip()
            if item:
                list_items.append(item)
        else:
            if list_items:
                cleaned.append(", ".join(list_items) + ".")
                list_items = []
            cleaned.append(line)

    if list_items:
        cleaned.append(", ".join(list_items) + ".")

    return " ".join(line for line in cleaned if line.strip())


def _add_prosody(text: str) -> str:
    """Insert breathing pauses around long conjunctions."""
    # Split very long sentences (>120 chars) at conjunctions
    sentences = re.split(r"(?<=[.!?])\s+", text)
    result: list[str] = []

    for sentence in sentences:
        if len(sentence) > 120:
            sentence = _SPLIT_CONJUNCTIONS.sub(
                lambda m: f", {m.group(1).lower()} ", sentence
            )
        result.append(sentence)

    return " ".join(result)


def _maybe_add_hesitation(
    text: str, rate: float, rng: random.Random
) -> str:
    """Prepend a hesitation phrase with probability *rate*."""
    if rate <= 0.0:
        return text
    if rng.random() < rate:
        hesitation = rng.choice(_HESITATIONS)
        # Don't double-up if the text already starts with a hesitation
        text_lower = text.lower()
        for h in _HESITATIONS:
            if text_lower.startswith(h.lower().strip(", .…")):
                return text
        text = hesitation + text
    return text
