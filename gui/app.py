"""
gui/app.py
==========
AURA desktop GUI — Jarvis / Batcave AI aesthetic.

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

import customtkinter as ctk
import tkinter as tk

from version import __version__

logger = logging.getLogger("AURA.GUI")

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
