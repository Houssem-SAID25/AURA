"""
gui_main.py
===========
GUI entry point for AURA.

Launch this file (or the compiled AURA.exe) to open the desktop interface.
The command-line voice loop is still available via ``main.py``.
"""


def main() -> None:
    """Load config, set up logging, and launch the GUI."""
    from utils.config_loader import load_config, validate_config  # noqa: PLC0415
    from utils.logger import setup_logging  # noqa: PLC0415

    config = load_config()
    config = validate_config(config)
    setup_logging(config)

    from gui.app import AuraApp  # noqa: PLC0415

    app = AuraApp(config)
    app.mainloop()


if __name__ == "__main__":
    main()
