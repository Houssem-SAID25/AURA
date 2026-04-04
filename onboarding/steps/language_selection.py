"""
onboarding/steps/language_selection.py
=======================================
Step 1 — Language Selection.

Prompts the user to choose French or English and activates the matching
i18n locale.
"""
from __future__ import annotations
from typing import Any


def run(data: dict[str, Any]) -> dict[str, Any]:
    """Ask the user to pick a language; return ``{"language": "fr"|"en"}``."""
    print("\nChoose language / Choisissez votre langue:")
    print("  [1] Français (défaut)")
    print("  [2] English")
    choice = input("Choice / Choix [1]: ").strip()
    lang = "en" if choice == "2" else "fr"

    from core.i18n import set_language  # noqa: PLC0415
    set_language(lang)
    print(f"\nLanguage set to: {'Français' if lang == 'fr' else 'English'}")
    return {"language": lang}
