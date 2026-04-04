"""
AURA – AI Voice Assistant for Gamers & Streamers
=================================================
Entry point: starts the assistant and runs the continuous listening loop.

First-launch flow
-----------------
If ``config/user_profile.json`` does not exist a CLI onboarding wizard is
shown in the terminal before the voice loop starts.
"""

import logging
import sys

from utils.config_loader import load_config, validate_config
from utils.logger import setup_logging
from core.session import create_session


def _run_cli_onboarding() -> bool:
    """Run a terminal-based onboarding wizard.

    Returns ``True`` if the wizard completed successfully, ``False`` if the
    user aborted or a save error occurred.
    """
    from core.i18n import set_language, t  # noqa: PLC0415
    from core.onboarding.onboarding_storage import (  # noqa: PLC0415
        build_profile,
        save_profile,
        validate_twitch,
    )

    print("\n" + "=" * 60)
    print("  AURA – First Launch Setup")
    print("=" * 60)

    # Step 1 – Language
    print("\nChoose language / Choisissez votre langue:")
    print("  [1] Français (défaut)")
    print("  [2] English")
    lang_choice = input("Choice / Choix [1]: ").strip()
    lang = "en" if lang_choice == "2" else "fr"
    set_language(lang)
    print(f"\nLanguage set to: {'Français' if lang == 'fr' else 'English'}")

    # Step 2 – Username
    print()
    while True:
        username = input(t("onboarding.username_label") + ": ").strip()
        if username:
            break
        print(f"  ! {t('onboarding.username_required')}")

    # Step 3 – Twitch
    print()
    while True:
        twitch = input(
            f"{t('onboarding.twitch_label')} [{t('onboarding.confirm_none')}]: "
        ).strip()
        if not twitch or validate_twitch(twitch):
            break
        print(f"  ! {t('onboarding.twitch_invalid')}")

    # Other links
    other = input(
        f"{t('onboarding.other_links_label')} [{t('onboarding.confirm_none')}]: "
    ).strip()

    # Step 4 – Confirm
    none_str = t("onboarding.confirm_none")
    print("\n" + "-" * 60)
    print(f"  {t('onboarding.confirm_language')}: {'Français' if lang == 'fr' else 'English'}")
    print(f"  {t('onboarding.confirm_username')}: {username}")
    print(f"  {t('onboarding.confirm_twitch')}:   {twitch or none_str}")
    print(f"  {t('onboarding.confirm_other')}:    {other or none_str}")
    print("-" * 60)

    confirm = input("\nConfirm? (y/n) [y]: ").strip().lower()
    if confirm == "n":
        print("Setup cancelled.")
        return False

    profile = build_profile(
        language=lang,
        username=username,
        twitch=twitch,
        other_links=other,
    )

    if not save_profile(profile):
        print(f"\n! {t('onboarding.save_error')}")
        return False

    print(f"\n{t('onboarding.done_message', username=username)}\n")
    return True


def main() -> None:
    """Main entry point – initialise modules and run the voice command loop."""
    config = load_config()
    config = validate_config(config)
    setup_logging(config)

    logger = logging.getLogger("AURA")

    from core.onboarding.onboarding_storage import profile_exists, load_profile  # noqa: PLC0415
    from core.i18n import set_language  # noqa: PLC0415

    if not profile_exists():
        logger.info("No user profile found — starting CLI onboarding wizard.")
        if not _run_cli_onboarding():
            logger.warning("Onboarding cancelled. Exiting.")
            sys.exit(0)
    else:
        profile = load_profile()
        set_language(profile.get("language", "en"))

    logger.info("Starting AURA AI Voice Assistant…")

    session = create_session(config)
    stt = session.stt
    tts = session.tts
    parser = session.parser
    handler = session.handler

    tts.speak("AURA is online. Ready to help you stream!")
    logger.info("AURA is ready. Listening for commands.")

    # Continuous listening loop
    while True:
        try:
            logger.info("Listening…")
            text = stt.listen()

            if not text:
                continue

            logger.info("Heard: %s", text)

            # Parse the spoken text into a structured command
            command = parser.parse(text)
            logger.info("Parsed command: %s", command)

            if command is None:
                tts.speak("Sorry, I didn't understand that command.")
                continue

            # Execute the command and get a response message
            response = handler.execute(command, raw_text=text)
            tts.speak(response)

        except KeyboardInterrupt:
            logger.info("Shutdown requested by user.")
            tts.speak("Goodbye! AURA shutting down.")
            break
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Unexpected error in main loop: %s", exc, exc_info=True)
            tts.speak("An unexpected error occurred. Please check the logs.")


if __name__ == "__main__":
    main()
