"""
onboarding/steps/obs_setup.py
==============================
Step 6 — OBS Auto Setup.

Probes common OBS WebSocket ports and records the detected port.
"""
from __future__ import annotations
from typing import Any


def run(data: dict[str, Any]) -> dict[str, Any]:
    print()
    print("  Probing for OBS WebSocket…", end="", flush=True)
    from core.onboarding.onboarding_storage import detect_obs_port  # noqa: PLC0415
    port = detect_obs_port()
    if port:
        print(f" found on port {port}!")
    else:
        print(" not detected (OBS may not be running).")
    return {"obs_auto_detected_port": port}
