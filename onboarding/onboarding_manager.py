"""
onboarding/onboarding_manager.py
==================================
Orchestrates all 8 onboarding steps for AURA's first-launch experience.

The manager runs each step in sequence, accumulating profile data, and
supports cancellation at the confirmation prompt.

Steps
-----
1. Language selection
2. User profile (nickname + streamer name)
3. App auto-detection (OBS, Discord, Steam, games)
4. Twitch setup (optional OAuth)
5. Discord setup (optional)
6. OBS auto-setup (port detection)
7. Stream configuration (platform / resolution / scene)
8. Save config to ``config/user_profile.json``

Usage::

    from onboarding import OnboardingManager

    manager = OnboardingManager()
    if manager.run():
        print("Onboarding complete!")
    else:
        print("Cancelled.")
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class OnboardingManager:
    """Runs the full 8-step CLI onboarding wizard.

    Parameters
    ----------
    skip_app_detection:
        When ``True`` (useful in tests) the app-detection step is skipped
        and an empty ``detected_apps`` dict is inserted instead.
    """

    def __init__(self, *, skip_app_detection: bool = False) -> None:
        self._skip_app_detection = skip_app_detection

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> bool:
        """Execute the full onboarding wizard.

        Returns
        -------
        bool
            ``True`` if onboarding completed and the profile was saved,
            ``False`` if the user cancelled or a save error occurred.
        """
        print("\n" + "=" * 60)
        print("  AURA – First Launch Setup")
        print("=" * 60)

        data: dict[str, Any] = {}

        # Import step modules lazily to keep startup fast
        from onboarding.steps import language_selection  # noqa: PLC0415
        from onboarding.steps import user_profile        # noqa: PLC0415
        from onboarding.steps import app_detection       # noqa: PLC0415
        from onboarding.steps import twitch_setup        # noqa: PLC0415
        from onboarding.steps import discord_setup       # noqa: PLC0415
        from onboarding.steps import obs_setup           # noqa: PLC0415
        from onboarding.steps import stream_config       # noqa: PLC0415
        from onboarding.steps import save_config         # noqa: PLC0415

        steps = [
            ("Step 1/8 — Language",           language_selection),
            ("Step 2/8 — User Profile",        user_profile),
            ("Step 3/8 — App Detection",       app_detection),
            ("Step 4/8 — Twitch Setup",        twitch_setup),
            ("Step 5/8 — Discord Setup",       discord_setup),
            ("Step 6/8 — OBS Setup",           obs_setup),
            ("Step 7/8 — Stream Config",       stream_config),
        ]

        for label, module in steps:
            logger.debug("Onboarding: %s", label)
            # App detection can be skipped (e.g. in tests)
            if module is app_detection and self._skip_app_detection:
                data["detected_apps"] = {
                    "obs_installed": False,
                    "discord_installed": False,
                    "steam_installed": False,
                    "spotify_installed": False,
                    "games": [],
                }
                continue
            updates = module.run(data)
            data.update(updates)

        # Confirmation
        if not self._confirm(data):
            print("Setup cancelled.")
            return False

        # Step 8 — Save
        result = save_config.run(data)
        return result.get("saved", False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _confirm(self, data: dict[str, Any]) -> bool:
        """Print a summary and ask the user to confirm."""
        from core.i18n import t  # noqa: PLC0415

        none_str = t("onboarding.confirm_none")
        lang = data.get("language", "en")
        stream_cfg = data.get("stream_config", {})

        print("\n" + "-" * 60)
        print(f"  {t('onboarding.confirm_language')}: {'Français' if lang == 'fr' else 'English'}")
        print(f"  {t('onboarding.confirm_username')}: {data.get('username', none_str)}")
        streamer = data.get("streamer_name", "")
        if streamer and streamer != data.get("username"):
            print(f"  Streamer name:   {streamer}")
        print(f"  {t('onboarding.confirm_twitch')}:   {data.get('twitch') or none_str}")
        print(f"  Twitch OAuth:    {'configured' if data.get('twitch_access_token') else none_str}")
        print(f"  Discord:         {'configured' if data.get('discord_bot_token') else none_str}")
        obs_port = data.get("obs_auto_detected_port")
        print(f"  OBS port:        {obs_port or none_str}")
        if stream_cfg:
            plat = stream_cfg.get("platform", none_str)
            res  = stream_cfg.get("resolution", none_str)
            scene = stream_cfg.get("default_scene", none_str)
            print(f"  Stream:          {plat} / {res} / '{scene}'")
        apps = data.get("detected_apps", {})
        games = apps.get("games", [])
        if games:
            print(f"  Games detected:  {', '.join(games)}")
        print("-" * 60)

        answer = input("\nConfirm? (y/n) [y]: ").strip().lower()
        return answer != "n"
