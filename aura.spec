# -*- mode: python ; coding: utf-8 -*-
"""
aura.spec
=========
PyInstaller build specification for AURA.

Build steps (Windows):
    1. pip install pyinstaller pillow
    2. python assets/make_icon.py        # generates assets/aura.ico
    3. pyinstaller aura.spec

Output:  dist/AURA/AURA.exe   (one-directory bundle)

SmartScreen / "Unknown publisher" note
---------------------------------------
Windows Defender SmartScreen may show a warning when end-users run AURA.exe
because the executable is not code-signed.  This is expected for open-source
builds distributed without a purchased code-signing certificate.

To suppress the SmartScreen warning completely:
  1. Obtain an EV (Extended Validation) code-signing certificate from a
     trusted Certificate Authority (DigiCert, Sectigo, etc.).  EV certs
     establish publisher reputation immediately.
  2. Sign the EXE with `signtool.exe` (included in the Windows SDK):
         signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256
                       /a dist/AURA/AURA.exe
  3. If using a standard OV certificate, reputation builds over time as more
     users run the signed executable.

Open-source contributors: the build will still produce a working EXE; users
may need to click "More info → Run anyway" on first launch.
"""

import os
import sys

# SPECPATH is injected by PyInstaller into the spec's execution namespace;
# it points to the directory containing this spec file (the project root).
# We add it to sys.path so that `version.py` (and other local modules) can
# be imported even when PyInstaller exec()s the spec from a different cwd.
sys.path.insert(0, SPECPATH)  # noqa: F821 – SPECPATH is set by PyInstaller

from version import __version__  # noqa: E402

block_cipher = None

# Detect whether the icon was pre-generated
_icon = "assets/aura.ico" if os.path.isfile("assets/aura.ico") else None

a = Analysis(
    ["gui_main.py"],
    pathex=["."],
    binaries=[],
    datas=[
        # Core runtime data
        ("config.json",          "."),
        ("config/commands.json", "config"),
        # Assets (icon, images)
        ("assets",               "assets"),
        # Include an empty user_profile.json placeholder so the first-run
        # onboarding wizard can detect its absence inside the bundle.
        # The real profile is written to the user's AppData directory at
        # runtime; this placeholder is never read.
    ],
    hiddenimports=[
        # GUI
        "customtkinter",
        # TTS
        "pyttsx3",
        "pyttsx3.drivers",
        "pyttsx3.drivers.sapi5",
        "pyttsx3.drivers.nsss",
        "pyttsx3.drivers.espeak",
        # STT
        "speech_recognition",
        "whisper",
        "whisper.audio",
        "whisper.decoding",
        "whisper.model",
        "whisper.tokenizer",
        "whisper.utils",
        # Audio
        "pyaudio",
        "sounddevice",
        "soundfile",
        # Integrations
        "obsws_python",
        "rapidfuzz",
        "rapidfuzz.fuzz",
        "requests",
        "dotenv",
        # New AI reasoning modules
        "core.intent_engine",
        "core.context_engine",
        "core.task_planner",
        "core.decision_engine",
        # Wake word
        "voice.wake_word",
        # Streaming shim
        "streaming.obs_controller",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AURA",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,      # No terminal window (GUI mode)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
    # Windows executable metadata
    # (requires PyInstaller >=6.0 or a .version_file — see build/ folder)
    version="build/version_info.txt" if os.path.isfile("build/version_info.txt") else None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AURA",
)
