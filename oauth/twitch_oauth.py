"""
oauth/twitch_oauth.py
======================
Twitch OAuth2 Authorization Code flow helper for AURA.

Launches a temporary local HTTP callback server on ``localhost:3000``, opens
the Twitch authorization URL in the system browser, waits for the OAuth
redirect, then exchanges the authorization code for an access token + refresh
token.

Usage::

    from oauth.twitch_oauth import TwitchOAuth

    oauth = TwitchOAuth(client_id="...", client_secret="...")
    result = oauth.authorize()   # returns dict or None
    if result:
        print(result["access_token"])
        print(result["refresh_token"])
        print(result["user_login"])
        print(result["user_id"])

The function blocks until the callback is received (or the timeout expires).
It is designed to be called from the onboarding wizard.

Scopes requested (all free, no paid tiers):
- ``channel:read:subscriptions``
- ``moderator:read:followers``
- ``bits:read``
- ``channel:read:raids``
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_CALLBACK_PORT = 3000
_CALLBACK_HOST = "localhost"
_CALLBACK_PATH = "/callback"
_REDIRECT_URI = f"http://{_CALLBACK_HOST}:{_CALLBACK_PORT}{_CALLBACK_PATH}"

_AUTH_URL = "https://id.twitch.tv/oauth2/authorize"
_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
_USERS_URL = "https://api.twitch.tv/helix/users"

_SCOPES = [
    "channel:read:subscriptions",
    "moderator:read:followers",
    "bits:read",
    "channel:read:raids",
]

_TIMEOUT_SECONDS = 120  # wait up to 2 minutes for the browser callback


# ---------------------------------------------------------------------------
# Internal HTTP handler for the OAuth callback
# ---------------------------------------------------------------------------

class _CallbackHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that captures the OAuth code query parameter."""

    received_code: Optional[str] = None
    received_state: Optional[str] = None
    error: Optional[str] = None

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != _CALLBACK_PATH:
            self._respond(404, "Not Found")
            return

        params = dict(urllib.parse.parse_qsl(parsed.query))
        if "error" in params:
            _CallbackHandler.error = params.get("error_description", params["error"])
            self._respond(200, "Authorization failed. You can close this tab.")
        elif "code" in params:
            _CallbackHandler.received_code = params["code"]
            _CallbackHandler.received_state = params.get("state", "")
            self._respond(200, "Authorization successful! You can close this tab and return to AURA.")
        else:
            self._respond(400, "Bad Request")

    def _respond(self, code: int, body: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *args) -> None:  # noqa: ANN002
        """Suppress default access log output."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class TwitchOAuth:
    """Handles the Twitch OAuth2 Authorization Code flow."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret

    def authorize(self) -> Optional[dict]:
        """
        Open the browser, wait for the callback, and exchange the code.

        Returns
        -------
        dict with keys ``access_token``, ``refresh_token``, ``user_id``,
        ``user_login``, ``user_display_name`` on success; ``None`` on failure.
        """
        if not self._client_id or not self._client_secret:
            logger.error("Twitch client_id / client_secret are required for OAuth.")
            return None

        state = secrets.token_urlsafe(16)

        # Reset shared state
        _CallbackHandler.received_code = None
        _CallbackHandler.received_state = None
        _CallbackHandler.error = None

        # Start local callback server
        try:
            server = HTTPServer((_CALLBACK_HOST, _CALLBACK_PORT), _CallbackHandler)
        except OSError as exc:
            logger.error("Could not start OAuth callback server on port %d: %s", _CALLBACK_PORT, exc)
            return None

        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        # Build authorization URL and open browser
        auth_params = {
            "client_id": self._client_id,
            "redirect_uri": _REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(_SCOPES),
            "state": state,
            "force_verify": "true",
        }
        auth_url = f"{_AUTH_URL}?{urllib.parse.urlencode(auth_params)}"
        logger.info("Opening Twitch authorization URL: %s", auth_url)
        webbrowser.open(auth_url)

        # Wait for callback
        deadline = time.monotonic() + _TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if _CallbackHandler.received_code or _CallbackHandler.error:
                break
            time.sleep(0.25)

        server.shutdown()

        if _CallbackHandler.error:
            logger.error("Twitch OAuth error: %s", _CallbackHandler.error)
            return None

        code = _CallbackHandler.received_code
        if not code:
            logger.error("Twitch OAuth timed out (no code received within %ds).", _TIMEOUT_SECONDS)
            return None

        if _CallbackHandler.received_state != state:
            logger.error("Twitch OAuth state mismatch – possible CSRF attempt.")
            return None

        return self._exchange_code(code)

    def _exchange_code(self, code: str) -> Optional[dict]:
        """Exchange the authorization code for tokens and fetch user info."""
        try:
            resp = requests.post(
                _TOKEN_URL,
                params={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": _REDIRECT_URI,
                },
                timeout=15,
            )
            resp.raise_for_status()
            token_data = resp.json()
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Token exchange failed: %s", exc)
            return None

        access_token = token_data.get("access_token", "")
        refresh_token = token_data.get("refresh_token", "")

        # Fetch user info
        user_info = self._fetch_user(access_token)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user_id": user_info.get("id", ""),
            "user_login": user_info.get("login", ""),
            "user_display_name": user_info.get("display_name", ""),
        }

    def _fetch_user(self, access_token: str) -> dict:
        """Fetch the authenticated user's info from Helix."""
        try:
            resp = requests.get(
                _USERS_URL,
                headers={
                    "Client-Id": self._client_id,
                    "Authorization": f"Bearer {access_token}",
                },
                timeout=10,
            )
            resp.raise_for_status()
            users = resp.json().get("data", [])
            return users[0] if users else {}
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Could not fetch Twitch user info: %s", exc)
            return {}


# ---------------------------------------------------------------------------
# Module-level functional helpers (used by account_manager)
# ---------------------------------------------------------------------------

_ACCOUNT_SCOPES = [
    "channel:read:subscriptions",
    "user:read:email",
    "chat:read",
]


def get_auth_url(client_id: str, redirect_uri: str = _REDIRECT_URI) -> str:
    """Build the Twitch OAuth authorization URL.

    Parameters
    ----------
    client_id:
        Twitch application client ID.
    redirect_uri:
        OAuth redirect URI (default: ``http://localhost:8765/callback``).

    Returns
    -------
    str
        Full authorization URL to open in the browser.
    """
    from oauth.oauth_server import REDIRECT_URI as _SERVER_REDIRECT  # noqa: PLC0415
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri or _SERVER_REDIRECT,
        "response_type": "code",
        "scope": " ".join(_ACCOUNT_SCOPES),
        "force_verify": "true",
    }
    return f"{_AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str = _REDIRECT_URI,
) -> dict:
    """Exchange an authorization code for access + refresh tokens.

    Parameters
    ----------
    client_id:
        Twitch application client ID.
    client_secret:
        Twitch application client secret.
    code:
        Authorization code received from the OAuth callback.
    redirect_uri:
        Must match the redirect URI used to obtain the code.

    Returns
    -------
    dict
        ``{"access_token": …, "refresh_token": …}`` or empty dict on failure.
    """
    from oauth.oauth_server import REDIRECT_URI as _SERVER_REDIRECT  # noqa: PLC0415
    try:
        resp = requests.post(
            _TOKEN_URL,
            params={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri or _SERVER_REDIRECT,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "access_token": data.get("access_token", ""),
            "refresh_token": data.get("refresh_token", ""),
        }
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Twitch token exchange failed: %s", exc)
        return {}


def get_user_info(access_token: str, client_id: str) -> dict:
    """Fetch the authenticated user's profile from Twitch Helix.

    Parameters
    ----------
    access_token:
        Valid Twitch access token.
    client_id:
        Twitch application client ID.

    Returns
    -------
    dict
        ``{"display_name": …, "profile_image_url": …, "email": …}`` or empty
        dict on failure.
    """
    try:
        resp = requests.get(
            _USERS_URL,
            headers={
                "Client-Id": client_id,
                "Authorization": f"Bearer {access_token}",
            },
            timeout=10,
        )
        resp.raise_for_status()
        users = resp.json().get("data", [])
        if not users:
            return {}
        u = users[0]
        return {
            "display_name": u.get("display_name", ""),
            "profile_image_url": u.get("profile_image_url", ""),
            "email": u.get("email", ""),
        }
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Could not fetch Twitch user info: %s", exc)
        return {}

