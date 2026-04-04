"""
tests/test_onboarding_manager.py
==================================
Unit tests for the top-level onboarding package:
- OnboardingManager
- onboarding/steps/app_detection.py
- onboarding/steps/stream_config.py
- voice/voice_naturalizer.py  (new mode= parameter)
- core/onboarding/onboarding_storage.build_profile (new fields)
"""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_step_module(name: str, return_value: dict) -> types.ModuleType:
    """Create a fake step module whose run() returns *return_value*."""
    mod = types.ModuleType(name)
    mod.run = MagicMock(return_value=return_value)  # type: ignore[attr-defined]
    return mod


# ---------------------------------------------------------------------------
# OnboardingManager tests
# ---------------------------------------------------------------------------

class TestOnboardingManager(unittest.TestCase):

    def _patch_steps(self, confirm: bool = True, saved: bool = True):
        """Patch all 8 step modules with lightweight fakes."""
        step_mocks = {
            "onboarding.steps.language_selection": _make_step_module("language_selection", {"language": "en"}),
            "onboarding.steps.user_profile":        _make_step_module("user_profile",       {"username": "Tester", "streamer_name": "Tester"}),
            "onboarding.steps.app_detection":       _make_step_module("app_detection",      {"detected_apps": {"obs_installed": True, "games": []}}),
            "onboarding.steps.twitch_setup":        _make_step_module("twitch_setup",       {"twitch": "", "twitch_access_token": ""}),
            "onboarding.steps.discord_setup":       _make_step_module("discord_setup",      {"discord_bot_token": "", "discord_channel_id": ""}),
            "onboarding.steps.obs_setup":           _make_step_module("obs_setup",          {"obs_auto_detected_port": 4455}),
            "onboarding.steps.stream_config":       _make_step_module("stream_config",      {"stream_config": {"platform": "twitch", "resolution": "1080p", "default_scene": "Gaming"}}),
            "onboarding.steps.save_config":         _make_step_module("save_config",        {"saved": saved}),
        }
        return patch.dict(sys.modules, step_mocks)

    def test_run_completes_successfully(self):
        from onboarding.onboarding_manager import OnboardingManager
        with self._patch_steps(confirm=True, saved=True):
            with patch.object(OnboardingManager, "_confirm", return_value=True):
                manager = OnboardingManager()
                result = manager.run()
        self.assertTrue(result)

    def test_run_returns_false_on_cancel(self):
        from onboarding.onboarding_manager import OnboardingManager
        with self._patch_steps():
            with patch.object(OnboardingManager, "_confirm", return_value=False):
                manager = OnboardingManager()
                result = manager.run()
        self.assertFalse(result)

    def test_run_returns_false_on_save_failure(self):
        from onboarding.onboarding_manager import OnboardingManager
        with self._patch_steps(saved=False):
            with patch.object(OnboardingManager, "_confirm", return_value=True):
                manager = OnboardingManager()
                result = manager.run()
        self.assertFalse(result)

    def test_skip_app_detection_inserts_empty_dict(self):
        from onboarding.onboarding_manager import OnboardingManager
        captured = {}

        def fake_save_run(data):
            captured.update(data)
            return {"saved": True}

        step_mocks = {
            "onboarding.steps.language_selection": _make_step_module("language_selection", {"language": "en"}),
            "onboarding.steps.user_profile":        _make_step_module("user_profile",       {"username": "X", "streamer_name": "X"}),
            "onboarding.steps.app_detection":       _make_step_module("app_detection",      {}),  # should NOT be called
            "onboarding.steps.twitch_setup":        _make_step_module("twitch_setup",       {}),
            "onboarding.steps.discord_setup":       _make_step_module("discord_setup",      {}),
            "onboarding.steps.obs_setup":           _make_step_module("obs_setup",          {}),
            "onboarding.steps.stream_config":       _make_step_module("stream_config",      {}),
            "onboarding.steps.save_config":         _make_step_module("save_config",        {"saved": True}),
        }
        # Ensure save_config.run captures data
        step_mocks["onboarding.steps.save_config"].run = MagicMock(side_effect=fake_save_run)

        with patch.dict(sys.modules, step_mocks):
            with patch.object(OnboardingManager, "_confirm", return_value=True):
                manager = OnboardingManager(skip_app_detection=True)
                manager.run()

        # app_detection.run should NOT have been called
        step_mocks["onboarding.steps.app_detection"].run.assert_not_called()
        self.assertIn("detected_apps", captured)
        self.assertIsInstance(captured["detected_apps"], dict)


# ---------------------------------------------------------------------------
# app_detection tests
# ---------------------------------------------------------------------------

class TestAppDetection(unittest.TestCase):

    def test_detect_installed_apps_returns_required_keys(self):
        from onboarding.steps.app_detection import detect_installed_apps
        result = detect_installed_apps()
        for key in ("obs_installed", "discord_installed", "steam_installed",
                    "spotify_installed", "games"):
            self.assertIn(key, result)

    def test_detect_installed_apps_games_is_list(self):
        from onboarding.steps.app_detection import detect_installed_apps
        result = detect_installed_apps()
        self.assertIsInstance(result["games"], list)

    def test_run_returns_detected_apps_key(self):
        from onboarding.steps.app_detection import run
        result = run({})
        self.assertIn("detected_apps", result)
        self.assertIsInstance(result["detected_apps"], dict)


# ---------------------------------------------------------------------------
# stream_config tests
# ---------------------------------------------------------------------------

class TestStreamConfig(unittest.TestCase):

    def test_run_twitch_1080p_gaming(self):
        from onboarding.steps.stream_config import run
        with patch("builtins.input", side_effect=["1", "1", "1"]):
            result = run({})
        sc = result["stream_config"]
        self.assertEqual(sc["platform"], "twitch")
        self.assertEqual(sc["resolution"], "1080p")
        self.assertEqual(sc["default_scene"], "Gaming")

    def test_run_youtube_720p_just_chatting(self):
        from onboarding.steps.stream_config import run
        with patch("builtins.input", side_effect=["2", "2", "2"]):
            result = run({})
        sc = result["stream_config"]
        self.assertEqual(sc["platform"], "youtube")
        self.assertEqual(sc["resolution"], "720p")
        self.assertEqual(sc["default_scene"], "Just Chatting")

    def test_run_defaults_on_empty_input(self):
        from onboarding.steps.stream_config import run
        with patch("builtins.input", return_value=""):
            result = run({})
        sc = result["stream_config"]
        self.assertEqual(sc["platform"], "twitch")
        self.assertEqual(sc["resolution"], "1080p")
        self.assertEqual(sc["default_scene"], "Gaming")


# ---------------------------------------------------------------------------
# build_profile new fields tests
# ---------------------------------------------------------------------------

class TestBuildProfileNewFields(unittest.TestCase):

    def test_streamer_name_stored(self):
        from core.onboarding.onboarding_storage import build_profile
        p = build_profile("en", "houssem", streamer_name="HoussemTV")
        self.assertEqual(p["streamer_name"], "HoussemTV")

    def test_streamer_name_falls_back_to_username(self):
        from core.onboarding.onboarding_storage import build_profile
        p = build_profile("en", "houssem")
        self.assertEqual(p["streamer_name"], "houssem")

    def test_detected_apps_stored(self):
        from core.onboarding.onboarding_storage import build_profile
        apps = {"obs_installed": True, "games": ["valorant"]}
        p = build_profile("en", "x", detected_apps=apps)
        self.assertEqual(p["detected_apps"], apps)

    def test_detected_apps_defaults_to_empty_dict(self):
        from core.onboarding.onboarding_storage import build_profile
        p = build_profile("en", "x")
        self.assertEqual(p["detected_apps"], {})

    def test_stream_config_stored(self):
        from core.onboarding.onboarding_storage import build_profile
        sc = {"platform": "twitch", "resolution": "1080p", "default_scene": "Gaming"}
        p = build_profile("en", "x", stream_config=sc)
        self.assertEqual(p["stream_config"], sc)

    def test_stream_config_defaults_to_empty_dict(self):
        from core.onboarding.onboarding_storage import build_profile
        p = build_profile("en", "x")
        self.assertEqual(p["stream_config"], {})


# ---------------------------------------------------------------------------
# voice naturalizer mode= tests
# ---------------------------------------------------------------------------

class TestVoiceNaturalizerModes(unittest.TestCase):

    def _natural(self, text, mode, seed=42):
        import random as _random
        from voice.voice_naturalizer import naturalize_text
        rng = _random.Random(seed)
        return naturalize_text(text, mode=mode, rng=rng)

    def test_calm_mode_removes_exclamation(self):
        result = self._natural("Let's go!", mode="calm", seed=0)
        self.assertNotIn("!", result)

    def test_excited_mode_adds_exclamation(self):
        result = self._natural("You got a raid", mode="excited", seed=0)
        self.assertIn("!", result)

    def test_gaming_mode_returns_non_empty(self):
        result = self._natural("Launching game now", mode="gaming")
        self.assertTrue(len(result) > 0)

    def test_default_mode_unchanged_structure(self):
        from voice.voice_naturalizer import naturalize_text
        import random as _r
        rng = _r.Random(0)
        result = naturalize_text("Hello", hesitation_rate=0.0, mode="default", rng=rng)
        self.assertEqual(result, "Hello")

    def test_unknown_mode_falls_back_gracefully(self):
        result = self._natural("Test text", mode="unknown_mode")
        self.assertTrue(len(result) > 0)


if __name__ == "__main__":
    unittest.main()
