"""
tests/test_onboarding.py
========================
Unit tests for the onboarding sub-system:

- core.i18n  (translation helper)
- core.onboarding.onboarding_storage  (profile persistence & validation)
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

# ---------------------------------------------------------------------------
# i18n tests
# ---------------------------------------------------------------------------

class TestI18n(unittest.TestCase):

    def setUp(self):
        # Reset to English before each test
        from core.i18n import set_language
        set_language("en")

    def test_t_returns_string_for_valid_key(self):
        from core.i18n import t
        result = t("onboarding.welcome")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_t_returns_key_for_missing_key(self):
        from core.i18n import t
        result = t("onboarding.nonexistent_key_xyz")
        self.assertEqual(result, "onboarding.nonexistent_key_xyz")

    def test_t_formats_kwargs(self):
        from core.i18n import t
        result = t("onboarding.done_message", username="Houssem")
        self.assertIn("Houssem", result)

    def test_set_language_en(self):
        from core.i18n import set_language, get_language, t
        set_language("en")
        self.assertEqual(get_language(), "en")
        self.assertIn("Welcome", t("onboarding.welcome"))

    def test_set_language_fr(self):
        from core.i18n import set_language, get_language, t
        set_language("fr")
        self.assertEqual(get_language(), "fr")
        self.assertIn("Bienvenue", t("onboarding.welcome"))

    def test_unsupported_language_falls_back_to_en(self):
        from core.i18n import set_language, get_language
        set_language("de")
        self.assertEqual(get_language(), "en")

    def test_both_languages_have_same_keys(self):
        """Ensure EN and FR JSON files contain the same onboarding keys."""
        locale_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "core", "i18n",
        )
        with open(os.path.join(locale_dir, "en.json"), encoding="utf-8") as f:
            en = json.load(f)
        with open(os.path.join(locale_dir, "fr.json"), encoding="utf-8") as f:
            fr = json.load(f)

        en_keys = set(en.get("onboarding", {}).keys())
        fr_keys = set(fr.get("onboarding", {}).keys())
        self.assertEqual(en_keys, fr_keys, "EN and FR translation files have different keys")


# ---------------------------------------------------------------------------
# Onboarding storage tests
# ---------------------------------------------------------------------------

class TestOnboardingStorage(unittest.TestCase):

    def _storage_with_tmpdir(self, tmp_dir: str):
        """Patch _PROFILE_PATH to point to a temp directory."""
        profile_path = os.path.join(tmp_dir, "user_profile.json")
        return patch(
            "core.onboarding.onboarding_storage._PROFILE_PATH",
            profile_path,
        )

    # profile_exists ─────────────────────────────────────────────────────────

    def test_profile_exists_false_when_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self._storage_with_tmpdir(tmp):
                from core.onboarding.onboarding_storage import profile_exists
                self.assertFalse(profile_exists())

    def test_profile_exists_true_after_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self._storage_with_tmpdir(tmp):
                from core.onboarding.onboarding_storage import (
                    profile_exists, save_profile, build_profile,
                )
                profile = build_profile(language="en", username="Tester")
                save_profile(profile)
                self.assertTrue(profile_exists())

    # save_profile / load_profile ────────────────────────────────────────────

    def test_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self._storage_with_tmpdir(tmp):
                from core.onboarding.onboarding_storage import (
                    save_profile, load_profile, build_profile,
                )
                profile = build_profile(
                    language="fr",
                    username="Houssem",
                    twitch="https://twitch.tv/houssem",
                    other_links="https://youtube.com/@houssem",
                )
                result = save_profile(profile)
                self.assertTrue(result)
                loaded = load_profile()
                self.assertEqual(loaded["username"], "Houssem")
                self.assertEqual(loaded["language"], "fr")
                self.assertEqual(loaded["twitch"], "https://twitch.tv/houssem")

    def test_load_profile_returns_empty_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self._storage_with_tmpdir(tmp):
                from core.onboarding.onboarding_storage import load_profile
                self.assertEqual(load_profile(), {})

    def test_save_creates_config_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            nested = os.path.join(tmp, "subdir")
            profile_path = os.path.join(nested, "user_profile.json")
            with patch("core.onboarding.onboarding_storage._PROFILE_PATH", profile_path):
                from core.onboarding.onboarding_storage import save_profile, build_profile
                profile = build_profile(language="en", username="Test")
                ok = save_profile(profile)
                self.assertTrue(ok)
                self.assertTrue(os.path.isfile(profile_path))

    # build_profile ──────────────────────────────────────────────────────────

    def test_build_profile_structure(self):
        from core.onboarding.onboarding_storage import build_profile
        p = build_profile(language="en", username="Alice", twitch="alice")
        self.assertEqual(p["language"], "en")
        self.assertEqual(p["username"], "Alice")
        self.assertIn("twitch.tv/alice", p["twitch"])
        self.assertIn("created_at", p)
        self.assertIn("settings", p)
        self.assertEqual(p["settings"]["assistant_name"], "AURA")

    def test_build_profile_strips_whitespace(self):
        from core.onboarding.onboarding_storage import build_profile
        p = build_profile(language="en", username="  Bob  ")
        self.assertEqual(p["username"], "Bob")

    def test_build_profile_empty_twitch(self):
        from core.onboarding.onboarding_storage import build_profile
        p = build_profile(language="en", username="Alice", twitch="")
        self.assertEqual(p["twitch"], "")

    # validate_twitch ────────────────────────────────────────────────────────

    def test_validate_twitch_empty_is_valid(self):
        from core.onboarding.onboarding_storage import validate_twitch
        self.assertTrue(validate_twitch(""))
        self.assertTrue(validate_twitch("   "))

    def test_validate_twitch_plain_username(self):
        from core.onboarding.onboarding_storage import validate_twitch
        self.assertTrue(validate_twitch("houssem"))
        self.assertTrue(validate_twitch("user_123"))

    def test_validate_twitch_full_url(self):
        from core.onboarding.onboarding_storage import validate_twitch
        self.assertTrue(validate_twitch("https://twitch.tv/houssem"))
        self.assertTrue(validate_twitch("https://www.twitch.tv/houssem"))
        self.assertTrue(validate_twitch("http://twitch.tv/houssem"))

    def test_validate_twitch_invalid_url(self):
        from core.onboarding.onboarding_storage import validate_twitch
        self.assertFalse(validate_twitch("https://youtube.com/houssem"))
        self.assertFalse(validate_twitch("not a url!!!"))
        self.assertFalse(validate_twitch("https://twitch.tv/"))   # no username

    def test_validate_twitch_normalisation(self):
        from core.onboarding.onboarding_storage import build_profile
        p = build_profile(language="en", username="x", twitch="myuser")
        self.assertEqual(p["twitch"], "https://twitch.tv/myuser")
