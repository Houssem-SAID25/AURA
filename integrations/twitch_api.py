"""
integrations/twitch_api.py
==========================
Twitch API integration using the Twitch Helix REST API.

Features
--------
- Fetch the top N trending games by viewer count
- Suggest a game with healthy viewership that is not overly saturated

Authentication uses the client-credentials flow (app access token).
``client_id`` and ``client_secret`` are read from ``config.json``.

If credentials are missing or the request fails, all methods degrade
gracefully and return empty results instead of raising exceptions.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Twitch Helix API base URL
HELIX_BASE = "https://api.twitch.tv/helix"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"


class TwitchAPI:
    """Thin wrapper around the Twitch Helix API for game-discovery features."""

    def __init__(self, config: dict) -> None:
        self._twitch_cfg = config.get("twitch", {})
        self._client_id: str = self._twitch_cfg.get("client_id", "")
        self._client_secret: str = self._twitch_cfg.get("client_secret", "")
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0  # epoch seconds

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _ensure_token(self) -> bool:
        """Obtain or refresh an app access token if needed."""
        if self._access_token and time.time() < self._token_expiry:
            return True

        if not self._client_id or not self._client_secret:
            logger.warning(
                "Twitch client_id / client_secret not configured in config.json."
            )
            return False

        try:
            import requests  # noqa: PLC0415

            resp = requests.post(
                TOKEN_URL,
                params={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "client_credentials",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            # Expire 60 seconds early as a safety margin
            self._token_expiry = time.time() + data.get("expires_in", 3600) - 60
            logger.info("Twitch access token obtained (expires in ~%ds).", data.get("expires_in", 3600))
            return True
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Could not obtain Twitch token: %s", exc)
            return False

    def _headers(self) -> dict:
        """Return Helix API request headers."""
        return {
            "Client-Id": self._client_id,
            "Authorization": f"Bearer {self._access_token}",
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_top_games(self, limit: int = 5) -> list[dict]:
        """
        Fetch the top *limit* games on Twitch ordered by current viewer count.

        Returns a list of dicts with ``id``, ``name``, and ``box_art_url`` keys.
        Returns an empty list on failure.
        """
        if not self._ensure_token():
            return []

        try:
            import requests  # noqa: PLC0415

            resp = requests.get(
                f"{HELIX_BASE}/games/top",
                headers=self._headers(),
                params={"first": limit},
                timeout=10,
            )
            resp.raise_for_status()
            games = resp.json().get("data", [])
            logger.info(
                "Fetched %d trending game(s) from Twitch.", len(games)
            )
            for idx, game in enumerate(games, start=1):
                logger.info("  %d. %s", idx, game.get("name", "Unknown"))
            return games
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("get_top_games failed: %s", exc)
            return []

    def suggest_game(self, top_n: int = 20, skip_top: int = 5) -> Optional[str]:
        """
        Suggest a game that is popular but not overly saturated.

        Strategy: fetch the top *top_n* games and pick the first one outside
        the top *skip_top* (the very top games are assumed to be too saturated).

        Returns the game name string or ``None`` if unavailable.
        """
        games = self.get_top_games(limit=top_n)
        if not games:
            return None

        # Skip the most saturated games (position 0 to skip_top - 1)
        candidates = games[skip_top:]
        if candidates:
            choice = candidates[0]
            logger.info("Suggesting game: %s", choice.get("name"))
            return choice.get("name")

        # Fallback: return the last game in the top list
        if games:
            return games[-1].get("name")
        return None

    def get_streams_for_game(self, game_id: str, limit: int = 5) -> list[dict]:
        """
        Fetch live streams for the given Twitch *game_id*.

        Returns a list of stream dicts on success, or an empty list on failure.
        """
        if not game_id:
            return []
        if not self._ensure_token():
            return []

        try:
            import requests  # noqa: PLC0415

            resp = requests.get(
                f"{HELIX_BASE}/streams",
                headers=self._headers(),
                params={"game_id": game_id, "first": limit},
                timeout=10,
            )
            resp.raise_for_status()
            streams = resp.json().get("data", [])
            return streams
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("get_streams_for_game failed: %s", exc)
            return []
