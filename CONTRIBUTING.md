# Contributing to AURA

Thank you for your interest in contributing to **AURA – AI Voice Assistant for Gamers & Streamers**!
This document explains how to get the project running locally, how to add features or fix bugs, and what to keep in mind before opening a pull request.

---

## Table of Contents

1. [Getting started](#1-getting-started)
2. [Project structure](#2-project-structure)
3. [Running tests](#3-running-tests)
4. [Adding a voice command](#4-adding-a-voice-command)
5. [Adding a new integration](#5-adding-a-new-integration)
6. [Code style](#6-code-style)
7. [Pull request checklist](#7-pull-request-checklist)

---

## 1. Getting started

```bash
# Clone the repository
git clone https://github.com/Houssem-SAID25/AURA.git
cd AURA

# (Optional) create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install runtime dependencies
pip install -r requirements.txt

# Install test dependencies
pip install pytest pytest-mock rapidfuzz requests
```

> **pyaudio** requires PortAudio.
> - **Windows:** `pip install pipwin && pipwin install pyaudio`
> - **Ubuntu/Debian:** `sudo apt-get install portaudio19-dev && pip install pyaudio`
> - **macOS:** `brew install portaudio && pip install pyaudio`

Configure `config.json` with your OBS/Twitch credentials and game paths (see
[README – Configure AURA](README.md#2-configure-aura)).

---

## 2. Project structure

```
AURA/
├── main.py            # CLI entry point
├── gui_main.py        # GUI entry point
├── config.json        # User configuration (not tracked for secrets)
├── core/              # Intent parsing and command execution (no I/O)
├── voice/             # STT (Whisper) and TTS (pyttsx3) adapters
├── integrations/      # OBS, Twitch, and game-launcher clients
├── gui/               # Desktop HUD (CustomTkinter)
├── utils/             # Config loader, logger, error handler
├── config/
│   └── commands.json  # Dynamic registry of compound voice commands
├── assets/
│   └── make_icon.py   # Generates assets/aura.ico for EXE builds
└── tests/             # pytest test suite
```

**Key principle:** keep each layer independent.

| Layer | Allowed to import |
|---|---|
| `core/` | `utils/` |
| `voice/` | `utils/` |
| `integrations/` | `utils/` |
| `gui/` | `core/`, `voice/`, `integrations/`, `utils/` |
| Entry points (`main.py`, `gui_main.py`) | everything |

`core/` must **not** import from `voice/`, `integrations/`, or `gui/`.

---

## 3. Running tests

```bash
pytest tests/ -v
```

All tests should pass (no network access required — external APIs are mocked).

When adding a feature, add or update tests in the corresponding file:

| Module | Test file |
|---|---|
| `core/command_parser.py` | `tests/test_command_parser.py` |
| `core/command_registry.py` | `tests/test_command_registry.py` |
| `core/intent_detector.py` | `tests/test_intent_detector.py` |
| `core/action_handler.py` | `tests/test_action_handler.py` |
| `integrations/game_launcher.py` | `tests/test_game_launcher.py` |
| `integrations/obs_controller.py` | `tests/test_obs_controller.py` |
| `integrations/twitch_api.py` | `tests/test_twitch_api.py` |
| `utils/config_loader.py` | `tests/test_config_loader.py` |
| Full pipeline | `tests/test_voice_pipeline.py` |

---

## 4. Adding a voice command

### Simple single-action command

Single-action commands are matched by `IntentDetector` using fuzzy matching.
To add a new intent:

1. Add it to the `_INTENT_EXAMPLES` dict in `core/intent_detector.py`.
2. Add a handler method to `ActionHandler` in `core/action_handler.py`.
3. Register the handler in the `_handlers` dispatch table.
4. Add tests to `tests/test_intent_detector.py` and `tests/test_action_handler.py`.

### Compound (multi-action) command

Compound commands run several actions in sequence and require **no Python changes**:

1. Open `config/commands.json`.
2. Add an entry following the existing pattern:

```json
{
  "stream_apex": {
    "description": "Full streaming setup for Apex Legends",
    "keywords": ["stream apex", "go live apex legends"],
    "intent": "stream",
    "game": "apex legends",
    "actions": ["launch_obs", "launch_game", "open_twitch"]
  }
}
```

3. Add the game path in `config.json` under `"games"`.

No Python changes required.

---

## 5. Adding a new integration

1. Create a new file in `integrations/`, e.g. `integrations/discord_rpc.py`.
2. Follow the existing pattern:
   - Accept `config: dict` in `__init__`.
   - Return `(success: bool, message: str)` tuples from all public methods.
   - Handle all exceptions internally; never let them propagate to callers.
3. Add a corresponding handler in `core/action_handler.py`.
4. Add tests in `tests/test_<module>.py`, mocking the external service.

---

## 6. Code style

- **Formatting:** [Black](https://black.readthedocs.io/) (line length 88).
- **Imports:** sorted with [isort](https://pycqa.github.io/isort/) (Black-compatible profile).
- **Linting:** [Ruff](https://docs.astral.sh/ruff/) or [Flake8](https://flake8.pycqa.org/).
- **Type hints:** use `from __future__ import annotations` at the top of every file.
- **Docstrings:** NumPy-style docstrings for all public classes and functions.
- **Logging:** use `logging.getLogger(__name__)` — never `print()` in library code.
- **No bare `except`:** always catch a specific exception or use `except Exception`.

Quick formatting:

```bash
pip install black isort
black .
isort .
```

---

## 7. Pull request checklist

Before opening a PR, please confirm:

- [ ] All existing tests pass (`pytest tests/ -v`).
- [ ] New functionality has corresponding tests.
- [ ] Code is formatted with Black and imports sorted with isort.
- [ ] No secrets, credentials, or absolute local paths are committed.
- [ ] `config.json` changes are reflected in the Configuration Reference in `README.md`.
- [ ] The PR description explains *what* the change does and *why*.
