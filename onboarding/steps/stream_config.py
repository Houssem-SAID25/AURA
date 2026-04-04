"""
onboarding/steps/stream_config.py
===================================
Step 7 — Stream Configuration.

Collects preferred streaming platform, output resolution, and default
OBS scene.
"""
from __future__ import annotations
from typing import Any

_PLATFORMS = {"1": "twitch", "2": "youtube"}
_RESOLUTIONS = {"1": "1080p", "2": "720p"}
_SCENES = {"1": "Gaming", "2": "Just Chatting", "3": "Starting Soon"}


def run(data: dict[str, Any]) -> dict[str, Any]:
    """Prompt for stream configuration and return ``{"stream_config": {...}}``."""
    print()
    print("  Stream configuration:")

    print("    Platform: [1] Twitch (default)  [2] YouTube")
    platform = _PLATFORMS.get(input("    Choice [1]: ").strip(), "twitch")

    print("    Resolution: [1] 1080p (default)  [2] 720p")
    resolution = _RESOLUTIONS.get(input("    Choice [1]: ").strip(), "1080p")

    print("    Default scene: [1] Gaming (default)  [2] Just Chatting  [3] Starting Soon")
    scene = _SCENES.get(input("    Choice [1]: ").strip(), "Gaming")

    stream_cfg = {"platform": platform, "resolution": resolution, "default_scene": scene}
    print(f"    Configured: {platform} / {resolution} / scene '{scene}'")
    return {"stream_config": stream_cfg}
