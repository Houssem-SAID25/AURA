"""
onboarding/steps/user_profile.py
==================================
Step 2 — User Profile.

Collects the user's nickname (required) and optional streamer name.
"""
from __future__ import annotations
from typing import Any


def run(data: dict[str, Any]) -> dict[str, Any]:
    """Collect nickname and optional streamer name."""
    from core.i18n import t  # noqa: PLC0415

    print()
    while True:
        username = input(t("onboarding.username_label") + ": ").strip()
        if username:
            break
        print(f"  ! {t('onboarding.username_required')}")

    print()
    streamer_name = input(
        "Streamer name (shown on-stream, blank to use nickname): "
    ).strip()
    if not streamer_name:
        streamer_name = username

    return {"username": username, "streamer_name": streamer_name}
