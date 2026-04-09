"""
gui/app.py
==========
AURA desktop GUI — redesigned dark theme with purple/cyan accent palette.

Layout (top to bottom):
  1. Header bar   – logo, version, language toggle, gear icon
  2. Status row   – OBS / Stream / Mic cards
  3. Visualizer   – 16-bar animated mic amplitude display
  4. Transcript   – scrollable USER / AURA conversation log
  5. Accounts row – Twitch / Discord / YouTube connect buttons
  6. Command bar  – text input + Send button
  7. Settings     – slide-in sidebar (gear icon)

Runs the voice assistant loop in a background daemon thread and mirrors
all state changes to the UI via a thread-safe ``queue.Queue`` polled with
Tkinter's ``after()`` scheduler.
"""

from __future__ import annotations

import logging
import math
import os
import queue
import random
import threading
import time
from typing import Any, Callable

import customtkinter as ctk
import tkinter as tk

from version import __version__
from utils.i18n import i18n

logger = logging.getLogger("AURA.GUI")

# ──────────────────────────────────────────────────────────────────────────────
# Colour palette
# ──────────────────────────────────────────────────────────────────────────────
BG_DEEP     = "#0D0D0F"   # main window background
BG_CARD     = "#16161A"   # card / panel surface
ACCENT_PUR  = "#7C5CFC"   # primary accent – purple
ACCENT_CYAN = "#00E5C0"   # secondary accent – cyan-teal
BORDER      = "#2A2A35"   # subtle panel border
TEXT_WHITE  = "#FFFFFF"   # primary text colour
TEXT_DIM    = "#888899"   # secondary / disabled text
DOT_GREEN   = "#00C96A"   # online indicator
DOT_RED     = "#FF4466"   # offline indicator

# ──────────────────────────────────────────────────────────────────────────────
# Colour helpers
# ──────────────────────────────────────────────────────────────────────────────

def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def _blend(colour: str, alpha: float, bg: str = BG_DEEP) -> str:
    """Blend *colour* with *bg* at opacity *alpha* (0.0 – 1.0)."""
    cr, cg, cb = _hex_to_rgb(colour)
    br, bg_g, bb = _hex_to_rgb(bg)
    r = int(br + (cr - br) * alpha)
    g = int(bg_g + (cg - bg_g) * alpha)
    b = int(bb + (cb - bb) * alpha)
    return _rgb_to_hex(
        max(0, min(255, r)),
        max(0, min(255, g)),
        max(0, min(255, b)),
    )


def _lerp_colour(c1: str, c2: str, t: float) -> str:
    """Linearly interpolate between two hex colours at position *t* (0.0–1.0)."""
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    return _rgb_to_hex(
        int(r1 + (r2 - r1) * t),
        int(g1 + (g2 - g1) * t),
        int(b1 + (b2 - b1) * t),
    )


# ──────────────────────────────────────────────────────────────────────────────
# 16-bar Visualizer Canvas
# ──────────────────────────────────────────────────────────────────────────────

class VisualizerCanvas(tk.Canvas):
    """Animated bar chart that reacts to microphone input amplitude."""

    NUM_BARS   = 16
    BAR_GAP    = 4
    FPS        = 30

    def __init__(self, parent: tk.Widget, width: int = 600, height: int = 80, **kwargs) -> None:
        super().__init__(
            parent,
            width=width, height=height,
            bg=BG_DEEP,
            highlightthickness=0,
            **kwargs,
        )
        self._w = width
        self._h = height
        self._active = False
        self._tick = 0

        bar_total_w = width - (self.NUM_BARS + 1) * self.BAR_GAP
        self._bar_w = max(4, bar_total_w // self.NUM_BARS)
        self._heights   = [0.0] * self.NUM_BARS
        self._targets   = [0.0] * self.NUM_BARS
        self._bar_ids: list[int] = []

        self._build_bars()
        self._animate()

    def _build_bars(self) -> None:
        total_w = self.NUM_BARS * (self._bar_w + self.BAR_GAP) - self.BAR_GAP
        x0 = (self._w - total_w) // 2
        base_y = self._h - 4
        for i in range(self.NUM_BARS):
            x = x0 + i * (self._bar_w + self.BAR_GAP)
            bid = self.create_rectangle(
                x, base_y, x + self._bar_w, base_y,
                fill=ACCENT_PUR, outline="",
            )
            self._bar_ids.append(bid)

    def set_active(self, active: bool) -> None:
        """Enable/disable the animation (listening/speaking = True)."""
        self._active = active

    def _animate(self) -> None:
        self._tick += 1
        total_w = self.NUM_BARS * (self._bar_w + self.BAR_GAP) - self.BAR_GAP
        x0 = (self._w - total_w) // 2
        base_y = self._h - 4
        max_h = self._h - 8

        for i in range(self.NUM_BARS):
            if self._active:
                if self._tick % 2 == i % 2:
                    self._targets[i] = random.uniform(0.1, 1.0)
                # Smooth ease towards target
                self._heights[i] += (self._targets[i] - self._heights[i]) * 0.3
            else:
                self._heights[i] *= 0.85
                if self._heights[i] < 0.02:
                    self._heights[i] = 0.0

            bh = max(3, int(self._heights[i] * max_h))
            t = self._heights[i]
            colour = _lerp_colour(ACCENT_PUR, ACCENT_CYAN, t)

            x = x0 + i * (self._bar_w + self.BAR_GAP)
            self.coords(self._bar_ids[i], x, base_y - bh, x + self._bar_w, base_y)
            self.itemconfig(self._bar_ids[i], fill=colour)

        self.after(1000 // self.FPS, self._animate)


# ──────────────────────────────────────────────────────────────────────────────
# Settings Sidebar
# ──────────────────────────────────────────────────────────────────────────────

class SettingsSidebar(ctk.CTkFrame):
    """Slide-in sidebar for AURA settings."""

    def __init__(self, parent: ctk.CTk, config: dict, on_save: Callable[[], None]) -> None:
        super().__init__(
            parent,
            fg_color=BG_CARD,
            corner_radius=0,
            border_width=1,
            border_color=BORDER,
            width=340,
        )
        self._config = config
        self._on_save = on_save
        self._visible = False
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text=i18n.t("settings"),
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=ACCENT_PUR,
        ).grid(row=0, column=0, padx=20, pady=(16, 8), sticky="w")

        # ── Language selector ──────────────────────────────────────────
        ctk.CTkLabel(
            self, text=i18n.t("language"),
            font=ctk.CTkFont(size=12), text_color=TEXT_WHITE,
        ).grid(row=1, column=0, padx=20, sticky="w")
        current_lang = self._config.get("language", "en")
        self._lang_var = ctk.StringVar(
            value=i18n.t("language_fr") if current_lang == "fr" else i18n.t("language_en")
        )
        ctk.CTkOptionMenu(
            self,
            values=[i18n.t("language_en"), i18n.t("language_fr")],
            variable=self._lang_var,
            fg_color=BG_DEEP,
            button_color=ACCENT_PUR,
            button_hover_color=_blend(ACCENT_PUR, 0.8),
            text_color=TEXT_WHITE,
        ).grid(row=2, column=0, padx=20, pady=(2, 12), sticky="ew")

        # ── Whisper model selector ─────────────────────────────────────
        ctk.CTkLabel(
            self, text=i18n.t("whisper_model"),
            font=ctk.CTkFont(size=12), text_color=TEXT_WHITE,
        ).grid(row=3, column=0, padx=20, sticky="w")
        self._whisper_var = ctk.StringVar(
            value=self._config.get("voice", {}).get("whisper_model", "base")
        )
        ctk.CTkOptionMenu(
            self,
            values=["tiny", "base", "small", "medium"],
            variable=self._whisper_var,
            fg_color=BG_DEEP,
            button_color=ACCENT_PUR,
            button_hover_color=_blend(ACCENT_PUR, 0.8),
            text_color=TEXT_WHITE,
        ).grid(row=4, column=0, padx=20, pady=(2, 12), sticky="ew")

        # ── OBS fields ────────────────────────────────────────────────
        obs_cfg = self._config.get("obs", {})
        self._obs_host  = self._labeled_entry(row=5,  label=i18n.t("obs_host"),     value=obs_cfg.get("host", "localhost"))
        self._obs_port  = self._labeled_entry(row=7,  label=i18n.t("obs_port"),     value=str(obs_cfg.get("port", 4455)))
        self._obs_pass  = self._labeled_entry(row=9,  label=i18n.t("obs_password"), value=obs_cfg.get("password", ""), show="*")

        # ── Twitch fields ─────────────────────────────────────────────
        tw_cfg = self._config.get("twitch", {})
        self._tw_id     = self._labeled_entry(row=11, label=i18n.t("twitch_client_id"),     value=tw_cfg.get("client_id", ""))
        self._tw_secret = self._labeled_entry(row=13, label=i18n.t("twitch_client_secret"), value=tw_cfg.get("client_secret", ""), show="*")

        # ── Streaming platform links ───────────────────────────────────
        profile_cfg = self._config.get("_profile", {})
        self._tw_link  = self._labeled_entry(row=15, label=i18n.t("twitch_link"),  value=profile_cfg.get("twitch", ""))
        self._yt_link  = self._labeled_entry(row=17, label=i18n.t("youtube_link"), value=profile_cfg.get("youtube_channel", ""))
        self._dc_link  = self._labeled_entry(row=19, label=i18n.t("discord_link"), value=profile_cfg.get("discord_channel_id", ""))

        # ── Save button ───────────────────────────────────────────────
        ctk.CTkButton(
            self, text=i18n.t("save"),
            fg_color=ACCENT_PUR,
            hover_color=_blend(ACCENT_PUR, 0.8),
            text_color=TEXT_WHITE,
            command=self._save,
        ).grid(row=21, column=0, padx=20, pady=20, sticky="ew")

    def _labeled_entry(
        self, row: int, label: str, value: str, show: str = ""
    ) -> ctk.CTkEntry:
        ctk.CTkLabel(
            self, text=label, font=ctk.CTkFont(size=12), text_color=TEXT_WHITE,
        ).grid(row=row, column=0, padx=20, sticky="w")
        entry = ctk.CTkEntry(
            self,
            fg_color=BG_DEEP, border_color=BORDER, text_color=TEXT_WHITE,
            show=show,
        )
        entry.insert(0, value)
        entry.grid(row=row + 1, column=0, padx=20, pady=(2, 8), sticky="ew")
        return entry

    def _save(self) -> None:
        # Resolve selected language
        fr_label = i18n.t("language_fr")
        new_lang = "fr" if self._lang_var.get() == fr_label else "en"
        self._config["language"] = new_lang
        i18n.set_language(new_lang)

        self._config.setdefault("voice", {})["whisper_model"] = self._whisper_var.get()
        self._config.setdefault("obs", {})["host"]     = self._obs_host.get()
        self._config.setdefault("obs", {})["password"] = self._obs_pass.get()
        try:
            self._config["obs"]["port"] = int(self._obs_port.get())
        except ValueError:
            pass
        self._config.setdefault("twitch", {})["client_id"]     = self._tw_id.get()
        self._config.setdefault("twitch", {})["client_secret"] = self._tw_secret.get()

        # Persist link changes to user profile
        profile_cfg = self._config.setdefault("_profile", {})
        profile_cfg["twitch"]          = self._tw_link.get().strip()
        profile_cfg["youtube_channel"] = self._yt_link.get().strip()
        profile_cfg["discord_channel_id"] = self._dc_link.get().strip()
        profile_cfg["language"] = new_lang
        self._flush_profile(profile_cfg)

        self._on_save()
        self.toggle()

    @staticmethod
    def _flush_profile(profile_patch: dict) -> None:
        """Merge *profile_patch* into the saved user profile on disk."""
        try:
            from core.onboarding.onboarding_storage import load_profile, save_profile  # noqa: PLC0415
            profile = load_profile()
            profile.update(profile_patch)
            save_profile(profile)
        except Exception:  # pylint: disable=broad-except
            pass

    def toggle(self) -> None:
        """Show or hide the sidebar."""
        if self._visible:
            self.place_forget()
            self._visible = False
        else:
            self.place(relx=1.0, rely=0.0, relheight=1.0, anchor="ne", x=0)
            self.lift()
            self._visible = True


# ──────────────────────────────────────────────────────────────────────────────
# Main Application Window
# ──────────────────────────────────────────────────────────────────────────────

class AuraApp(ctk.CTk):
    """Main AURA desktop window – redesigned dark theme."""

    def __init__(self, config: dict) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        super().__init__()

        self._config   = config
        self._state    = "idle"
        self._muted    = False
        self._running  = False
        self._msg_queue: queue.Queue = queue.Queue()
        self._obs_connected  = False
        self._stream_live    = False
        self._mic_active     = False

        # Load user profile so settings sidebar can show/edit links
        try:
            from core.onboarding.onboarding_storage import load_profile  # noqa: PLC0415
            self._config.setdefault("_profile", load_profile())
        except Exception:  # pylint: disable=broad-except
            self._config.setdefault("_profile", {})

        self.title("AURA – AI Voice Assistant")
        self.geometry("980x740")
        self.minsize(860, 660)
        self.configure(fg_color=BG_DEEP)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        _icon = os.path.join(os.path.dirname(__file__), "..", "assets", "aura.ico")
        if os.path.isfile(_icon):
            try:
                self.iconbitmap(_icon)
            except Exception:
                pass

        self._build_ui()
        self._start_aura()
        self._poll_queue()

    # ──────────────────────────────────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        # Rows: header, status, visualizer, transcript, accounts, command
        self.grid_rowconfigure(3, weight=1)   # transcript expands

        self._build_header()        # row 0
        self._build_status_row()    # row 1
        self._build_visualizer()    # row 2
        self._build_transcript()    # row 3
        self._build_accounts_row()  # row 4
        self._build_command_bar()   # row 5

        # Settings sidebar (placed dynamically)
        self._sidebar = SettingsSidebar(self, self._config, self._on_settings_save)

    # ── Header bar ────────────────────────────────────────────────────────

    def _build_header(self) -> None:
        hdr = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, height=56)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_columnconfigure(1, weight=1)
        hdr.grid_propagate(False)

        # Logo
        ctk.CTkLabel(
            hdr,
            text="AURA",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=ACCENT_PUR,
        ).grid(row=0, column=0, padx=(20, 6), pady=12, sticky="w")

        ctk.CTkLabel(
            hdr,
            text=f"v{__version__}",
            font=ctk.CTkFont(size=10),
            text_color=TEXT_DIM,
        ).grid(row=0, column=1, sticky="w")

        # Language toggle
        self._lang_btn = ctk.CTkButton(
            hdr,
            text=i18n.get_language().upper(),
            width=48, height=30,
            fg_color=BG_DEEP, hover_color=BG_CARD,
            text_color=TEXT_WHITE,
            border_width=1, border_color=BORDER,
            corner_radius=6,
            command=self._toggle_language,
        )
        self._lang_btn.grid(row=0, column=2, padx=(0, 8), pady=12)

        # Gear icon
        ctk.CTkButton(
            hdr,
            text="⚙",
            width=36, height=30,
            fg_color=BG_DEEP, hover_color=BG_CARD,
            text_color=TEXT_DIM,
            border_width=1, border_color=BORDER,
            corner_radius=6,
            command=self._sidebar.toggle,
        ).grid(row=0, column=3, padx=(0, 20), pady=12)

        # Bottom border
        ctk.CTkFrame(self, fg_color=BORDER, height=1, corner_radius=0).grid(
            row=0, column=0, sticky="sew"
        )

    # ── Status row ────────────────────────────────────────────────────────

    def _build_status_row(self) -> None:
        row_frame = ctk.CTkFrame(self, fg_color=BG_DEEP, corner_radius=0, height=72)
        row_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=12)
        row_frame.grid_columnconfigure((0, 1, 2), weight=1)
        row_frame.grid_propagate(False)

        self._obs_dot,    self._obs_label    = self._status_card(row_frame, col=0)
        self._stream_dot, self._stream_label = self._status_card(row_frame, col=1)
        self._mic_dot,    self._mic_label    = self._status_card(row_frame, col=2)

        self._update_status_cards()

    def _status_card(self, parent: ctk.CTkFrame, col: int) -> tuple[ctk.CTkLabel, ctk.CTkLabel]:
        card = ctk.CTkFrame(
            parent,
            fg_color=BG_CARD, corner_radius=10,
            border_width=1, border_color=BORDER,
        )
        card.grid(row=0, column=col, sticky="nsew", padx=6, pady=0)

        dot   = ctk.CTkLabel(card, text="●", font=ctk.CTkFont(size=14), text_color=DOT_RED)
        label = ctk.CTkLabel(card, text="–",  font=ctk.CTkFont(size=11), text_color=TEXT_WHITE)
        dot.pack(side="left", padx=(16, 6), pady=10)
        label.pack(side="left", padx=(0, 16), pady=10)
        return dot, label

    def _update_status_cards(self) -> None:
        self._obs_dot.configure(text_color=DOT_GREEN if self._obs_connected else DOT_RED)
        self._obs_label.configure(
            text=i18n.t("obs_connected") if self._obs_connected else i18n.t("obs_disconnected")
        )
        self._stream_dot.configure(text_color=DOT_GREEN if self._stream_live else DOT_RED)
        self._stream_label.configure(
            text=i18n.t("stream_live") if self._stream_live else i18n.t("stream_offline")
        )
        self._mic_dot.configure(text_color=ACCENT_CYAN if self._mic_active else DOT_RED)
        self._mic_label.configure(
            text=i18n.t("mic_active") if self._mic_active else i18n.t("mic_idle")
        )

    # ── Visualizer ────────────────────────────────────────────────────────

    def _build_visualizer(self) -> None:
        wrap = ctk.CTkFrame(self, fg_color=BG_DEEP, corner_radius=0, height=88)
        wrap.grid(row=2, column=0, sticky="ew", padx=12)
        wrap.grid_propagate(False)
        wrap.grid_columnconfigure(0, weight=1)

        self._visualizer = VisualizerCanvas(wrap, width=940, height=72)
        self._visualizer.pack(padx=0, pady=8, fill="x", expand=True)

    # ── Transcript panel ──────────────────────────────────────────────────

    def _build_transcript(self) -> None:
        wrap = ctk.CTkFrame(self, fg_color=BG_DEEP, corner_radius=0)
        wrap.grid(row=3, column=0, sticky="nsew", padx=12, pady=(0, 0))
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(0, weight=1)

        self._transcript = ctk.CTkTextbox(
            wrap,
            font=ctk.CTkFont(family="Courier New", size=13),
            fg_color=BG_DEEP,
            text_color=TEXT_WHITE,
            corner_radius=0,
            border_width=0,
            wrap="word",
        )
        self._transcript.grid(row=0, column=0, sticky="nsew")
        self._transcript.configure(state="disabled")

        # Configure coloured tags via the underlying tk.Text widget
        self._transcript._textbox.tag_config("user",  foreground=ACCENT_CYAN)
        self._transcript._textbox.tag_config("aura",  foreground=ACCENT_PUR)
        self._transcript._textbox.tag_config("system", foreground=TEXT_DIM)

    def _append_transcript(self, speaker: str, text: str) -> None:
        """Append a line to the transcript with speaker colouring."""
        ts = time.strftime("%H:%M:%S")
        tag = {"USER": "user", "AURA": "aura"}.get(speaker, "system")
        line = f"[{ts}]  {speaker}: {text}\n"

        self._transcript.configure(state="normal")
        self._transcript._textbox.insert("end", line, tag)
        self._transcript._textbox.see("end")
        self._transcript.configure(state="disabled")

    # ── Accounts row ──────────────────────────────────────────────────────

    def _build_accounts_row(self) -> None:
        row_frame = ctk.CTkFrame(self, fg_color=BG_DEEP, corner_radius=0, height=52)
        row_frame.grid(row=4, column=0, sticky="ew", padx=12, pady=8)
        row_frame.grid_columnconfigure((0, 1, 2), weight=1)
        row_frame.grid_propagate(False)

        self._twitch_btn  = self._account_btn(row_frame, 0, "Twitch",  "#6441a5", self._on_connect_twitch)
        self._discord_btn = self._account_btn(row_frame, 1, "Discord", "#5865f2", self._on_connect_discord)
        self._youtube_btn = self._account_btn(row_frame, 2, "YouTube", "#c4302b", self._on_connect_youtube)
        self._refresh_account_buttons()

    def _account_btn(
        self, parent: ctk.CTkFrame, col: int, name: str, color: str, cmd: Callable[[], None]
    ) -> ctk.CTkButton:
        btn = ctk.CTkButton(
            parent, text=name,
            fg_color=color,
            hover_color=_blend(color, 0.8, BG_DEEP),
            text_color=TEXT_WHITE,
            corner_radius=8,
            height=38,
            command=cmd,
        )
        btn.grid(row=0, column=col, sticky="nsew", padx=6, pady=0)
        return btn

    def _refresh_account_buttons(self) -> None:
        try:
            from integrations.account_manager import AccountManager  # noqa: PLC0415
            mgr = AccountManager(self._config)
            status = mgr.get_status()
        except Exception:  # pylint: disable=broad-except
            status = {"twitch": False, "discord": False, "youtube": False}

        suffix_t = f"  {i18n.t('connected')}" if status.get("twitch")  else f"  {i18n.t('connect')}"
        suffix_d = f"  {i18n.t('connected')}" if status.get("discord") else f"  {i18n.t('connect')}"
        suffix_y = f"  {i18n.t('connected')}" if status.get("youtube") else f"  {i18n.t('connect')}"
        self._twitch_btn.configure(text=f"Twitch{suffix_t}")
        self._discord_btn.configure(text=f"Discord{suffix_d}")
        self._youtube_btn.configure(text=f"YouTube{suffix_y}")

    # ── Command input bar ─────────────────────────────────────────────────

    def _build_command_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, height=52)
        bar.grid(row=5, column=0, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)
        bar.grid_propagate(False)

        self._cmd_entry = ctk.CTkEntry(
            bar,
            placeholder_text=i18n.t("command_placeholder"),
            fg_color=BG_DEEP,
            border_color=BORDER,
            text_color=TEXT_WHITE,
            height=38,
        )
        self._cmd_entry.grid(row=0, column=0, padx=(16, 8), pady=7, sticky="ew")
        self._cmd_entry.bind("<Return>", lambda _e: self._on_send_command())

        ctk.CTkButton(
            bar,
            text=i18n.t("send"),
            width=72, height=38,
            fg_color=ACCENT_PUR,
            hover_color=_blend(ACCENT_PUR, 0.8),
            text_color=TEXT_WHITE,
            corner_radius=8,
            command=self._on_send_command,
        ).grid(row=0, column=1, padx=(0, 16), pady=7)

    # ──────────────────────────────────────────────────────────────────────
    # State management
    # ──────────────────────────────────────────────────────────────────────

    def _set_state(self, state: str) -> None:
        self._state = state
        listening_states = ("listening", "speaking")
        self._mic_active = state in listening_states
        self._visualizer.set_active(self._mic_active)
        self._update_status_cards()

    # ──────────────────────────────────────────────────────────────────────
    # Voice loop (background thread)
    # ──────────────────────────────────────────────────────────────────────

    def _start_aura(self) -> None:
        self._running = True
        threading.Thread(
            target=self._voice_loop, daemon=True, name="AURA-VoiceLoop"
        ).start()
        self._set_state("listening")

    def _voice_loop(self) -> None:
        """Background thread: run the voice assistant loop."""
        try:
            from core.session import create_session  # noqa: PLC0415
            from core.onboarding.onboarding_storage import load_profile  # noqa: PLC0415
            from voice.wake_word import WakeWordDetector  # noqa: PLC0415

            profile = load_profile()
            session = create_session(self._config, profile=profile)
            stt = session.stt
            tts = session.tts
            parser = session.parser
            handler = session.handler
            wake_detector = WakeWordDetector(self._config)

            if session.events is not None:
                session.events.start()
        except Exception as exc:  # pylint: disable=broad-except
            self._post("transcript", ("SYSTEM", f"Initialisation failed: {exc}"))
            self._post("state", "error")
            return

        self._post("transcript", ("SYSTEM", "AURA initialised. Listening for commands."))
        self._post("transcript", ("AURA", i18n.t("greeting")))
        tts.speak(i18n.t("greeting"))
        if wake_detector.is_enabled:
            self._post("transcript", ("SYSTEM", "Wake word detection active — say 'AURA'."))

        while self._running:
            try:
                if self._muted:
                    time.sleep(0.1)
                    continue

                # Phase 1: Wake word (low-CPU idle)
                if wake_detector.is_enabled:
                    self._post("state", "idle")
                    if not wake_detector.wait_for_wake_word(timeout=5.0):
                        continue
                    self._post("transcript", ("SYSTEM", "Wake word detected!"))

                # Phase 2: Full command recognition
                self._post("state", "listening")
                text = stt.listen()
                if not text:
                    continue

                self._post("transcript", ("USER", text))
                self._post("state", "processing")

                # Phase 3: Parse + execute
                if session.decision_engine is not None:
                    response = session.decision_engine.process(text)
                else:
                    command = parser.parse(text)
                    if command is None:
                        response = i18n.t("unknown_command")
                    else:
                        response = handler.execute(command, raw_text=text)

                self._post("transcript", ("AURA", response))
                self._post("state", "speaking")
                tts.speak(response)

            except Exception as exc:  # pylint: disable=broad-except
                logger.error("Voice loop error: %s", exc, exc_info=True)
                self._post("transcript", ("SYSTEM", f"Error: {exc}"))

        self._post("state", "idle")
        self._post("transcript", ("SYSTEM", "AURA stopped."))

    # ──────────────────────────────────────────────────────────────────────
    # Message queue
    # ──────────────────────────────────────────────────────────────────────

    def _post(self, kind: str, data: Any) -> None:
        self._msg_queue.put((kind, data))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, data = self._msg_queue.get_nowait()
                if kind == "state":
                    self._set_state(data)
                elif kind == "transcript":
                    speaker, text = data
                    self._append_transcript(speaker, text)
                elif kind == "obs_status":
                    self._obs_connected = bool(data)
                    self._update_status_cards()
                elif kind == "stream_status":
                    self._stream_live = bool(data)
                    self._update_status_cards()
                elif kind == "accounts":
                    self._refresh_account_buttons()
        except queue.Empty:
            pass
        self.after(50, self._poll_queue)

    # ──────────────────────────────────────────────────────────────────────
    # Button / control callbacks
    # ──────────────────────────────────────────────────────────────────────

    def _toggle_language(self) -> None:
        current = i18n.get_language()
        new_lang = "fr" if current == "en" else "en"
        i18n.set_language(new_lang)
        self._config["language"] = new_lang
        self._lang_btn.configure(text=new_lang.upper())

    def _on_send_command(self) -> None:
        text = self._cmd_entry.get().strip()
        if not text:
            return
        self._cmd_entry.delete(0, "end")
        self._append_transcript("USER", text)

        def _run() -> None:
            try:
                from core.command_parser import CommandParser  # noqa: PLC0415
                from core.action_handler import ActionHandler  # noqa: PLC0415
                parser = CommandParser(self._config)
                handler = ActionHandler(self._config)
                command = parser.parse(text)
                if command is None:
                    response = i18n.t("unknown_command")
                else:
                    response = handler.execute(command, raw_text=text)
            except Exception as exc:  # pylint: disable=broad-except
                response = f"Error: {exc}"
            self._post("transcript", ("AURA", response))

        threading.Thread(target=_run, daemon=True, name="AURA-TextCmd").start()

    def _on_connect_twitch(self) -> None:
        threading.Thread(
            target=self._connect_account, args=("twitch",),
            daemon=True, name="AURA-ConnectTwitch"
        ).start()

    def _on_connect_discord(self) -> None:
        threading.Thread(
            target=self._connect_account, args=("discord",),
            daemon=True, name="AURA-ConnectDiscord"
        ).start()

    def _on_connect_youtube(self) -> None:
        threading.Thread(
            target=self._connect_account, args=("youtube",),
            daemon=True, name="AURA-ConnectYouTube"
        ).start()

    def _connect_account(self, platform: str) -> None:
        try:
            from integrations.account_manager import AccountManager  # noqa: PLC0415
            mgr = AccountManager(self._config)
            method = getattr(mgr, f"connect_{platform}")
            ok = method()
            if ok:
                self._post("accounts", None)
                self._post("transcript", ("SYSTEM", f"{platform.capitalize()} connected."))
            else:
                self._post("transcript", ("SYSTEM", f"{platform.capitalize()} connection failed."))
        except Exception as exc:  # pylint: disable=broad-except
            self._post("transcript", ("SYSTEM", f"Error connecting {platform}: {exc}"))

    def _on_settings_save(self) -> None:
        try:
            import json  # noqa: PLC0415
            import os as _os  # noqa: PLC0415
            repo_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
            config_path = _os.path.join(repo_root, "config.json")
            with open(config_path, "w", encoding="utf-8") as fh:
                json.dump(self._config, fh, indent=2, ensure_ascii=False)
            self._append_transcript("SYSTEM", "Settings saved.")
        except Exception as exc:  # pylint: disable=broad-except
            self._append_transcript("SYSTEM", f"Could not save settings: {exc}")

    def _on_close(self) -> None:
        self._running = False
        self.destroy()


# ──────────────────────────────────────────────────────────────────────────────
# Colour palette  (Jarvis / Batcave HUD)
# ──────────────────────────────────────────────────────────────────────────────
BG_DEEP     = "#060d1a"   # main window background
BG_PANEL    = "#0a1628"   # card / panel background
NEON_CYAN   = "#00d4ff"   # primary accent – Jarvis electric-blue
NEON_BLUE   = "#0080ff"   # secondary accent
NEON_GREEN  = "#00ff88"   # online / success
NEON_AMBER  = "#ff9900"   # processing / warning
NEON_RED    = "#ff3366"   # error / danger
TEXT_BRIGHT = "#d0eeff"   # primary text colour
TEXT_DIM    = "#3a6080"   # disabled / secondary text
BORDER      = "#1a3050"   # subtle panel border
GRID_LINE   = "#0d1e30"   # background guide lines

# State → accent colour
STATE_COLOURS: dict[str, str] = {
    "idle":       TEXT_DIM,
    "listening":  NEON_CYAN,
    "processing": NEON_AMBER,
    "speaking":   NEON_GREEN,
    "error":      NEON_RED,
}

STATE_LABELS: dict[str, str] = {
    "idle":       "STANDBY",
    "listening":  "LISTENING",
    "processing": "PROCESSING",
    "speaking":   "SPEAKING",
    "error":      "ERROR",
}

STATE_SYMBOLS: dict[str, str] = {
    "idle":       "◈",
    "listening":  "◎",
    "processing": "⟳",
    "speaking":   "◉",
    "error":      "⚠",
}


# ──────────────────────────────────────────────────────────────────────────────
# Colour helpers
# ──────────────────────────────────────────────────────────────────────────────

def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def _blend(colour: str, alpha: float, bg: str = BG_DEEP) -> str:
    """Blend *colour* with *bg* at opacity *alpha* (0.0 – 1.0)."""
    cr, cg, cb = _hex_to_rgb(colour)
    br, bg_g, bb = _hex_to_rgb(bg)
    r = int(br + (cr - br) * alpha)
    g = int(bg_g + (cg - bg_g) * alpha)
    b = int(bb + (cb - bb) * alpha)
    return _rgb_to_hex(
        max(0, min(255, r)),
        max(0, min(255, g)),
        max(0, min(255, b)),
    )


# ──────────────────────────────────────────────────────────────────────────────
# HUD Canvas – animated pulse rings + audio bars + centre orb
# ──────────────────────────────────────────────────────────────────────────────

class HUDCanvas(tk.Canvas):
    """Animated Holographic-HUD canvas widget."""

    NUM_RINGS  = 4
    NUM_BARS   = 28
    BAR_WIDTH  = 4
    BAR_GAP    = 3
    MAX_BAR_H  = 44
    FPS        = 30

    def __init__(self, parent: tk.Widget, size: int = 300, **kwargs) -> None:
        super().__init__(
            parent,
            width=size, height=size,
            bg=BG_DEEP,
            highlightthickness=0,
            **kwargs,
        )
        self._size = size
        self._cx   = size // 2
        self._cy   = size // 2
        self._state = "idle"
        self._tick  = 0

        # Pulse-ring animation state
        self._rings: list[dict] = [
            {"phase": i / self.NUM_RINGS, "speed": 0.008}
            for i in range(self.NUM_RINGS)
        ]

        # Audio bar heights (0.0 – 1.0)
        self._bar_heights = [0.0] * self.NUM_BARS
        self._bar_targets  = [0.0] * self.NUM_BARS

        # Canvas item IDs
        self._ring_ids: list[int] = []
        self._bar_ids:  list[int] = []
        self._orb_id:   int = 0
        self._glow_id:  int = 0
        self._status_id: int = 0

        self._build_static_bg()
        self._build_rings()
        self._build_bars()
        self._build_orb()
        self._build_status_text()
        self._animate()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_static_bg(self) -> None:
        for r in (58, 98, 138):
            self.create_oval(
                self._cx - r, self._cy - r,
                self._cx + r, self._cy + r,
                outline=GRID_LINE, width=1,
            )
        self.create_line(
            self._cx, self._cy - 145, self._cx, self._cy + 145,
            fill=GRID_LINE, width=1,
        )
        self.create_line(
            self._cx - 145, self._cy, self._cx + 145, self._cy,
            fill=GRID_LINE, width=1,
        )
        # Corner tick marks
        for angle_deg in range(0, 360, 45):
            angle = math.radians(angle_deg)
            r_inner, r_outer = 136, 143
            x1 = self._cx + r_inner * math.cos(angle)
            y1 = self._cy + r_inner * math.sin(angle)
            x2 = self._cx + r_outer * math.cos(angle)
            y2 = self._cy + r_outer * math.sin(angle)
            self.create_line(x1, y1, x2, y2, fill=TEXT_DIM, width=1)

    def _build_rings(self) -> None:
        for _ in self._rings:
            oid = self.create_oval(
                self._cx, self._cy, self._cx, self._cy,
                outline=NEON_CYAN, width=2,
            )
            self._ring_ids.append(oid)

    def _build_bars(self) -> None:
        total_w = self.NUM_BARS * (self.BAR_WIDTH + self.BAR_GAP) - self.BAR_GAP
        x0 = self._cx - total_w // 2
        bar_base_y = self._cy + 52
        for i in range(self.NUM_BARS):
            x = x0 + i * (self.BAR_WIDTH + self.BAR_GAP)
            bid = self.create_rectangle(
                x, bar_base_y,
                x + self.BAR_WIDTH, bar_base_y,
                fill=NEON_CYAN, outline="",
            )
            self._bar_ids.append(bid)

    def _build_orb(self) -> None:
        r  = 22
        r2 = 32
        self._glow_id = self.create_oval(
            self._cx - r2, self._cy - r2,
            self._cx + r2, self._cy + r2,
            fill="", outline=NEON_CYAN, width=1,
        )
        self._orb_id = self.create_oval(
            self._cx - r, self._cy - r,
            self._cx + r, self._cy + r,
            fill=NEON_CYAN, outline="",
        )

    def _build_status_text(self) -> None:
        self._status_id = self.create_text(
            self._cx, self._cy + 98,
            text="◈  STANDBY",
            font=("Consolas", 10, "bold"),
            fill=TEXT_DIM,
        )

    # ── State ──────────────────────────────────────────────────────────────

    def set_state(self, state: str) -> None:
        self._state = state

    # ── Animation ──────────────────────────────────────────────────────────

    def _animate(self) -> None:
        self._tick += 1
        colour = STATE_COLOURS.get(self._state, TEXT_DIM)
        speed_mult = {
            "idle": 0.45,
            "listening": 1.8,
            "processing": 1.3,
            "speaking": 1.5,
            "error": 0.7,
        }.get(self._state, 1.0)

        # ── Pulse rings ───────────────────────────────────────────────────
        base_r, max_r = 36, 130
        for i, ring in enumerate(self._rings):
            ring["phase"] = (ring["phase"] + ring["speed"] * speed_mult) % 1.0
            phase  = ring["phase"]
            radius = base_r + phase * (max_r - base_r)
            alpha  = (1.0 - phase) * 0.75
            rc = _blend(colour, alpha)
            w  = max(1, int(2.5 * (1.0 - phase) + 0.5))
            self.coords(
                self._ring_ids[i],
                self._cx - radius, self._cy - radius,
                self._cx + radius, self._cy + radius,
            )
            self.itemconfig(self._ring_ids[i], outline=rc, width=w)

        # ── Centre orb pulse ─────────────────────────────────────────────
        orb_alpha = 0.25 + 0.4 * (0.5 + 0.5 * math.sin(self._tick * 0.06 * speed_mult))
        self.itemconfig(self._orb_id, fill=_blend(colour, orb_alpha, BG_DEEP))
        glow_alpha = 0.1 + 0.25 * (0.5 + 0.5 * math.sin(self._tick * 0.06 * speed_mult))
        self.itemconfig(self._glow_id, outline=_blend(colour, glow_alpha))

        # ── Audio bars ────────────────────────────────────────────────────
        total_w   = self.NUM_BARS * (self.BAR_WIDTH + self.BAR_GAP) - self.BAR_GAP
        x0_base   = self._cx - total_w // 2
        bar_base_y = self._cy + 52
        active    = self._state in ("listening", "speaking")

        for i in range(self.NUM_BARS):
            if active:
                if self._tick % 3 == i % 3:
                    self._bar_targets[i] = random.uniform(0.06, 1.0)
                self._bar_heights[i] += (
                    (self._bar_targets[i] - self._bar_heights[i]) * 0.35
                )
            else:
                self._bar_heights[i] *= 0.82
                if self._bar_heights[i] < 0.02:
                    self._bar_heights[i] = 0.0

            bh  = max(2, int(self._bar_heights[i] * self.MAX_BAR_H))
            x   = x0_base + i * (self.BAR_WIDTH + self.BAR_GAP)
            ba  = 0.35 + 0.65 * self._bar_heights[i]
            self.coords(
                self._bar_ids[i],
                x, bar_base_y - bh,
                x + self.BAR_WIDTH, bar_base_y,
            )
            self.itemconfig(self._bar_ids[i], fill=_blend(colour, ba))

        # ── Status text ───────────────────────────────────────────────────
        label  = STATE_LABELS.get(self._state, "")
        symbol = STATE_SYMBOLS.get(self._state, "◈")
        # Blink symbol while active
        if self._state in ("listening", "processing") and (self._tick // 10) % 2 == 1:
            symbol = " "
        self.itemconfig(
            self._status_id,
            text=f"{symbol}  {label}",
            fill=colour,
        )

        self.after(1000 // self.FPS, self._animate)


# ──────────────────────────────────────────────────────────────────────────────
# Main Application Window
# ──────────────────────────────────────────────────────────────────────────────

class AuraApp(ctk.CTk):
    """Main AURA desktop window with Jarvis-style HUD interface."""

    def __init__(self, config: dict) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        super().__init__()

        self._config   = config
        self._state    = "idle"
        self._muted    = False
        self._running  = False
        self._msg_queue: queue.Queue = queue.Queue()

        self.title("AURA – AI Voice Assistant")
        self.geometry("960x720")
        self.minsize(840, 640)
        self.configure(fg_color=BG_DEEP)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Try to set window icon
        _icon = os.path.join(os.path.dirname(__file__), "..", "assets", "aura.ico")
        if os.path.isfile(_icon):
            try:
                self.iconbitmap(_icon)
            except Exception:
                pass

        self._build_ui()
        self._start_aura()
        self._poll_queue()

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()
        self._build_main()
        self._build_footer()

    # ── Header ────────────────────────────────────────────────────────────

    def _build_header(self) -> None:
        hdr = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0, height=62)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_columnconfigure(1, weight=1)
        hdr.grid_propagate(False)

        ctk.CTkLabel(
            hdr,
            text="◈  A U R A",
            font=ctk.CTkFont(family="Consolas", size=22, weight="bold"),
            text_color=NEON_CYAN,
        ).grid(row=0, column=0, padx=20, pady=12, sticky="w")

        ctk.CTkLabel(
            hdr,
            text="AI VOICE ASSISTANT  ·  GAMER EDITION",
            font=ctk.CTkFont(family="Consolas", size=9),
            text_color=TEXT_DIM,
        ).grid(row=0, column=1)

        ctk.CTkLabel(
            hdr,
            text=f"v{__version__}",
            font=ctk.CTkFont(family="Consolas", size=9),
            text_color=TEXT_DIM,
        ).grid(row=0, column=2, padx=20, sticky="e")

        # Bottom neon border
        ctk.CTkFrame(self, fg_color=NEON_CYAN, height=1, corner_radius=0).grid(
            row=0, column=0, sticky="sew"
        )

    # ── Main area ─────────────────────────────────────────────────────────

    def _build_main(self) -> None:
        main = ctk.CTkFrame(self, fg_color=BG_DEEP, corner_radius=0)
        main.grid(row=1, column=0, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_columnconfigure(1, weight=2)
        main.grid_rowconfigure(0, weight=1)
        self._build_left_panel(main)
        self._build_right_panel(main)

    def _build_left_panel(self, parent: ctk.CTkFrame) -> None:
        left = ctk.CTkFrame(parent, fg_color=BG_DEEP, corner_radius=0)
        left.grid(row=0, column=0, sticky="nsew", padx=(16, 8), pady=16)
        left.grid_columnconfigure(0, weight=1)

        # HUD canvas
        canvas_wrap = ctk.CTkFrame(left, fg_color=BG_PANEL, corner_radius=12)
        canvas_wrap.grid(row=0, column=0, sticky="n")
        self._hud = HUDCanvas(canvas_wrap, size=300)
        self._hud.pack(padx=10, pady=10)

        ctk.CTkLabel(
            left,
            text="─── SYSTEM STATUS ───",
            font=ctk.CTkFont(family="Consolas", size=9),
            text_color=TEXT_DIM,
        ).grid(row=1, column=0, pady=(10, 4))

        # Status mini-grid
        sf = ctk.CTkFrame(left, fg_color=BG_PANEL, corner_radius=8)
        sf.grid(row=2, column=0, sticky="ew")
        sf.grid_columnconfigure(1, weight=1)

        self._status_vals: dict[str, ctk.CTkLabel] = {}
        rows = [
            ("VOICE ENGINE", "Whisper"),
            ("TTS ENGINE",   "pyttsx3"),
            ("OBS",          "● connecting…"),
            ("TWITCH",       "● connecting…"),
        ]
        for i, (key, val) in enumerate(rows):
            ctk.CTkLabel(
                sf, text=key,
                font=ctk.CTkFont(family="Consolas", size=9),
                text_color=TEXT_DIM, anchor="w",
            ).grid(row=i, column=0, padx=(12, 4), pady=3, sticky="w")
            lbl = ctk.CTkLabel(
                sf, text=val,
                font=ctk.CTkFont(family="Consolas", size=9, weight="bold"),
                text_color=NEON_CYAN, anchor="w",
            )
            lbl.grid(row=i, column=1, padx=(0, 12), pady=3, sticky="w")
            self._status_vals[key] = lbl

    def _build_right_panel(self, parent: ctk.CTkFrame) -> None:
        right = ctk.CTkFrame(parent, fg_color=BG_DEEP, corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=16)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(3, weight=1)

        # Command received
        self._cmd_label = self._info_card(
            right, row=0,
            header="COMMAND RECEIVED",
            initial='Waiting for voice input…',
            text_colour=NEON_CYAN,
            wraplength=500,
            font_size=16,
        )

        # AURA response
        self._resp_label = self._info_card(
            right, row=1,
            header="AURA RESPONSE",
            initial="AURA is online. Ready to help you stream!",
            text_colour=NEON_GREEN,
            wraplength=500,
            font_size=13,
        )

        # Mission log header
        ctk.CTkLabel(
            right,
            text="─── MISSION LOG ───",
            font=ctk.CTkFont(family="Consolas", size=9),
            text_color=TEXT_DIM,
            anchor="w",
        ).grid(row=2, column=0, pady=(6, 2), sticky="w")

        # Scrollable log
        self._log_box = ctk.CTkTextbox(
            right,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=BG_PANEL,
            text_color=TEXT_BRIGHT,
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
            wrap="word",
        )
        self._log_box.grid(row=3, column=0, sticky="nsew")
        self._log_box.configure(state="disabled")

    @staticmethod
    def _info_card(
        parent: ctk.CTkFrame,
        row: int,
        header: str,
        initial: str,
        text_colour: str,
        wraplength: int = 460,
        font_size: int = 14,
    ) -> ctk.CTkLabel:
        """Create a labelled HUD card and return the value label."""
        card = ctk.CTkFrame(
            parent, fg_color=BG_PANEL, corner_radius=10,
            border_width=1, border_color=BORDER,
        )
        card.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            card, text=header,
            font=ctk.CTkFont(family="Consolas", size=9),
            text_color=TEXT_DIM, anchor="w",
        ).grid(row=0, column=0, padx=12, pady=(8, 0), sticky="w")
        val_lbl = ctk.CTkLabel(
            card, text=initial,
            font=ctk.CTkFont(family="Consolas", size=font_size, weight="bold"),
            text_color=text_colour, anchor="w",
            wraplength=wraplength,
        )
        val_lbl.grid(row=1, column=0, padx=12, pady=(4, 12), sticky="ew")
        return val_lbl

    # ── Footer ────────────────────────────────────────────────────────────

    def _build_footer(self) -> None:
        ftr = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0, height=66)
        ftr.grid(row=2, column=0, sticky="ew")
        ftr.grid_columnconfigure(3, weight=1)
        ftr.grid_propagate(False)

        # Top border
        ctk.CTkFrame(ftr, fg_color=BORDER, height=1, corner_radius=0).place(
            relx=0, rely=0, relwidth=1
        )

        _btn = dict(
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            width=130, height=38, corner_radius=6,
        )

        self._start_btn = ctk.CTkButton(
            ftr, text="▶  START", command=self._on_start,
            fg_color="#0d2a45", hover_color="#1a4a70",
            text_color=NEON_CYAN, border_width=1, border_color=NEON_CYAN,
            **_btn,
        )
        self._start_btn.grid(row=0, column=0, padx=(16, 6), pady=14)

        self._stop_btn = ctk.CTkButton(
            ftr, text="■  STOP", command=self._on_stop,
            fg_color="#2a0d1a", hover_color="#4a1a2a",
            text_color=NEON_RED, border_width=1, border_color=NEON_RED,
            state="disabled", **_btn,
        )
        self._stop_btn.grid(row=0, column=1, padx=6, pady=14)

        self._mute_btn = ctk.CTkButton(
            ftr, text="🔇  MUTE", command=self._on_mute_toggle,
            fg_color="#0d1a2a", hover_color="#1a3040",
            text_color=TEXT_DIM, border_width=1, border_color=BORDER,
            **_btn,
        )
        self._mute_btn.grid(row=0, column=2, padx=6, pady=14)

        ctk.CTkLabel(
            ftr,
            text='Say  "help"  for available commands',
            font=ctk.CTkFont(family="Consolas", size=9),
            text_color=TEXT_DIM,
        ).grid(row=0, column=3, padx=16, sticky="e")

    # ── Internal state ────────────────────────────────────────────────────

    def _set_state(self, state: str) -> None:
        self._state = state
        self._hud.set_state(state)

    # ── Voice loop (background thread) ───────────────────────────────────

    def _start_aura(self) -> None:
        self._running = True
        threading.Thread(
            target=self._voice_loop, daemon=True, name="AURA-VoiceLoop"
        ).start()
        self._set_state("listening")
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")

    def _voice_loop(self) -> None:
        """Background thread: run the voice assistant loop."""
        try:
            from core.session import create_session  # noqa: PLC0415
            from core.onboarding.onboarding_storage import load_profile  # noqa: PLC0415
            from voice.wake_word import WakeWordDetector  # noqa: PLC0415

            profile = load_profile()
            session = create_session(self._config, profile=profile)
            stt = session.stt
            tts = session.tts
            parser = session.parser
            handler = session.handler
            wake_detector = WakeWordDetector(self._config)

            if session.events is not None:
                session.events.start()
        except Exception as exc:  # pylint: disable=broad-except
            self._post("log", f"[ERROR] Initialisation failed: {exc}\n")
            self._post("state", "error")
            return

        self._post("log", "[SYSTEM] AURA initialised. Listening for commands.\n")
        self._post("response", "AURA is online. Ready to help you stream!")
        tts.speak("AURA is online. Ready to help you stream!")
        if wake_detector.is_enabled:
            self._post("log", "[SYSTEM] Wake word detection active — say 'AURA'.\n")

        while self._running:
            try:
                if self._muted:
                    time.sleep(0.1)
                    continue

                # ── Phase 1: Wake word (low-CPU idle) ────────────────────
                if wake_detector.is_enabled:
                    self._post("state", "idle")
                    if not wake_detector.wait_for_wake_word(timeout=5.0):
                        continue  # No wake word — keep waiting
                    self._post("log", "[SYSTEM] Wake word detected!\n")

                # ── Phase 2: Full command recognition ────────────────────
                self._post("state", "listening")
                self._post("log", "[AURA] Listening…\n")
                text = stt.listen()

                if not text:
                    continue

                self._post("command", text)
                self._post("log", f"[HEARD] {text}\n")
                self._post("state", "processing")

                # ── Phase 3: Parse / AI reasoning ────────────────────────
                if session.decision_engine is not None:
                    response = session.decision_engine.process(text)
                else:
                    command = parser.parse(text)
                    if command is None:
                        response = "Sorry, I didn't understand that command."
                    else:
                        self._post("log", f"[COMMAND] {command.get('type', '?')}\n")
                        response = handler.execute(command, raw_text=text)

                self._post("response", response)
                self._post("log", f"[AURA] {response}\n")
                self._post("state", "speaking")
                tts.speak(response)

            except Exception as exc:  # pylint: disable=broad-except
                logger.error("Voice loop error: %s", exc, exc_info=True)
                self._post("log", f"[ERROR] {exc}\n")

        self._post("state", "idle")
        self._post("log", "[SYSTEM] AURA stopped.\n")

    def _post(self, kind: str, data: str) -> None:
        self._msg_queue.put((kind, data))

    # ── Queue polling (main thread) ───────────────────────────────────────

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, data = self._msg_queue.get_nowait()
                if kind == "state":
                    self._set_state(data)
                elif kind == "command":
                    self._cmd_label.configure(text=f'"{data}"')
                elif kind == "response":
                    self._resp_label.configure(text=data)
                elif kind == "log":
                    self._append_log(data)
        except queue.Empty:
            pass
        self.after(50, self._poll_queue)

    def _append_log(self, text: str) -> None:
        self._log_box.configure(state="normal")
        ts = time.strftime("%H:%M:%S")
        self._log_box.insert("end", f"[{ts}] {text}")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    # ── Button callbacks ──────────────────────────────────────────────────

    def _on_start(self) -> None:
        if not self._running:
            self._start_aura()

    def _on_stop(self) -> None:
        self._running = False
        self._set_state("idle")
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self._append_log("[SYSTEM] AURA stopped by user.\n")

    def _on_mute_toggle(self) -> None:
        self._muted = not self._muted
        if self._muted:
            self._mute_btn.configure(
                text="🔊  UNMUTE",
                text_color=NEON_AMBER,
                border_color=NEON_AMBER,
            )
            self._append_log("[SYSTEM] Microphone muted.\n")
        else:
            self._mute_btn.configure(
                text="🔇  MUTE",
                text_color=TEXT_DIM,
                border_color=BORDER,
            )
            self._append_log("[SYSTEM] Microphone unmuted.\n")

    def _on_close(self) -> None:
        self._running = False
        self.destroy()
