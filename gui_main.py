"""
gui_main.py
===========
GUI entry point for AURA.

Launch this file (or the compiled AURA.exe) to open the desktop interface.
The command-line voice loop is still available via ``main.py``.

First-launch flow
-----------------
If ``config/user_profile.json`` does not exist the onboarding wizard is
shown before the main application window opens.  Once the wizard completes
the profile is saved and the main window launches automatically.
"""


def main() -> None:
    """Load config, run onboarding if needed, then launch the GUI."""
    from utils.config_loader import load_config, validate_config  # noqa: PLC0415
    from utils.logger import setup_logging  # noqa: PLC0415

    config = load_config()
    config = validate_config(config)
    setup_logging(config)

    from core.onboarding.onboarding_storage import profile_exists, save_profile  # noqa: PLC0415
    from core.i18n import set_language  # noqa: PLC0415

    if not profile_exists():
        # ── First launch: show onboarding wizard ──────────────────────────
        from gui.onboarding_window import OnboardingRoot  # noqa: PLC0415

        completed_profile: dict = {}

        def on_complete(profile: dict) -> None:
            nonlocal completed_profile
            completed_profile = profile

        wizard = OnboardingRoot(on_complete)
        wizard.mainloop()

        if not completed_profile:
            # User closed the wizard without finishing; exit gracefully
            return

        if not save_profile(completed_profile):
            import tkinter.messagebox as mb  # noqa: PLC0415
            mb.showerror(
                "AURA",
                "Could not save your profile. Please check disk permissions.",
            )
            return

        # Apply the chosen language for the upcoming main window session
        set_language(completed_profile.get("language", "en"))

    else:
        # Restore persisted language preference
        from core.onboarding.onboarding_storage import load_profile  # noqa: PLC0415
        profile = load_profile()
        set_language(profile.get("language", "en"))

    # ── Normal launch ─────────────────────────────────────────────────────
    from gui.app import AuraApp  # noqa: PLC0415

    app = AuraApp(config)
    app.mainloop()


if __name__ == "__main__":
    main()
