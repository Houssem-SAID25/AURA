"""
onboarding/steps/twitch_setup.py
==================================
Step 4 — Twitch Setup (optional OAuth).
"""
from __future__ import annotations
from typing import Any


def run(data: dict[str, Any]) -> dict[str, Any]:
    from core.i18n import t  # noqa: PLC0415
    from core.onboarding.onboarding_storage import validate_twitch  # noqa: PLC0415

    print()
    while True:
        twitch = input(
            f"{t('onboarding.twitch_label')} [{t('onboarding.confirm_none')}]: "
        ).strip()
        if not twitch or validate_twitch(twitch):
            break
        print(f"  ! {t('onboarding.twitch_invalid')}")

    updates: dict[str, Any] = {
        "twitch": twitch,
        "twitch_access_token": "",
        "twitch_refresh_token": "",
        "twitch_user_id": "",
        "twitch_login": "",
    }
    if not twitch:
        return updates

    print()
    if input("Connect Twitch account for live alerts (raids/follows/subs)? (y/n) [n]: ").strip().lower() != "y":
        return updates

    try:
        from utils.config_loader import load_config  # noqa: PLC0415
        cfg = load_config()
        client_id = cfg.get("twitch", {}).get("client_id", "")
        client_secret = cfg.get("twitch", {}).get("client_secret", "")
        if not client_id or not client_secret:
            print("  Twitch client_id/client_secret not configured. Skipping OAuth.")
            return updates
        from oauth.twitch_oauth import TwitchOAuth  # noqa: PLC0415
        result = TwitchOAuth(client_id, client_secret).authorize()
        if result:
            updates.update({
                "twitch_access_token": result.get("access_token", ""),
                "twitch_refresh_token": result.get("refresh_token", ""),
                "twitch_user_id": result.get("user_id", ""),
                "twitch_login": result.get("user_login", ""),
            })
            print(f"  Twitch connected: @{updates['twitch_login']}")
        else:
            print("  Twitch OAuth failed or timed out. Skipping.")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"  Twitch OAuth error: {exc}. Skipping.")
    return updates
