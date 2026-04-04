"""
onboarding/steps/save_config.py
=================================
Step 8 — Save Config.

Builds the final profile dict from accumulated data and persists it to
``config/user_profile.json``.
"""
from __future__ import annotations
from typing import Any


def run(data: dict[str, Any]) -> dict[str, Any]:
    from core.i18n import t  # noqa: PLC0415
    from core.onboarding.onboarding_storage import build_profile, save_profile  # noqa: PLC0415

    profile = build_profile(
        language=data.get("language", "en"),
        username=data.get("username", ""),
        streamer_name=data.get("streamer_name", ""),
        twitch=data.get("twitch", ""),
        other_links=data.get("other_links", ""),
        twitch_access_token=data.get("twitch_access_token", ""),
        twitch_refresh_token=data.get("twitch_refresh_token", ""),
        twitch_user_id=data.get("twitch_user_id", ""),
        twitch_login=data.get("twitch_login", ""),
        discord_bot_token=data.get("discord_bot_token", ""),
        discord_channel_id=data.get("discord_channel_id", ""),
        obs_auto_detected_port=data.get("obs_auto_detected_port"),
        detected_apps=data.get("detected_apps"),
        stream_config=data.get("stream_config"),
    )

    if not save_profile(profile):
        print(f"\n! {t('onboarding.save_error')}")
        return {"saved": False}

    print(f"\n{t('onboarding.done_message', username=profile.get('username', ''))}\n")
    return {"saved": True}
