"""
AURA – AI Voice Assistant for Gamers & Streamers
=================================================
Entry point: starts the assistant and runs the continuous listening loop.
"""

import logging
import json
import os
import sys

from voice.speech_to_text import SpeechToText
from voice.text_to_speech import TextToSpeech
from core.command_parser import CommandParser
from core.action_handler import ActionHandler


def load_config(path: str = "config.json") -> dict:
    """Load the JSON configuration file relative to this script's directory."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, path)
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def setup_logging(config: dict) -> None:
    """Configure root logger based on config settings."""
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
    """Main entry point – initialise modules and run the voice command loop."""
    config = load_config()
    setup_logging(config)

    logger = logging.getLogger("AURA")
    logger.info("Starting AURA AI Voice Assistant…")

    # Initialise modules
    stt = SpeechToText(config)
    tts = TextToSpeech(config)
    parser = CommandParser(config)
    handler = ActionHandler(config)

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
