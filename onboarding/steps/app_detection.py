"""
onboarding/steps/app_detection.py
===================================
Step 3 — App Auto Detection.

Scans the host system for common gaming and streaming applications and
returns a structured dict.

Detected apps
-------------
* OBS Studio, Discord, Steam, Spotify
* Games: Valorant, Fortnite, Minecraft, Counter-Strike 2, Apex Legends,
  League of Legends, Rocket League, GTA V, Overwatch 2, Dota 2, PUBG,
  Rainbow Six Siege.
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
from typing import Any

logger = logging.getLogger(__name__)

_WIN_ROOTS: list[str] = [
    os.environ.get("PROGRAMFILES", r"C:\Program Files"),
    os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
    os.environ.get("LOCALAPPDATA", ""),
]

# (key, win_exe_paths, unix_binary_names)
_APPS: list[tuple[str, list[str], list[str]]] = [
    ("obs", ["obs-studio\\bin\\64bit\\obs64.exe", "obs64.exe"], ["obs", "obs-studio"]),
    ("discord", ["Discord\\Discord.exe", "Discord.exe"], ["discord"]),
    ("steam", ["Steam\\steam.exe", "steam.exe"], ["steam"]),
    ("spotify", ["Spotify\\Spotify.exe", "Spotify.exe"], ["spotify"]),
]

_GAMES: list[tuple[str, list[str], list[str]]] = [
    ("valorant", [r"Riot Games\VALORANT\live\VALORANT.exe"], ["valorant"]),
    ("fortnite", [r"Epic Games\Fortnite\FortniteGame\Binaries\Win64\FortniteClient-Win64-Shipping.exe"], ["fortnite"]),
    ("minecraft", [r"Minecraft\minecraft.exe"], ["minecraft"]),
    ("counter-strike 2", [r"Steam\steamapps\common\Counter-Strike Global Offensive\cs2.exe"], ["cs2"]),
    ("apex legends", [r"Steam\steamapps\common\Apex Legends\r5apex.exe"], ["apex"]),
    ("league of legends", [r"Riot Games\League of Legends\LeagueClient.exe"], ["leagueclient"]),
    ("rocket league", [r"Steam\steamapps\common\rocketleague\Binaries\Win64\RocketLeague.exe"], ["rocketleague"]),
    ("gta v", [r"Rockstar Games\Grand Theft Auto V\GTA5.exe"], ["gta5"]),
    ("overwatch 2", [r"Battle.net\Games\Overwatch\Overwatch.exe"], ["overwatch"]),
    ("dota 2", [r"Steam\steamapps\common\dota 2 beta\game\bin\win64\dota2.exe"], ["dota2"]),
    ("pubg", [r"Steam\steamapps\common\PUBG\TslGame\Binaries\Win64\TslGame.exe"], ["tslgame"]),
    ("rainbow six siege", [r"Ubisoft Game Launcher\games\Tom Clancy's Rainbow Six Siege\RainbowSix.exe"], ["rainbowsix"]),
]


def detect_installed_apps() -> dict[str, Any]:
    """Scan the host system and return a structured detection result.

    Returns
    -------
    dict
        Keys: ``obs_installed``, ``discord_installed``, ``steam_installed``,
        ``spotify_installed`` (all bool), ``games`` (list[str]).
    """
    result: dict[str, Any] = {
        "obs_installed": False,
        "discord_installed": False,
        "steam_installed": False,
        "spotify_installed": False,
        "games": [],
    }
    for key, win_exes, unix_bins in _APPS:
        result[f"{key}_installed"] = _find(win_exes, unix_bins)

    result["games"] = [
        name for name, win_paths, unix_bins in _GAMES
        if _find(win_paths, unix_bins)
    ]
    return result


def run(data: dict[str, Any]) -> dict[str, Any]:
    """Detect installed apps and print a summary."""
    print()
    print("  Scanning for installed applications…", end="", flush=True)
    apps = detect_installed_apps()
    print(" done.")
    for label, key in [("OBS Studio", "obs"), ("Discord", "discord"),
                       ("Steam", "steam"), ("Spotify", "spotify")]:
        mark = "✔" if apps.get(f"{key}_installed") else "✘"
        print(f"    {mark}  {label}")
    games = apps.get("games", [])
    if games:
        print(f"    ✔  Games: {', '.join(games)}")
    else:
        print("    ✘  No known games detected in default locations.")
    return {"detected_apps": apps}


def _find(win_paths: list[str], unix_bins: list[str]) -> bool:
    if sys.platform == "win32":
        for root in _WIN_ROOTS:
            if not root:
                continue
            for rel in win_paths:
                if os.path.isfile(os.path.join(root, rel)):
                    return True
        return False
    return any(shutil.which(b) for b in unix_bins)
