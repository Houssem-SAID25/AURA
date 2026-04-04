"""
gui_main.py
===========
GUI entry point for AURA.

Launch this file (or the compiled AURA.exe) to open the desktop interface.
The command-line voice loop is still available via ``main.py``.
"""

import json
import logging
import os
import sys


def load_config(path: str = "config.json") -> dict:
    """Load config.json relative to this script's directory."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, path)
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def setup_logging(config: dict) -> None:
    """Configure root logger from config settings."""
    log_cfg = config.get("logging", {})
    level = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)
    log_file = log_cfg.get("file", "aura.log")
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


def main() -> None:
    """Load config, set up logging, and launch the GUI."""
    config = load_config()
    setup_logging(config)

    from gui.app import AuraApp  # noqa: PLC0415

    app = AuraApp(config)
    app.mainloop()


if __name__ == "__main__":
    main()
