"""
gui/onboarding_window.py
========================
Step-by-step onboarding wizard for AURA's first-launch experience.

Uses the same customtkinter aesthetic as the main AuraApp (dark Jarvis/
Batcave HUD palette) so the transition is seamless.

Flow
----
  Step 0 – Language selection (FR / EN)
  Step 1 – Username / nickname
  Step 2 – Twitch channel (optional)
  Step 3 – Confirmation summary
  Step 4 – Done / launch

The wizard calls ``on_complete(profile)`` when the user confirms so that
the caller can save the profile and proceed to the main application.
"""

from __future__ import annotations

import logging
import tkinter as tk
from typing import Callable

import customtkinter as ctk

from core.i18n import get_language, set_language, t
from core.onboarding.onboarding_storage import (
    build_profile,
    validate_twitch,
)

logger = logging.getLogger("AURA.Onboarding")

# ──────────────────────────────────────────────────────────────────────────────
# Palette (mirrors gui/app.py)
# ──────────────────────────────────────────────────────────────────────────────
BG_DEEP    = "#060d1a"
BG_PANEL   = "#0a1628"
NEON_CYAN  = "#00d4ff"
NEON_BLUE  = "#0080ff"
NEON_GREEN = "#00ff88"
NEON_AMBER = "#ff9900"
NEON_RED   = "#ff3366"
TEXT_BRIGHT = "#d0eeff"
TEXT_DIM   = "#3a6080"
BORDER     = "#1a3050"

STEP_NAMES = ["step_language", "step_username", "step_twitch", "step_confirm"]
TOTAL_STEPS = len(STEP_NAMES)


class OnboardingWindow(ctk.CTkToplevel):
    """First-launch setup wizard rendered as a modal Toplevel window.

    Parameters
    ----------
    master:
        Parent Tk/CTk widget (can be a hidden root created by the caller).
    on_complete:
        Callback invoked with the completed profile ``dict`` after the user
        saves.  The caller is responsible for saving the profile and
        destroying/hiding this window.
    """

    def __init__(
        self,
        master: tk.Misc,
        on_complete: Callable[[dict], None],
    ) -> None:
        super().__init__(master)
        self._on_complete = on_complete
        self._step = 0

        # Wizard data collected across steps
        self._lang = "fr"          # default to French per spec
        self._username_var = ctk.StringVar()
        self._twitch_var   = ctk.StringVar()
        self._other_var    = ctk.StringVar()

        # Apply language chosen at start
        set_language(self._lang)

        self.title("AURA – Setup")
        self.geometry("560x520")
        self.resizable(False, False)
        self.configure(fg_color=BG_DEEP)

        # Make this window modal
        self.grab_set()
        self.focus_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_header()
        self._build_step_indicator()
        self._content_frame = ctk.CTkFrame(self, fg_color=BG_DEEP)
        self._content_frame.pack(fill="both", expand=True, padx=30, pady=(0, 10))
        self._build_footer()

        self._render_step()

    # ── Layout skeleton ───────────────────────────────────────────────────

    def _build_header(self) -> None:
        hdr = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0, height=72)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        ctk.CTkLabel(
            hdr,
            text="◈  AURA",
            font=("Consolas", 22, "bold"),
            text_color=NEON_CYAN,
        ).pack(side="left", padx=24, pady=16)

        self._step_label = ctk.CTkLabel(
            hdr,
            text="",
            font=("Consolas", 11),
            text_color=TEXT_DIM,
        )
        self._step_label.pack(side="right", padx=24)

    def _build_step_indicator(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=BG_PANEL, height=6, corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        self._progress_bar = ctk.CTkProgressBar(
            bar,
            height=6,
            corner_radius=0,
            fg_color=BG_DEEP,
            progress_color=NEON_CYAN,
        )
        self._progress_bar.pack(fill="x")
        self._progress_bar.set(0)

    def _build_footer(self) -> None:
        self._footer = ctk.CTkFrame(self, fg_color=BG_PANEL, height=64, corner_radius=0)
        self._footer.pack(fill="x", side="bottom")
        self._footer.pack_propagate(False)

        self._btn_back = ctk.CTkButton(
            self._footer,
            text=t("onboarding.btn_back"),
            width=110,
            fg_color=BG_DEEP,
            hover_color=BORDER,
            border_color=BORDER,
            border_width=1,
            text_color=TEXT_DIM,
            command=self._go_back,
        )
        self._btn_back.pack(side="left", padx=16, pady=14)

        self._btn_next = ctk.CTkButton(
            self._footer,
            text=t("onboarding.btn_next"),
            width=200,
            fg_color=NEON_BLUE,
            hover_color=NEON_CYAN,
            text_color=BG_DEEP,
            font=("Consolas", 13, "bold"),
            command=self._go_next,
        )
        self._btn_next.pack(side="right", padx=16, pady=14)

    # ── Step rendering ────────────────────────────────────────────────────

    def _render_step(self) -> None:
        # Clear content frame
        for widget in self._content_frame.winfo_children():
            widget.destroy()

        # Update progress
        progress = self._step / TOTAL_STEPS
        self._progress_bar.set(progress)

        step_key = STEP_NAMES[min(self._step, TOTAL_STEPS - 1)]
        self._step_label.configure(
            text=f"{t(f'onboarding.{step_key}')}  ({self._step + 1}/{TOTAL_STEPS})"
        )

        # Back button visibility
        if self._step == 0:
            self._btn_back.configure(state="disabled", text_color=TEXT_DIM)
        else:
            self._btn_back.configure(state="normal", text_color=TEXT_BRIGHT)

        # Next / confirm button text
        if self._step == TOTAL_STEPS - 1:
            self._btn_next.configure(text=t("onboarding.btn_confirm"))
        else:
            self._btn_next.configure(text=t("onboarding.btn_next"))

        renderers = [
            self._render_language_step,
            self._render_username_step,
            self._render_twitch_step,
            self._render_confirm_step,
        ]
        if self._step < len(renderers):
            renderers[self._step]()

    def _render_language_step(self) -> None:
        frame = self._content_frame

        ctk.CTkLabel(
            frame,
            text=t("onboarding.welcome"),
            font=("Consolas", 24, "bold"),
            text_color=NEON_CYAN,
        ).pack(pady=(28, 4))

        ctk.CTkLabel(
            frame,
            text=t("onboarding.welcome_subtitle"),
            font=("Consolas", 12),
            text_color=TEXT_DIM,
        ).pack(pady=(0, 28))

        ctk.CTkLabel(
            frame,
            text=t("onboarding.choose_language"),
            font=("Consolas", 14),
            text_color=TEXT_BRIGHT,
        ).pack(pady=(0, 16))

        btn_fr = ctk.CTkButton(
            frame,
            text=f"{t('onboarding.fr_flag')}  {t('onboarding.language_fr')}",
            width=200,
            height=48,
            font=("Consolas", 14, "bold"),
            fg_color=NEON_BLUE if self._lang == "fr" else BG_PANEL,
            hover_color=NEON_CYAN,
            text_color=BG_DEEP if self._lang == "fr" else TEXT_BRIGHT,
            border_color=NEON_CYAN if self._lang == "fr" else BORDER,
            border_width=2,
            command=lambda: self._select_language("fr"),
        )
        btn_fr.pack(pady=6)

        btn_en = ctk.CTkButton(
            frame,
            text=f"{t('onboarding.en_flag')}  {t('onboarding.language_en')}",
            width=200,
            height=48,
            font=("Consolas", 14, "bold"),
            fg_color=NEON_BLUE if self._lang == "en" else BG_PANEL,
            hover_color=NEON_CYAN,
            text_color=BG_DEEP if self._lang == "en" else TEXT_BRIGHT,
            border_color=NEON_CYAN if self._lang == "en" else BORDER,
            border_width=2,
            command=lambda: self._select_language("en"),
        )
        btn_en.pack(pady=6)

        self._lang_buttons = {"fr": btn_fr, "en": btn_en}

    def _select_language(self, lang: str) -> None:
        self._lang = lang
        set_language(lang)
        # Re-render so button highlight and all labels update
        self._render_step()

    def _render_username_step(self) -> None:
        frame = self._content_frame

        ctk.CTkLabel(
            frame,
            text=t("onboarding.username_title"),
            font=("Consolas", 18, "bold"),
            text_color=NEON_CYAN,
        ).pack(pady=(32, 8))

        ctk.CTkLabel(
            frame,
            text=t("onboarding.username_label"),
            font=("Consolas", 12),
            text_color=TEXT_DIM,
        ).pack(pady=(0, 8))

        entry = ctk.CTkEntry(
            frame,
            textvariable=self._username_var,
            placeholder_text=t("onboarding.username_placeholder"),
            width=320,
            height=44,
            font=("Consolas", 14),
            fg_color=BG_PANEL,
            border_color=NEON_BLUE,
            text_color=TEXT_BRIGHT,
        )
        entry.pack(pady=8)
        entry.focus_set()

        self._username_error = ctk.CTkLabel(
            frame,
            text="",
            font=("Consolas", 11),
            text_color=NEON_RED,
        )
        self._username_error.pack(pady=(4, 0))

    def _render_twitch_step(self) -> None:
        frame = self._content_frame

        ctk.CTkLabel(
            frame,
            text=t("onboarding.twitch_title"),
            font=("Consolas", 18, "bold"),
            text_color=NEON_CYAN,
        ).pack(pady=(32, 8))

        ctk.CTkLabel(
            frame,
            text=t("onboarding.twitch_label"),
            font=("Consolas", 12),
            text_color=TEXT_DIM,
        ).pack(pady=(0, 8))

        twitch_entry = ctk.CTkEntry(
            frame,
            textvariable=self._twitch_var,
            placeholder_text=t("onboarding.twitch_placeholder"),
            width=360,
            height=44,
            font=("Consolas", 13),
            fg_color=BG_PANEL,
            border_color=NEON_BLUE,
            text_color=TEXT_BRIGHT,
        )
        twitch_entry.pack(pady=8)

        self._twitch_error = ctk.CTkLabel(
            frame,
            text="",
            font=("Consolas", 11),
            text_color=NEON_RED,
        )
        self._twitch_error.pack(pady=(4, 0))

        ctk.CTkLabel(
            frame,
            text=t("onboarding.other_links_label"),
            font=("Consolas", 12),
            text_color=TEXT_DIM,
        ).pack(pady=(16, 4))

        ctk.CTkEntry(
            frame,
            textvariable=self._other_var,
            placeholder_text=t("onboarding.other_links_placeholder"),
            width=360,
            height=44,
            font=("Consolas", 13),
            fg_color=BG_PANEL,
            border_color=BORDER,
            text_color=TEXT_BRIGHT,
        ).pack(pady=4)

    def _render_confirm_step(self) -> None:
        frame = self._content_frame

        ctk.CTkLabel(
            frame,
            text=t("onboarding.confirm_title"),
            font=("Consolas", 18, "bold"),
            text_color=NEON_CYAN,
        ).pack(pady=(28, 16))

        none_str = t("onboarding.confirm_none")
        lang_display = "Français" if self._lang == "fr" else "English"
        rows = [
            (t("onboarding.confirm_language"), lang_display),
            (t("onboarding.confirm_username"),  self._username_var.get() or none_str),
            (t("onboarding.confirm_twitch"),    self._twitch_var.get() or none_str),
            (t("onboarding.confirm_other"),     self._other_var.get() or none_str),
        ]

        card = ctk.CTkFrame(frame, fg_color=BG_PANEL, corner_radius=10)
        card.pack(fill="x", padx=8, pady=4)

        for label, value in rows:
            row = ctk.CTkFrame(card, fg_color=BG_PANEL)
            row.pack(fill="x", padx=16, pady=6)
            ctk.CTkLabel(
                row,
                text=f"{label}:",
                font=("Consolas", 12),
                text_color=TEXT_DIM,
                width=120,
                anchor="w",
            ).pack(side="left")
            ctk.CTkLabel(
                row,
                text=value,
                font=("Consolas", 12, "bold"),
                text_color=TEXT_BRIGHT,
                anchor="w",
            ).pack(side="left", padx=(8, 0))

        self._save_error = ctk.CTkLabel(
            frame,
            text="",
            font=("Consolas", 11),
            text_color=NEON_RED,
        )
        self._save_error.pack(pady=(12, 0))

    # ── Navigation ────────────────────────────────────────────────────────

    def _go_next(self) -> None:
        if not self._validate_current_step():
            return

        if self._step == TOTAL_STEPS - 1:
            self._finish()
        else:
            self._step += 1
            # Refresh all text after language change on step 0
            if self._step == 1:
                self._refresh_footer_buttons()
            self._render_step()

    def _go_back(self) -> None:
        if self._step > 0:
            self._step -= 1
            self._render_step()

    def _refresh_footer_buttons(self) -> None:
        """Update footer button labels after a language change."""
        self._btn_back.configure(text=t("onboarding.btn_back"))
        self._btn_next.configure(text=t("onboarding.btn_next"))

    def _validate_current_step(self) -> bool:
        if self._step == 1:
            # Username required
            if not self._username_var.get().strip():
                self._username_error.configure(text=t("onboarding.username_required"))
                return False
            self._username_error.configure(text="")

        elif self._step == 2:
            # Twitch URL optional but must be valid if provided
            twitch_val = self._twitch_var.get().strip()
            if twitch_val and not validate_twitch(twitch_val):
                self._twitch_error.configure(text=t("onboarding.twitch_invalid"))
                return False
            self._twitch_error.configure(text="")

        return True

    def _finish(self) -> None:
        """Build the profile dict and hand off to the caller."""
        profile = build_profile(
            language=self._lang,
            username=self._username_var.get(),
            twitch=self._twitch_var.get(),
            other_links=self._other_var.get(),
        )
        self._on_complete(profile)

    def _on_close(self) -> None:
        """Allow users to exit the wizard and quit the application."""
        import tkinter.messagebox as mb  # noqa: PLC0415
        if mb.askyesno(
            "AURA – Exit",
            "Are you sure you want to exit without completing setup?",
            parent=self,
        ):
            logger.info("Onboarding cancelled by user — exiting.")
            # Destroy the wizard and its master so mainloop() ends cleanly
            self.destroy()
            try:
                self.master.destroy()
            except Exception:  # pylint: disable=broad-except
                pass


class OnboardingRoot(ctk.CTk):
    """Standalone Tk root used when there is no existing master widget.

    Starts the onboarding wizard and destroys itself once setup is done,
    allowing the caller to launch the main application afterward.
    """

    def __init__(self, on_complete: Callable[[dict], None]) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        super().__init__()
        self.withdraw()   # hide root – only the wizard window is visible

        self._on_complete = on_complete
        self._wizard = OnboardingWindow(self, self._handle_complete)

    def _handle_complete(self, profile: dict) -> None:
        self._on_complete(profile)
        self._wizard.destroy()
        self.destroy()
