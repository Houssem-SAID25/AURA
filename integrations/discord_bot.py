"""
integrations/discord_bot.py
============================
Discord notification integration for AURA.

``DiscordNotifier`` sends messages to a configured Discord channel using the
Discord HTTP API directly (no gateway connection required for simple
outgoing messages).  This approach works with a standard bot token and
requires no persistent WebSocket connection, keeping resource usage minimal.

Configuration comes from ``config/user_profile.json``::

    {
        "discord_bot_token": "Bot <token>",
        "discord_channel_id": "123456789012345678"
    }

And optionally from ``config.json``::

    "discord": {
        "announce_stream": true
    }

If ``discord_bot_token`` is missing or empty the notifier runs in **disabled**
mode: all methods succeed silently without making any network requests.

Usage::

    notifier = DiscordNotifier(config, profile)
    notifier.announce_stream_live("Minecraft", "Chill survival stream!")
    notifier.send_message("Hello chat, AURA is online!")
    notifier.announce_stream_offline()
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Discord REST API base
_DISCORD_API = "https://discord.com/api/v10"


class DiscordNotifier:
    """
    Sends outgoing notifications to a Discord channel via the REST API.

    All public methods are safe to call even when unconfigured: they log a
    debug message and return immediately without raising.
    """

    def __init__(self, config: dict, profile: Optional[dict] = None) -> None:
        profile = profile or {}
        discord_cfg = config.get("discord", {})

        raw_token: str = profile.get("discord_bot_token", "")
        # Normalise – Discord expects the token prefixed with "Bot "
        if raw_token and not raw_token.startswith("Bot "):
            raw_token = f"Bot {raw_token}"

        self._token: str = raw_token
        self._channel_id: str = profile.get("discord_channel_id", "")
        self._enabled: bool = bool(
            self._token and self._channel_id and discord_cfg.get("announce_stream", False)
        )

        if self._enabled:
            logger.info(
                "DiscordNotifier enabled for channel %s.", self._channel_id
            )
        else:
            logger.debug("DiscordNotifier disabled (no token/channel_id configured).")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_message(self, text: str, channel_id: Optional[str] = None) -> bool:
        """
        Send *text* to the configured Discord channel (or *channel_id*).

        Parameters
        ----------
        text:
            The message content to send (max 2000 chars per Discord limit).
        channel_id:
            Override channel ID.  Uses the profile channel by default.

        Returns
        -------
        bool
            ``True`` on success, ``False`` otherwise.
        """
        target = channel_id or self._channel_id
        if not self._token or not target:
            logger.debug("DiscordNotifier.send_message: not configured, skipping.")
            return False

        text = text[:2000]  # Discord message length limit
        try:
            import requests  # noqa: PLC0415

            resp = requests.post(
                f"{_DISCORD_API}/channels/{target}/messages",
                headers={
                    "Authorization": self._token,
                    "Content-Type": "application/json",
                },
                json={"content": text},
                timeout=10,
            )
            if resp.status_code in (200, 201):
                logger.info("Discord message sent to channel %s.", target)
                return True
            logger.warning(
                "Discord message failed (HTTP %d): %s", resp.status_code, resp.text[:200]
            )
            return False
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("DiscordNotifier.send_message error: %s", exc)
            return False

    def announce_stream_live(
        self,
        game: str = "",
        title: str = "",
        channel_id: Optional[str] = None,
    ) -> bool:
        """
        Post a "stream is live" announcement.

        Parameters
        ----------
        game:
            The game being streamed (optional).
        title:
            Stream title (optional).
        channel_id:
            Override channel ID.

        Returns ``True`` on success.
        """
        if not self._enabled:
            return False

        parts = [":red_circle: **Stream is live!**"]
        if game:
            parts.append(f"Playing: **{game}**")
        if title:
            parts.append(f"> {title}")
        message = "\n".join(parts)
        return self.send_message(message, channel_id)

    def announce_stream_offline(self, channel_id: Optional[str] = None) -> bool:
        """
        Post a "stream ended" announcement.

        Returns ``True`` on success.
        """
        if not self._enabled:
            return False

        message = ":black_circle: **Stream ended.** Thanks for watching! See you next time!"
        return self.send_message(message, channel_id)
