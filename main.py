"""
AURA – AI Voice Assistant for Gamers & Streamers
=================================================
Entry point: starts the assistant and runs the continuous listening loop.
"""

import logging
import sys

from utils.config_loader import load_config, validate_config
from utils.logger import setup_logging
from core.session import create_session


def main() -> None:
    """Main entry point – initialise modules and run the voice command loop."""
    config = load_config()
    config = validate_config(config)
    setup_logging(config)

    logger = logging.getLogger("AURA")
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
