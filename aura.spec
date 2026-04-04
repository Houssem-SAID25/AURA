# -*- mode: python ; coding: utf-8 -*-
"""
aura.spec
=========
PyInstaller build specification for AURA.

Build steps (Windows):
    1. pip install pyinstaller
    2. python assets/make_icon.py        # generates assets/aura.ico
    3. pyinstaller aura.spec

Output:  dist/AURA/AURA.exe   (one-directory bundle)
"""

import os

block_cipher = None

# Detect whether the icon was pre-generated
_icon = "assets/aura.ico" if os.path.isfile("assets/aura.ico") else None

a = Analysis(
    ["gui_main.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("config.json", "."),
        ("assets",      "assets"),
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
        # Integrations
        "obsws_python",
        "rapidfuzz",
        "rapidfuzz.fuzz",
        "requests",
        "dotenv",
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
    console=False,      # No terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
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
