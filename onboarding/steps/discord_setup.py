"""
onboarding/steps/discord_setup.py
===================================
Step 5 — Discord Setup (optional).
"""
from __future__ import annotations
from typing import Any


def run(data: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {"discord_bot_token": "", "discord_channel_id": ""}
    print()
    if input("Connect Discord for stream announcements? (y/n) [n]: ").strip().lower() != "y":
        return updates
    try:
        from oauth.discord_oauth import collect_discord_credentials  # noqa: PLC0415
        creds = collect_discord_credentials(skip_allowed=True)
        if creds:
            updates["discord_bot_token"] = creds.get("discord_bot_token", "")
            updates["discord_channel_id"] = creds.get("discord_channel_id", "")
            if updates["discord_bot_token"]:
                print("  Discord configured successfully.")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"  Discord setup error: {exc}. Skipping.")
    return updates
