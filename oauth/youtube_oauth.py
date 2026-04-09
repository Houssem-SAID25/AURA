"""
oauth/youtube_oauth.py
======================
YouTube Data API v3 OAuth2 authentication helper for AURA.

Uses ``google-auth-oauthlib`` (``InstalledAppFlow``) to perform the OAuth2
flow and returns credentials together with the authenticated channel's display
name via the YouTube Data API v3.

Usage
-----
    from oauth.youtube_oauth import authenticate

    creds, channel_name = authenticate("client_secrets.json")
    if creds:
        print("Logged in as:", channel_name)

Requires
--------
    pip install google-auth-oauthlib google-api-python-client
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


def authenticate(client_secrets_file: str) -> tuple[Optional[object], Optional[str]]:
    """Run the OAuth2 InstalledApp flow for the YouTube Data API v3.

    Opens the system browser for the user to grant access.  After the user
    approves, returns the credentials object and the channel display name.

    Parameters
    ----------
    client_secrets_file:
        Path to the OAuth2 client secrets JSON file downloaded from the
        Google Cloud Console.

    Returns
    -------
    tuple (credentials, channel_name)
        *credentials* is a :class:`google.oauth2.credentials.Credentials`
        instance, or ``None`` on failure.
        *channel_name* is the authenticated channel's display name, or
        ``None`` if it could not be fetched.
    """
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: PLC0415
    except ImportError:
        logger.error(
            "google-auth-oauthlib is not installed. "
            "Run: pip install google-auth-oauthlib google-api-python-client"
        )
        return None, None

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            client_secrets_file, scopes=_YOUTUBE_SCOPES
        )
        credentials = flow.run_local_server(port=0, open_browser=True)
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("YouTube OAuth flow failed: %s", exc)
        return None, None

    channel_name = _get_channel_name(credentials)
    return credentials, channel_name


def _get_channel_name(credentials: object) -> Optional[str]:
    """Fetch the authenticated channel's display name via YouTube Data API v3.

    Parameters
    ----------
    credentials:
        Valid Google OAuth2 credentials.

    Returns
    -------
    str or None
        Display name of the authenticated channel, or ``None`` on failure.
    """
    try:
        from googleapiclient.discovery import build  # noqa: PLC0415

        youtube = build("youtube", "v3", credentials=credentials)
        response = youtube.channels().list(part="snippet", mine=True).execute()
        items = response.get("items", [])
        if items:
            return items[0].get("snippet", {}).get("title")
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Could not fetch YouTube channel name: %s", exc)
    return None
