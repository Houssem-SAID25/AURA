# AURA – AI Voice Assistant for Gamers & Streamers

AURA is a desktop AI voice assistant built for gamers and streamers. It listens
for voice commands, understands natural language, and automates your streaming
setup — launching OBS, opening Twitch, starting games, and more.

The desktop interface is styled after a sci-fi HUD (think **Jarvis from Iron Man**
or the **Batcave AI**) — dark background, electric-cyan neon accents, animated
pulse rings, and live audio visualisation bars.

---

## Features

| Feature | Description |
|---|---|
| 🎙️ Voice recognition | Offline transcription via OpenAI Whisper (Google STT fallback) |
| 🔊 Text-to-speech | Spoken responses via pyttsx3 (offline, cross-platform) |
| 🧠 NLP command parsing | Fuzzy intent matching with rapidfuzz – no rigid keywords |
| 📺 OBS control | Start/stop stream, switch scenes via OBS WebSocket API v5 |
| 🎮 Game launcher | Launch games by voice; paths configured in `config.json` |
| 🟣 Twitch integration | Fetch trending games, get smart game suggestions |
| 🖥️ HUD desktop GUI | Jarvis-style animated interface (customtkinter + Canvas) |
| 📦 Windows EXE | Single-folder installer built with PyInstaller |
| 🔁 Continuous loop | Runs indefinitely, listening for new commands |
| 📝 Logging | File + console logging with configurable level |

---

## Download (Windows EXE)

> The latest pre-built Windows installer is attached to every
> [GitHub Release](../../releases/latest).

1. Download **AURA-Windows.zip** from the Releases page.
2. Extract the zip to any folder (e.g. `C:\AURA`).
3. Edit **`AURA/config.json`** with your credentials and game paths (see
   [Configure AURA](#2-configure-aura) below).
4. Double-click **`AURA.exe`** — no Python installation required.

---

## Project Structure

```
AURA/
├── gui_main.py               # GUI entry point – opens the HUD desktop app
├── main.py                   # CLI entry point – headless voice loop
├── config.json               # Configuration (paths, credentials, voice settings)
├── requirements.txt          # Python dependencies
├── aura.spec                 # PyInstaller build specification
├── gui/
│   ├── __init__.py
│   └── app.py                # AuraApp GUI (customtkinter + animated Canvas HUD)
├── assets/
│   └── make_icon.py          # Generates aura.ico for the EXE
├── voice/
│   ├── speech_to_text.py     # Whisper-based STT with Google fallback
│   └── text_to_speech.py     # pyttsx3 TTS engine wrapper
├── core/
│   ├── command_parser.py     # NLP intent classifier (fuzzy matching)
│   └── action_handler.py     # Dispatches commands to integrations
├── integrations/
│   ├── obs_controller.py     # OBS WebSocket control
│   ├── twitch_api.py         # Twitch Helix API (trending games, suggestions)
│   └── game_launcher.py      # Subprocess-based launcher for games and OBS
└── tests/
    ├── test_command_parser.py
    ├── test_action_handler.py
    ├── test_game_launcher.py
    ├── test_obs_controller.py
    └── test_twitch_api.py
```

---

## Quick Start (from source)

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

> **Note:** `pyaudio` requires PortAudio.
> - **Windows:** `pip install pipwin && pipwin install pyaudio`
> - **Ubuntu/Debian:** `sudo apt-get install portaudio19-dev`
> - **macOS:** `brew install portaudio`

### 2. Configure AURA

Edit `config.json` to set your paths and credentials:

```json
{
  "obs": {
    "host": "localhost",
    "port": 4455,
    "password": "your_obs_websocket_password",
    "path": "C:\\Program Files\\obs-studio\\bin\\64bit\\obs64.exe"
  },
  "twitch": {
    "client_id": "your_twitch_client_id",
    "client_secret": "your_twitch_client_secret",
    "channel": "your_channel_name"
  },
  "games": {
    "counter-strike 2": "C:\\...\\cs2.exe",
    "valorant": "C:\\...\\VALORANT.exe"
  },
  "voice": {
    "whisper_model": "base",
    "tts_rate": 175
  }
}
```

### 3. Enable OBS WebSocket

In OBS Studio: **Tools → WebSocket Server Settings** → enable the server and
set the password to match `config.json`.

### 4. Launch AURA

**Desktop GUI (recommended):**
```bash
python gui_main.py
```

**Headless CLI mode:**
```bash
python main.py
```

---

## Building the Windows EXE

The EXE is automatically built and attached to every GitHub Release via the
[`build-exe.yml`](.github/workflows/build-exe.yml) workflow. To build locally:

```bash
# 1. Install build tools
pip install pyinstaller pillow

# 2. Generate the app icon
python assets/make_icon.py

# 3. Build (output: dist/AURA/AURA.exe)
pyinstaller aura.spec
```

The resulting `dist/AURA/` folder is self-contained — zip it and share.

---

## Supported Voice Commands

| Voice command | Action |
|---|---|
| "Start stream" / "Go live" | Starts OBS streaming |
| "Stop stream" / "End stream" | Stops OBS streaming |
| "Switch scene to Gameplay" | Changes the active OBS scene |
| "Launch OBS" / "Open OBS Studio" | Launches OBS Studio |
| "Open Twitch" | Opens your Twitch channel in the browser |
| "Launch Counter-Strike 2" | Launches the configured game |
| "I'm going to stream Valorant" | Launches Valorant |
| "What's trending" / "Top games" | Lists top 5 Twitch games |
| "Suggest a game" | Suggests a popular but unsaturated game |
| "Help" | Lists available commands |

---

## Running Tests

```bash
pip install pytest rapidfuzz requests
pytest tests/ -v
```

---

## Architecture

```
Microphone ──► SpeechToText (Whisper)
                    │
                    ▼
             CommandParser (fuzzy NLP)
                    │
                    ▼
             ActionHandler (dispatch)
            /    |     |      \
     OBSCtrl  Twitch  Game   Browser
              API    Launcher
                    │
                    ▼
             TextToSpeech (pyttsx3) ──► Speakers
```

---

## Configuration Reference

| Key | Description |
|---|---|
| `obs.host` | OBS WebSocket host (default: `localhost`) |
| `obs.port` | OBS WebSocket port (default: `4455`) |
| `obs.password` | OBS WebSocket password |
| `obs.path` | Full path to the OBS executable |
| `twitch.client_id` | Twitch app client ID |
| `twitch.client_secret` | Twitch app client secret |
| `twitch.channel` | Your Twitch channel name |
| `games.<name>` | Full path to the game executable |
| `voice.whisper_model` | Whisper model size (`tiny`, `base`, `small`, …) |
| `voice.tts_rate` | TTS speech rate (words per minute) |
| `logging.level` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `logging.file` | Log file path (default: `aura.log`) |