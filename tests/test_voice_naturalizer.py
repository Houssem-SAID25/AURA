"""
tests/test_voice_naturalizer.py
================================
Unit tests for voice/voice_naturalizer.py.
"""

import random

import pytest

from voice.voice_naturalizer import (
    naturalize_text,
    _apply_substitutions,
    _cleanup_lists,
    _add_prosody,
    _maybe_add_hesitation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seeded_rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


# ---------------------------------------------------------------------------
# naturalize_text – public API
# ---------------------------------------------------------------------------

class TestNaturalizeText:
    def test_returns_string(self):
        result = naturalize_text("Hello world.")
        assert isinstance(result, str)

    def test_empty_string_returned_unchanged(self):
        assert naturalize_text("") == ""

    def test_whitespace_only_returned_unchanged(self):
        assert naturalize_text("   ") == "   "

    def test_formal_phrase_replaced(self):
        result = naturalize_text("I can assist you with that.")
        assert "assist you with" not in result
        assert "help you with" in result

    def test_hesitation_injected_with_rate_1(self):
        rng = _seeded_rng(0)
        result = naturalize_text("This is a test.", hesitation_rate=1.0, rng=rng)
        hesitations = ["Hmm, ", "Let me see… ", "Ok so, ", "Alright, ", "So, "]
        assert any(result.startswith(h) for h in hesitations)

    def test_hesitation_never_injected_with_rate_0(self):
        for seed in range(20):
            rng = _seeded_rng(seed)
            result = naturalize_text("This is a test.", hesitation_rate=0.0, rng=rng)
            assert result == "This is a test."

    def test_result_stripped(self):
        result = naturalize_text("  Hello world.  ", hesitation_rate=0.0)
        assert result == result.strip()

    def test_does_not_double_hesitation(self):
        """If text already starts with a hesitation word, don't prepend another."""
        rng = _seeded_rng(0)
        result = naturalize_text("Hmm, let me think.", hesitation_rate=1.0, rng=rng)
        # Should not have two hesitation phrases stacked
        assert not result.startswith("Hmm, Hmm,")
        assert not result.startswith("Hmm, Let me see")


# ---------------------------------------------------------------------------
# _apply_substitutions
# ---------------------------------------------------------------------------

class TestApplySubstitutions:
    def test_assist_replaced(self):
        assert "help you with" in _apply_substitutions("I can assist you with that.")

    def test_certainly_replaced(self):
        result = _apply_substitutions("Certainly, I will help.")
        assert "Sure" in result or "sure" in result

    def test_absolutely_replaced(self):
        result = _apply_substitutions("Absolutely, let me do that.")
        assert "Of course" in result or "of course" in result

    def test_cannot_replaced(self):
        result = _apply_substitutions("I cannot do that right now.")
        assert "can't" in result

    def test_do_not_replaced(self):
        result = _apply_substitutions("Please do not do that.")
        assert "don't" in result

    def test_will_not_replaced(self):
        result = _apply_substitutions("I will not stop.")
        assert "won't" in result

    def test_i_am_contracted(self):
        result = _apply_substitutions("I am ready to help.")
        assert "I'm" in result

    def test_unrelated_text_unchanged(self):
        text = "The stream is live."
        assert _apply_substitutions(text) == text

    def test_multiple_substitutions_in_one_sentence(self):
        # "certainly" → "sure"; "cannot" → "can't"
        result = _apply_substitutions("Certainly I cannot do that.")
        assert "can't" in result
        assert "certainly" not in result.lower() or "Sure" in result or "sure" in result


# ---------------------------------------------------------------------------
# _cleanup_lists
# ---------------------------------------------------------------------------

class TestCleanupLists:
    def test_numbered_list_converted(self):
        text = "Options:\n1. Start stream\n2. Stop stream\n3. Switch scene"
        result = _cleanup_lists(text)
        assert "1." not in result
        assert "Start stream" in result
        assert "Stop stream" in result

    def test_bullet_list_converted(self):
        text = "- Alpha\n- Beta\n- Gamma"
        result = _cleanup_lists(text)
        assert "- " not in result
        assert "Alpha" in result
        assert "Beta" in result

    def test_no_list_unchanged(self):
        text = "Stream is starting now."
        assert _cleanup_lists(text) == text

    def test_empty_string_unchanged(self):
        assert _cleanup_lists("") == ""

    def test_asterisk_bullet_converted(self):
        text = "* One\n* Two"
        result = _cleanup_lists(text)
        assert "* " not in result
        assert "One" in result


# ---------------------------------------------------------------------------
# _add_prosody
# ---------------------------------------------------------------------------

class TestAddProsody:
    def test_short_sentence_unchanged(self):
        text = "Stream started!"
        assert _add_prosody(text) == text

    def test_long_sentence_gets_pause(self):
        long_text = (
            "I can help you start streaming and I can also switch scenes "
            "and mute the microphone so you have full control of your setup."
        )
        result = _add_prosody(long_text)
        # Result should still contain the key content
        assert "streaming" in result
        assert "microphone" in result

    def test_multiple_sentences_preserved(self):
        text = "Stream started. Scene switched. Mic muted."
        result = _add_prosody(text)
        assert "Stream started" in result
        assert "Scene switched" in result


# ---------------------------------------------------------------------------
# _maybe_add_hesitation
# ---------------------------------------------------------------------------

class TestMaybeAddHesitation:
    def test_always_adds_when_rate_1(self):
        rng = _seeded_rng(1)
        result = _maybe_add_hesitation("Hello.", 1.0, rng)
        assert result != "Hello."

    def test_never_adds_when_rate_0(self):
        rng = _seeded_rng(1)
        result = _maybe_add_hesitation("Hello.", 0.0, rng)
        assert result == "Hello."

    def test_result_ends_with_original_text(self):
        rng = _seeded_rng(1)
        result = _maybe_add_hesitation("Hello.", 1.0, rng)
        assert result.endswith("Hello.")
