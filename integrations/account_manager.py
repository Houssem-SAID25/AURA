"""
integrations/account_manager.py
================================
Manages OAuth2 account connections for Twitch, Discord, and YouTube.

Each ``connect_*()`` method:
1. Opens the system browser at the platform's OAuth authorization URL.
2. Starts the local callback server (:mod:`oauth.oauth_server`).
3. Waits for the authorization code to be received.
4. Exchanges the code for an access token.
5. Fetches the user's display name.
6. Persists the tokens back to ``config.json``.

All network calls run on the calling thread (intended for use in a background
:class:`threading.Thread` spawned by the GUI).

Usage
-----
    from integrations.account_manager import AccountManager

    mgr = AccountManager(config, config_path="config.json")
    mgr.connect_twitch()
    print(mgr.get_status())   # {"twitch": True, "discord": False, "youtube": False}
"""

from __future__ import annotations

import json
import logging
import os
import webbrowser
from typing import Any

logger = logging.getLogger(__name__)

# Repository root – two levels up from this file
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class AccountManager:
    """Handles OAuth2 account linking for Twitch, Discord, and YouTube.

    Parameters
    ----------
    config:
        The current application configuration dict.
    config_path:
        Path to ``config.json`` relative to the repository root.  Used when
        persisting token updates.
    """

    def __init__(self, config: dict, config_path: str = "config.json") -> None:
        self._config = config
        self._config_path = os.path.join(_REPO_ROOT, config_path)

    # ------------------------------------------------------------------
    # Connection methods
    # ------------------------------------------------------------------

    def connect_twitch(self) -> bool:
        """Run the Twitch OAuth2 flow.

        Returns
        -------
        bool
            ``True`` if the flow completed successfully.
        """
        from oauth import twitch_oauth  # noqa: PLC0415
        from oauth.oauth_server import start_server, wait_for_code  # noqa: PLC0415

        client_id = self._config.get("twitch", {}).get("client_id", "")
        client_secret = self._config.get("twitch", {}).get("client_secret", "")
        if not client_id or not client_secret:
            logger.error("Twitch client_id / client_secret are not configured.")
            return False

        start_server()
        auth_url = twitch_oauth.get_auth_url(client_id)
        webbrowser.open(auth_url)
        logger.info("Opened Twitch auth URL; waiting for callback…")

        code = wait_for_code(timeout=120)
        if not code:
            return False

        tokens = twitch_oauth.exchange_code(client_id, client_secret, code)
        if not tokens.get("access_token"):
            return False

        user_info = twitch_oauth.get_user_info(tokens["access_token"], client_id)
        accounts = self._config.setdefault("accounts", {})
        accounts["twitch"] = {
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "display_name": user_info.get("display_name"),
        }
        self._save_config()
        logger.info("Twitch account linked: %s", user_info.get("display_name"))
        return True

    def connect_discord(self) -> bool:
        """Run the Discord OAuth2 user flow.

        Returns
        -------
        bool
            ``True`` if the flow completed successfully.
        """
        from oauth import discord_oauth  # noqa: PLC0415
        from oauth.oauth_server import start_server, wait_for_code  # noqa: PLC0415

        client_id = self._config.get("discord", {}).get("client_id", "")
        client_secret = self._config.get("discord", {}).get("client_secret", "")
        if not client_id or not client_secret:
            logger.error("Discord client_id / client_secret are not configured.")
            return False

        start_server()
        auth_url = discord_oauth.get_auth_url(client_id)
        webbrowser.open(auth_url)
        logger.info("Opened Discord auth URL; waiting for callback…")

        code = wait_for_code(timeout=120)
        if not code:
            return False

        tokens = discord_oauth.exchange_code(client_id, client_secret, code)
        if not tokens.get("access_token"):
            return False

        user_info = discord_oauth.get_user_info(tokens["access_token"])
        accounts = self._config.setdefault("accounts", {})
        accounts["discord"] = {
            "access_token": tokens.get("access_token"),
            "display_name": user_info.get("display_name"),
        }
        self._save_config()
        logger.info("Discord account linked: %s", user_info.get("display_name"))
        return True

    def connect_youtube(self) -> bool:
        """Run the YouTube OAuth2 InstalledApp flow.

        Returns
        -------
        bool
            ``True`` if the flow completed successfully.
        """
        from oauth.youtube_oauth import authenticate  # noqa: PLC0415

        credentials_file = (
            self._config.get("accounts", {})
            .get("youtube", {})
            .get("credentials_file") or ""
        )
        if not credentials_file or not os.path.isfile(credentials_file):
            logger.error(
                "YouTube credentials file not found: '%s'. "
                "Download client_secrets.json from the Google Cloud Console and set "
                "accounts.youtube.credentials_file in config.json.",
                credentials_file,
            )
            return False

        creds, channel_name = authenticate(credentials_file)
        if creds is None:
            return False

        accounts = self._config.setdefault("accounts", {})
        accounts["youtube"] = {
            "credentials_file": credentials_file,
            "channel_name": channel_name,
        }
        self._save_config()
        logger.info("YouTube account linked: %s", channel_name)
        return True

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, bool]:
        """Return connection status for each platform.

        Returns
        -------
        dict
            ``{"twitch": bool, "discord": bool, "youtube": bool}``
        """
        accounts: dict[str, Any] = self._config.get("accounts", {})
        return {
            "twitch": bool(
                accounts.get("twitch", {}) and accounts["twitch"].get("access_token")
            ),
            "discord": bool(
                accounts.get("discord", {}) and accounts["discord"].get("access_token")
            ),
            "youtube": bool(
                accounts.get("youtube", {}) and accounts["youtube"].get("channel_name")
            ),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _save_config(self) -> None:
        """Persist the in-memory config back to ``config.json``."""
        try:
            with open(self._config_path, "w", encoding="utf-8") as fh:
                json.dump(self._config, fh, indent=2, ensure_ascii=False)
            logger.debug("Config saved to '%s'.", self._config_path)
        except OSError as exc:
            logger.error("Could not save config: %s", exc)
