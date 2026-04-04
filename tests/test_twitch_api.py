"""
tests/test_twitch_api.py
=========================
Unit tests for integrations/twitch_api.py.

All HTTP requests are mocked with `unittest.mock.patch` so no network
access is required and no real Twitch credentials are needed.
"""

from unittest.mock import MagicMock, patch

import pytest
from integrations.twitch_api import TwitchAPI


DUMMY_CONFIG_WITH_CREDS: dict = {
    "twitch": {
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
        "channel": "test_channel",
    }
}

DUMMY_CONFIG_NO_CREDS: dict = {
    "twitch": {
        "client_id": "",
        "client_secret": "",
        "channel": "",
    }
}

TOP_GAMES_RESPONSE = {
    "data": [
        {"id": "1", "name": "Fortnite", "box_art_url": ""},
        {"id": "2", "name": "Valorant", "box_art_url": ""},
        {"id": "3", "name": "Minecraft", "box_art_url": ""},
        {"id": "4", "name": "CS2", "box_art_url": ""},
        {"id": "5", "name": "Apex Legends", "box_art_url": ""},
        {"id": "6", "name": "League of Legends", "box_art_url": ""},
    ]
}

TOKEN_RESPONSE = {
    "access_token": "fake_token_abc123",
    "expires_in": 3600,
    "token_type": "bearer",
}


def _make_mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


@pytest.fixture()
def api_with_creds() -> TwitchAPI:
    return TwitchAPI(DUMMY_CONFIG_WITH_CREDS)


@pytest.fixture()
def api_no_creds() -> TwitchAPI:
    return TwitchAPI(DUMMY_CONFIG_NO_CREDS)


class TestTokenAcquisition:
    def test_token_obtained_successfully(self, api_with_creds):
        api_with_creds._session.post = MagicMock(
            return_value=_make_mock_response(TOKEN_RESPONSE)
        )
        result = api_with_creds._ensure_token()
        assert result is True
        assert api_with_creds._access_token == "fake_token_abc123"

    def test_no_creds_returns_false(self, api_no_creds):
        result = api_no_creds._ensure_token()
        assert result is False

    def test_network_error_returns_false(self, api_with_creds):
        api_with_creds._session.post = MagicMock(side_effect=Exception("network error"))
        result = api_with_creds._ensure_token()
        assert result is False

    def test_session_is_reused(self, api_with_creds):
        """The same session object should be used for all requests."""
        session_id = id(api_with_creds._session)
        # Inject token so _ensure_token doesn't need to POST
        api_with_creds._access_token = "tok"
        api_with_creds._token_expiry = float("inf")
        api_with_creds._session.get = MagicMock(
            return_value=_make_mock_response(TOP_GAMES_RESPONSE)
        )
        api_with_creds.get_top_games(limit=3)
        api_with_creds.get_top_games(limit=3)
        assert id(api_with_creds._session) == session_id


class TestGetTopGames:
    def _patch_token(self, api):
        """Pre-inject a valid token so tests skip the token acquisition step."""
        api._access_token = "fake_token"
        api._token_expiry = float("inf")

    def test_returns_game_list(self, api_with_creds):
        self._patch_token(api_with_creds)
        api_with_creds._session.get = MagicMock(
            return_value=_make_mock_response(TOP_GAMES_RESPONSE)
        )
        games = api_with_creds.get_top_games(limit=5)
        assert len(games) == 6  # mock returns 6 games
        assert games[0]["name"] == "Fortnite"

    def test_no_creds_returns_empty(self, api_no_creds):
        games = api_no_creds.get_top_games()
        assert games == []

    def test_network_error_returns_empty(self, api_with_creds):
        self._patch_token(api_with_creds)
        api_with_creds._session.get = MagicMock(side_effect=Exception("timeout"))
        games = api_with_creds.get_top_games()
        assert games == []


class TestSuggestGame:
    def _patch_token(self, api):
        api._access_token = "fake_token"
        api._token_expiry = float("inf")

    def test_suggest_skips_top_5(self, api_with_creds):
        self._patch_token(api_with_creds)
        api_with_creds._session.get = MagicMock(
            return_value=_make_mock_response(TOP_GAMES_RESPONSE)
        )
        suggestion = api_with_creds.suggest_game(top_n=6, skip_top=5)
        # Should return the 6th game (index 5) = "League of Legends"
        assert suggestion == "League of Legends"

    def test_suggest_fallback_when_skip_exceeds_results(self, api_with_creds):
        self._patch_token(api_with_creds)
        small_response = {"data": [{"id": "1", "name": "Fortnite", "box_art_url": ""}]}
        api_with_creds._session.get = MagicMock(
            return_value=_make_mock_response(small_response)
        )
        suggestion = api_with_creds.suggest_game(top_n=1, skip_top=5)
        # Fallback: last item in the list
        assert suggestion == "Fortnite"

    def test_no_creds_returns_none(self, api_no_creds):
        suggestion = api_no_creds.suggest_game()
        assert suggestion is None

