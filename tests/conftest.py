"""
tests/conftest.py
=================
Shared pytest fixtures and module-level mocks for the AURA test suite.

``obsws_python`` is an optional runtime dependency that requires a live
OBS Studio installation.  We inject a lightweight mock into ``sys.modules``
before any test imports so that tests can patch its symbols normally with
``unittest.mock.patch``.
"""

import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock obsws_python
# ---------------------------------------------------------------------------
# The OBSController imports obsws_python lazily inside _connect().
# Tests patch "obsws_python.ReqClient" which requires the top-level module
# to be importable.  We register a MagicMock only when the real package is
# absent so that a real installation is always preferred.

if "obsws_python" not in sys.modules:
    _mock_obsws = MagicMock()
    sys.modules["obsws_python"] = _mock_obsws
