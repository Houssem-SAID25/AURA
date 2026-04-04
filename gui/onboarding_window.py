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
  Step 2 – Account linking (Twitch, YouTube, OBS, Discord)
  Step 3 – Confirmation summary

The wizard calls ``on_complete(profile)`` when the user confirms so that
the caller can save the profile and proceed to the main application.
"""

from __future__ import annotations

import logging
import re
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

STEP_NAMES = ["step_language", "step_username", "step_accounts", "step_confirm"]
TOTAL_STEPS = len(STEP_NAMES)

_YOUTUBE_PATTERN = re.compile(
    r"^https?://(www\.)?(youtube\.com|youtu\.be)/", re.IGNORECASE
)

# Characters used to mask sensitive tokens in the confirmation summary
_TOKEN_MASK_CHAR = "●"
_TOKEN_MASK_LENGTH = 8


def _validate_youtube(value: str) -> bool:
    """Return True if value is a valid YouTube URL or empty."""
    value = value.strip()
    if not value:
        return True
    return bool(_YOUTUBE_PATTERN.match(value))


def _validate_obs_port(value: str) -> bool:
    """Return True if value is a valid port number (1-65535) or empty."""
    value = value.strip()
    if not value:
        return True
    try:
        port = int(value)
        return 1 <= port <= 65535
    except ValueError:
        return False


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
        self._username_var      = ctk.StringVar()
        self._twitch_var        = ctk.StringVar()
        self._youtube_var       = ctk.StringVar()
        self._obs_host_var      = ctk.StringVar(value="localhost")
        self._obs_port_var      = ctk.StringVar(value="4455")
        self._obs_password_var  = ctk.StringVar()
        self._discord_token_var = ctk.StringVar()
        self._discord_chan_var  = ctk.StringVar()

        # Apply language chosen at start
        set_language(self._lang)

        self.title("AURA – Setup")
        self.geometry("600x640")
        self.minsize(560, 580)
        self.resizable(True, False)
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
            self._render_accounts_step,
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

    def _render_accounts_step(self) -> None:
        """Render the accounts/services linking step inside a scrollable frame."""
        frame = self._content_frame

        ctk.CTkLabel(
            frame,
            text=t("onboarding.accounts_title"),
            font=("Consolas", 18, "bold"),
            text_color=NEON_CYAN,
        ).pack(pady=(12, 2))

        ctk.CTkLabel(
            frame,
            text=t("onboarding.accounts_subtitle"),
            font=("Consolas", 11),
            text_color=TEXT_DIM,
        ).pack(pady=(0, 8))

        # Scrollable area for all service fields
        scroll = ctk.CTkScrollableFrame(
            frame,
            fg_color=BG_DEEP,
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=NEON_BLUE,
        )
        scroll.pack(fill="both", expand=True, pady=(0, 4))

        # ── Twitch ──────────────────────────────────────────────────────
        self._add_section_header(scroll, t("onboarding.twitch_section"), "🟣")
        self._twitch_entry = ctk.CTkEntry(
            scroll,
            textvariable=self._twitch_var,
            placeholder_text=t("onboarding.twitch_placeholder"),
            height=38,
            font=("Consolas", 12),
            fg_color=BG_PANEL,
            border_color=NEON_BLUE,
            text_color=TEXT_BRIGHT,
        )
        self._twitch_entry.pack(fill="x", padx=8, pady=(0, 2))
        self._twitch_error = ctk.CTkLabel(
            scroll,
            text="",
            font=("Consolas", 10),
            text_color=NEON_RED,
            anchor="w",
        )
        self._twitch_error.pack(fill="x", padx=8, pady=(0, 6))

        # ── YouTube ─────────────────────────────────────────────────────
        self._add_section_header(scroll, t("onboarding.youtube_section"), "🔴")
        self._youtube_entry = ctk.CTkEntry(
            scroll,
            textvariable=self._youtube_var,
            placeholder_text=t("onboarding.youtube_placeholder"),
            height=38,
            font=("Consolas", 12),
            fg_color=BG_PANEL,
            border_color=NEON_BLUE,
            text_color=TEXT_BRIGHT,
        )
        self._youtube_entry.pack(fill="x", padx=8, pady=(0, 2))
        self._youtube_error = ctk.CTkLabel(
            scroll,
            text="",
            font=("Consolas", 10),
            text_color=NEON_RED,
            anchor="w",
        )
        self._youtube_error.pack(fill="x", padx=8, pady=(0, 6))

        # ── OBS Studio ──────────────────────────────────────────────────
        self._add_section_header(scroll, t("onboarding.obs_section"), "⚫")
        obs_row = ctk.CTkFrame(scroll, fg_color=BG_DEEP)
        obs_row.pack(fill="x", padx=8, pady=(0, 4))
        obs_row.columnconfigure(0, weight=3)
        obs_row.columnconfigure(1, weight=1)

        # Host
        ctk.CTkLabel(
            obs_row,
            text=t("onboarding.obs_host_label"),
            font=("Consolas", 11),
            text_color=TEXT_DIM,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(0, 6), pady=(0, 2))
        ctk.CTkLabel(
            obs_row,
            text=t("onboarding.obs_port_label"),
            font=("Consolas", 11),
            text_color=TEXT_DIM,
            anchor="w",
        ).grid(row=0, column=1, sticky="w", pady=(0, 2))

        ctk.CTkEntry(
            obs_row,
            textvariable=self._obs_host_var,
            placeholder_text=t("onboarding.obs_host_placeholder"),
            height=36,
            font=("Consolas", 12),
            fg_color=BG_PANEL,
            border_color=BORDER,
            text_color=TEXT_BRIGHT,
        ).grid(row=1, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkEntry(
            obs_row,
            textvariable=self._obs_port_var,
            placeholder_text=t("onboarding.obs_port_placeholder"),
            height=36,
            font=("Consolas", 12),
            fg_color=BG_PANEL,
            border_color=BORDER,
            text_color=TEXT_BRIGHT,
        ).grid(row=1, column=1, sticky="ew")

        self._obs_port_error = ctk.CTkLabel(
            scroll,
            text="",
            font=("Consolas", 10),
            text_color=NEON_RED,
            anchor="w",
        )
        self._obs_port_error.pack(fill="x", padx=8, pady=(0, 2))

        ctk.CTkLabel(
            scroll,
            text=t("onboarding.obs_password_label"),
            font=("Consolas", 11),
            text_color=TEXT_DIM,
            anchor="w",
        ).pack(fill="x", padx=8)
        ctk.CTkEntry(
            scroll,
            textvariable=self._obs_password_var,
            placeholder_text=t("onboarding.obs_password_placeholder"),
            show="●",
            height=36,
            font=("Consolas", 12),
            fg_color=BG_PANEL,
            border_color=BORDER,
            text_color=TEXT_BRIGHT,
        ).pack(fill="x", padx=8, pady=(0, 8))

        # ── Discord ─────────────────────────────────────────────────────
        self._add_section_header(scroll, t("onboarding.discord_section"), "🔵")
        ctk.CTkLabel(
            scroll,
            text=t("onboarding.discord_token_label"),
            font=("Consolas", 11),
            text_color=TEXT_DIM,
            anchor="w",
        ).pack(fill="x", padx=8)
        ctk.CTkEntry(
            scroll,
            textvariable=self._discord_token_var,
            placeholder_text=t("onboarding.discord_token_placeholder"),
            show="●",
            height=36,
            font=("Consolas", 12),
            fg_color=BG_PANEL,
            border_color=BORDER,
            text_color=TEXT_BRIGHT,
        ).pack(fill="x", padx=8, pady=(0, 6))

        ctk.CTkLabel(
            scroll,
            text=t("onboarding.discord_channel_label"),
            font=("Consolas", 11),
            text_color=TEXT_DIM,
            anchor="w",
        ).pack(fill="x", padx=8)
        ctk.CTkEntry(
            scroll,
            textvariable=self._discord_chan_var,
            placeholder_text=t("onboarding.discord_channel_placeholder"),
            height=36,
            font=("Consolas", 12),
            fg_color=BG_PANEL,
            border_color=BORDER,
            text_color=TEXT_BRIGHT,
        ).pack(fill="x", padx=8, pady=(0, 10))

    def _add_section_header(self, parent: ctk.CTkScrollableFrame, label: str, icon: str) -> None:
        """Add a styled section divider inside the scrollable accounts frame."""
        row = ctk.CTkFrame(parent, fg_color=BG_PANEL, corner_radius=6, height=32)
        row.pack(fill="x", padx=0, pady=(6, 4))
        row.pack_propagate(False)
        ctk.CTkLabel(
            row,
            text=f"{icon}  {label}",
            font=("Consolas", 12, "bold"),
            text_color=NEON_CYAN,
            anchor="w",
        ).pack(side="left", padx=12)

    def _render_confirm_step(self) -> None:
        frame = self._content_frame

        ctk.CTkLabel(
            frame,
            text=t("onboarding.confirm_title"),
            font=("Consolas", 18, "bold"),
            text_color=NEON_CYAN,
        ).pack(pady=(20, 12))

        none_str = t("onboarding.confirm_none")
        lang_display = "Français" if self._lang == "fr" else "English"

        # Build OBS summary
        obs_host = self._obs_host_var.get().strip() or "localhost"
        obs_port = self._obs_port_var.get().strip() or "4455"
        obs_summary = f"{obs_host}:{obs_port}" if (obs_host or obs_port) else none_str

        # Build Discord summary (mask token)
        discord_token = self._discord_token_var.get().strip()
        discord_chan = self._discord_chan_var.get().strip()
        if discord_token:
            discord_summary = f"{_TOKEN_MASK_CHAR * _TOKEN_MASK_LENGTH}  ch:{discord_chan or '—'}"
        elif discord_chan:
            discord_summary = f"ch:{discord_chan}"
        else:
            discord_summary = none_str

        rows = [
            (t("onboarding.confirm_language"), lang_display),
            (t("onboarding.confirm_username"),  self._username_var.get() or none_str),
            (t("onboarding.confirm_twitch"),    self._twitch_var.get() or none_str),
            (t("onboarding.confirm_youtube"),   self._youtube_var.get() or none_str),
            (t("onboarding.confirm_obs"),       obs_summary),
            (t("onboarding.confirm_discord"),   discord_summary),
        ]

        card = ctk.CTkFrame(frame, fg_color=BG_PANEL, corner_radius=10)
        card.pack(fill="x", padx=8, pady=4)

        for label, value in rows:
            row = ctk.CTkFrame(card, fg_color=BG_PANEL)
            row.pack(fill="x", padx=16, pady=5)
            ctk.CTkLabel(
                row,
                text=f"{label}:",
                font=("Consolas", 11),
                text_color=TEXT_DIM,
                width=100,
                anchor="w",
            ).pack(side="left")
            ctk.CTkLabel(
                row,
                text=value,
                font=("Consolas", 11, "bold"),
                text_color=TEXT_BRIGHT,
                anchor="w",
                wraplength=330,
            ).pack(side="left", padx=(8, 0))

        self._save_error = ctk.CTkLabel(
            frame,
            text="",
            font=("Consolas", 11),
            text_color=NEON_RED,
        )
        self._save_error.pack(pady=(10, 0))

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
            valid = True
            # Twitch URL optional but must be valid if provided
            twitch_val = self._twitch_var.get().strip()
            if twitch_val and not validate_twitch(twitch_val):
                self._twitch_error.configure(text=t("onboarding.twitch_invalid"))
                valid = False
            else:
                self._twitch_error.configure(text="")

            # YouTube URL optional but must be valid if provided
            youtube_val = self._youtube_var.get().strip()
            if youtube_val and not _validate_youtube(youtube_val):
                self._youtube_error.configure(text=t("onboarding.youtube_invalid"))
                valid = False
            else:
                self._youtube_error.configure(text="")

            # OBS port must be valid if provided
            obs_port_val = self._obs_port_var.get().strip()
            if not _validate_obs_port(obs_port_val):
                self._obs_port_error.configure(text=t("onboarding.obs_port_invalid"))
                valid = False
            else:
                self._obs_port_error.configure(text="")

            return valid

        return True

    def _finish(self) -> None:
        """Build the profile dict and hand off to the caller."""
        obs_port_str = self._obs_port_var.get().strip()
        obs_port = int(obs_port_str) if obs_port_str else 4455

        profile = build_profile(
            language=self._lang,
            username=self._username_var.get(),
            twitch=self._twitch_var.get(),
            youtube_channel=self._youtube_var.get(),
            obs_host=self._obs_host_var.get().strip() or "localhost",
            obs_port=obs_port,
            obs_password=self._obs_password_var.get(),
            discord_bot_token=self._discord_token_var.get(),
            discord_channel_id=self._discord_chan_var.get(),
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
