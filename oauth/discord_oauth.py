"""
oauth/discord_oauth.py
=======================
Discord bot token collection helper for AURA.

Discord bots authenticate with a **bot token** rather than an OAuth2 user
flow.  This helper guides the user to:

1. Create a Discord application and bot at https://discord.com/developers
2. Copy their bot token
3. Paste it here

The helper also prompts for the target channel ID (used for announcements).

Usage::

    from oauth.discord_oauth import collect_discord_credentials

    result = collect_discord_credentials()   # interactive; reads from stdin
    if result:
        print(result["discord_bot_token"])
        print(result["discord_channel_id"])
"""

from __future__ import annotations

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_DISCORD_API = "https://discord.com/api/v10"


def validate_bot_token(token: str) -> bool:
    """
    Validate a Discord bot token by calling the ``/users/@me`` endpoint.

    Returns ``True`` when the token is valid, ``False`` otherwise.
    """
    if not token:
        return False
    auth = token if token.startswith("Bot ") else f"Bot {token}"
    try:
        resp = requests.get(
            f"{_DISCORD_API}/users/@me",
            headers={"Authorization": auth},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception as exc:  # pylint: disable=broad-except
        logger.debug("Discord token validation error: %s", exc)
        return False


def collect_discord_credentials(
    *,
    skip_allowed: bool = True,
) -> Optional[dict]:
    """
    Interactive CLI helper that collects a Discord bot token + channel ID.

    Parameters
    ----------
    skip_allowed:
        If ``True`` (default), the user can press Enter to skip and return
        ``None``.

    Returns
    -------
    dict with ``discord_bot_token`` and ``discord_channel_id``, or ``None``
    if the user skips.
    """
    print()
    print("─── Discord Integration (optional) ───")
    print("To enable Discord announcements, you need a Discord bot token.")
    print("Steps:")
    print("  1. Visit https://discord.com/developers/applications")
    print("  2. Create a new Application, then add a Bot")
    print("  3. Copy the Bot Token and paste it below")
    print()

    if skip_allowed:
        print("  Press Enter (blank) to skip Discord integration.")

    while True:
        token = input("Discord Bot Token: ").strip()
        if not token:
            if skip_allowed:
                print("  Discord integration skipped.")
                return None
            print("  Token is required. Please paste your bot token.")
            continue

        print("  Validating token…", end="", flush=True)
        if validate_bot_token(token):
            print(" OK")
            break
        print(" FAILED")
        print("  Invalid token. Please check and try again, or press Enter to skip.")
        if skip_allowed:
            retry = input("  Try again? (y/n) [n]: ").strip().lower()
            if retry != "y":
                print("  Discord integration skipped.")
                return None

    print()
    channel_id = input(
        "Discord Channel ID for announcements (press Enter to skip): "
    ).strip()

    if not channel_id:
        print("  No channel configured – announcements will be disabled.")

    return {
        "discord_bot_token": token,
        "discord_channel_id": channel_id,
    }
