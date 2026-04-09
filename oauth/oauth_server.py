"""
oauth/oauth_server.py
=====================
Minimal local HTTP callback server for OAuth2 Authorization Code flows.

Starts an ``http.server.HTTPServer`` on ``localhost:8765`` that captures the
``code`` query parameter from the browser redirect and makes it available to
the caller via :func:`wait_for_code`.

Usage
-----
    from oauth.oauth_server import start_server, wait_for_code

    start_server()
    # … open browser with auth URL that redirects to http://localhost:8765/callback
    code = wait_for_code(timeout=120)
    if code:
        print("Got code:", code)
"""

from __future__ import annotations

import logging
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

logger = logging.getLogger(__name__)

_CALLBACK_HOST = "localhost"
_CALLBACK_PORT = 8765
_CALLBACK_PATH = "/callback"

REDIRECT_URI = f"http://{_CALLBACK_HOST}:{_CALLBACK_PORT}{_CALLBACK_PATH}"

# Shared state between the HTTP handler and the main thread
_state: dict = {
    "code": None,
    "error": None,
}
_code_event = threading.Event()
_server: Optional[HTTPServer] = None
_server_thread: Optional[threading.Thread] = None


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that captures the OAuth ``code`` query parameter."""

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != _CALLBACK_PATH:
            self._respond(404, "Not Found")
            return

        params = dict(urllib.parse.parse_qsl(parsed.query))
        if "error" in params:
            _state["error"] = params.get("error_description", params["error"])
            self._respond(200, "Authorization failed. You can close this tab.")
            _code_event.set()
        elif "code" in params:
            _state["code"] = params["code"]
            self._respond(200, "Authorization successful! You can close this tab and return to AURA.")
            _code_event.set()
        else:
            self._respond(400, "Bad Request")

    def _respond(self, code: int, body: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *args) -> None:  # noqa: ANN002
        """Suppress default access log output."""


def start_server() -> None:
    """Start the OAuth callback server in a background thread.

    It is safe to call this multiple times; subsequent calls are no-ops if the
    server is already running.
    """
    global _server, _server_thread  # noqa: PLW0603

    if _server is not None:
        return

    # Reset shared state
    _state["code"] = None
    _state["error"] = None
    _code_event.clear()

    try:
        _server = HTTPServer((_CALLBACK_HOST, _CALLBACK_PORT), _OAuthCallbackHandler)
    except OSError as exc:
        logger.error(
            "Could not start OAuth callback server on port %d: %s",
            _CALLBACK_PORT, exc,
        )
        return

    _server_thread = threading.Thread(
        target=_server.serve_forever, daemon=True, name="AURA-OAuthServer"
    )
    _server_thread.start()
    logger.info(
        "OAuth callback server listening on http://%s:%d%s",
        _CALLBACK_HOST, _CALLBACK_PORT, _CALLBACK_PATH,
    )


def stop_server() -> None:
    """Shut down the callback server."""
    global _server, _server_thread  # noqa: PLW0603

    if _server is not None:
        _server.shutdown()
        _server = None
        _server_thread = None


def wait_for_code(timeout: int = 120) -> Optional[str]:
    """Block until the OAuth code is received or *timeout* seconds elapse.

    Parameters
    ----------
    timeout:
        Maximum seconds to wait for the browser redirect.

    Returns
    -------
    str or None
        The authorization ``code``, or ``None`` on timeout / error.
    """
    received = _code_event.wait(timeout=timeout)
    stop_server()

    if not received:
        logger.error("OAuth callback timed out after %d seconds.", timeout)
        return None

    if _state.get("error"):
        logger.error("OAuth error received: %s", _state["error"])
        return None

    return _state.get("code")
