"""
tests/test_discord_bot.py
==========================
Unit tests for integrations/discord_bot.py.

All HTTP calls are mocked – no real Discord connection is made.
"""

from unittest.mock import MagicMock, patch

import pytest

from integrations.discord_bot import DiscordNotifier


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ENABLED_CONFIG = {
    "discord": {"announce_stream": True},
}

ENABLED_PROFILE = {
    "discord_bot_token": "testtoken123",
    "discord_channel_id": "111222333444555666",
}

DISABLED_CONFIG = {"discord": {"announce_stream": False}}
DISABLED_PROFILE: dict = {}


@pytest.fixture()
def notifier():
    return DiscordNotifier(ENABLED_CONFIG, ENABLED_PROFILE)


@pytest.fixture()
def disabled_notifier():
    return DiscordNotifier(DISABLED_CONFIG, DISABLED_PROFILE)


def _mock_response(status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = ""
    return resp


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestDiscordNotifierInit:
    def test_enabled_when_configured(self, notifier):
        assert notifier._enabled is True

    def test_disabled_when_no_token(self):
        n = DiscordNotifier(ENABLED_CONFIG, {"discord_channel_id": "123"})
        assert n._enabled is False

    def test_disabled_when_no_channel(self):
        n = DiscordNotifier(ENABLED_CONFIG, {"discord_bot_token": "tok"})
        assert n._enabled is False

    def test_disabled_when_announce_false(self):
        n = DiscordNotifier(DISABLED_CONFIG, ENABLED_PROFILE)
        assert n._enabled is False

    def test_token_prefix_added(self, notifier):
        assert notifier._token.startswith("Bot ")

    def test_token_prefix_not_doubled(self):
        profile = {"discord_bot_token": "Bot already_prefixed", "discord_channel_id": "123"}
        n = DiscordNotifier(ENABLED_CONFIG, profile)
        assert n._token == "Bot already_prefixed"

    def test_empty_profile_is_accepted(self):
        n = DiscordNotifier({}, None)
        assert n._enabled is False


# ---------------------------------------------------------------------------
# send_message
# ---------------------------------------------------------------------------

class TestSendMessage:
    def test_send_success(self, notifier):
        with patch("requests.post", return_value=_mock_response(200)) as mock_post:
            result = notifier.send_message("Hello!")
        assert result is True
        mock_post.assert_called_once()

    def test_send_201_also_success(self, notifier):
        with patch("requests.post", return_value=_mock_response(201)):
            result = notifier.send_message("Hello!")
        assert result is True

    def test_send_failure_returns_false(self, notifier):
        with patch("requests.post", return_value=_mock_response(403)):
            result = notifier.send_message("Hello!")
        assert result is False

    def test_send_network_error_returns_false(self, notifier):
        with patch("requests.post", side_effect=ConnectionError("timeout")):
            result = notifier.send_message("Hello!")
        assert result is False

    def test_text_truncated_to_2000_chars(self, notifier):
        long_text = "x" * 3000
        with patch("requests.post", return_value=_mock_response(200)) as mock_post:
            notifier.send_message(long_text)
        sent_body = mock_post.call_args.kwargs["json"]["content"]
        assert len(sent_body) == 2000

    def test_no_request_when_no_token(self, disabled_notifier):
        with patch("requests.post") as mock_post:
            result = disabled_notifier.send_message("Hello!", channel_id="123")
        mock_post.assert_not_called()
        assert result is False

    def test_channel_id_override(self, notifier):
        with patch("requests.post", return_value=_mock_response(200)) as mock_post:
            notifier.send_message("Hi!", channel_id="999888777")
        url = mock_post.call_args.args[0]
        assert "999888777" in url


# ---------------------------------------------------------------------------
# announce_stream_live
# ---------------------------------------------------------------------------

class TestAnnounceStreamLive:
    def test_sends_message(self, notifier):
        with patch.object(notifier, "send_message", return_value=True) as mock_send:
            result = notifier.announce_stream_live("Minecraft", "Chill stream")
        assert result is True
        mock_send.assert_called_once()
        content = mock_send.call_args[0][0]
        assert "Minecraft" in content
        assert "Chill stream" in content

    def test_no_game_still_sends(self, notifier):
        with patch.object(notifier, "send_message", return_value=True) as mock_send:
            notifier.announce_stream_live()
        mock_send.assert_called_once()

    def test_disabled_returns_false(self, disabled_notifier):
        with patch.object(disabled_notifier, "send_message") as mock_send:
            result = disabled_notifier.announce_stream_live("CS2")
        assert result is False
        mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# announce_stream_offline
# ---------------------------------------------------------------------------

class TestAnnounceStreamOffline:
    def test_sends_message(self, notifier):
        with patch.object(notifier, "send_message", return_value=True) as mock_send:
            result = notifier.announce_stream_offline()
        assert result is True
        mock_send.assert_called_once()
        content = mock_send.call_args[0][0]
        assert "ended" in content.lower() or "offline" in content.lower()

    def test_disabled_returns_false(self, disabled_notifier):
        result = disabled_notifier.announce_stream_offline()
        assert result is False
