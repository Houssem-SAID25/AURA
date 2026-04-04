"""
assets/make_icon.py
===================
Generates ``aura.ico`` for the Windows EXE using Pillow.

The icon is **circular** (transparent outside the disc, like Steam's icon):
a deep-navy filled circle with a neon-cyan outer ring, cross-hair tick marks,
a central glowing dot, and "AURA" lettering at the bottom arc.

Run once before building with PyInstaller:

    python assets/make_icon.py
"""

import os

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    raise SystemExit("Pillow is required: pip install Pillow")

SIZES = [16, 32, 48, 64, 128, 256]

# Colour palette  (matches gui/app.py)
TRANSPARENT = (0,   0,   0,   0)    # fully transparent
NAVY        = (6,  13,  26, 255)    # deep navy  #060D1A
CYAN        = (0, 212, 255, 255)    # neon cyan  #00D4FF
CYAN_DIM    = (0, 212, 255, 140)    # semi-transparent cyan (glow fill)


def _make_frame(size: int) -> Image.Image:
    # Start fully transparent so corners are empty (circular appearance)
    img  = Image.new("RGBA", (size, size), TRANSPARENT)
    draw = ImageDraw.Draw(img)

    cx = cy = size // 2
    # Radius of the circular "canvas" – fills ~96 % of the tile
    r_disc = int(size * 0.48)

    # ── 1. Filled navy disc (the circle background) ──────────────────────────
    draw.ellipse(
        [cx - r_disc, cy - r_disc, cx + r_disc, cy + r_disc],
        fill=NAVY,
    )

    # ── 2. Outer neon-cyan ring ───────────────────────────────────────────────
    ring_w = max(1, size // 20)
    r_ring = int(size * 0.42)
    draw.ellipse(
        [cx - r_ring, cy - r_ring, cx + r_ring, cy + r_ring],
        outline=CYAN,
        width=ring_w,
    )

    # ── 3. Cross-hair tick marks (top / right / bottom / left of ring) ────────
    tick = max(1, size // 10)
    lw   = max(1, size // 36)
    draw.line([(cx, cy - r_ring - tick), (cx, cy - r_ring + tick)], fill=CYAN, width=lw)
    draw.line([(cx, cy + r_ring - tick), (cx, cy + r_ring + tick)], fill=CYAN, width=lw)
    draw.line([(cx - r_ring - tick, cy), (cx - r_ring + tick, cy)], fill=CYAN, width=lw)
    draw.line([(cx + r_ring - tick, cy), (cx + r_ring + tick, cy)], fill=CYAN, width=lw)

    # ── 4. Central glowing dot ────────────────────────────────────────────────
    # Outer soft glow
    r_glow = max(3, int(size * 0.16))
    draw.ellipse(
        [cx - r_glow, cy - r_glow, cx + r_glow, cy + r_glow],
        fill=CYAN_DIM,
    )
    # Bright core
    r_dot = max(2, int(size * 0.09))
    draw.ellipse(
        [cx - r_dot, cy - r_dot, cx + r_dot, cy + r_dot],
        fill=CYAN,
    )

    # ── 5. "AURA" text (only at larger sizes where it's legible) ──────────────
    if size >= 64:
        font_size = max(8, size // 7)
        font = None
        # Try common system/CI fonts in order of preference.
        # On Windows builds Arial is always present; on Linux CI runners
        # DejaVu or Liberation Sans are typically available.
        # Falls back to Pillow's built-in raster font if none are found.
        for name in ("arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf",
                     "FreeSansBold.ttf", "LiberationSans-Bold.ttf"):
            try:
                font = ImageFont.truetype(name, font_size)
                break
            except (IOError, OSError):
                continue
        if font is None:
            font = ImageFont.load_default()

        text = "AURA"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        # Position text near the bottom of the disc
        tx = cx - tw // 2
        ty = cy + int(size * 0.18)
        draw.text((tx, ty), text, fill=CYAN, font=font)

    return img


def _pack_ico(frames: list) -> bytes:
    """Pack RGBA PIL images into a multi-resolution ICO byte string.

    Pillow's built-in ICO writer only embeds one resolution; this function
    builds the ICO container manually so all sizes are present (matching the
    approach used by icon tools like rcedit/ResourceHacker).
    """
    import io
    import struct

    n = len(frames)
    # ICONDIR header: reserved=0, type=1 (ICO), count=n
    header = struct.pack("<HHH", 0, 1, n)

    # Encode each frame as PNG inside the ICO container
    raw_images: list[bytes] = []
    for img in frames:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        raw_images.append(buf.getvalue())

    # ICONDIRENTRY records (16 bytes each)
    # Entries start right after the ICONDIR header + all ICONDIRENTRY records
    offset = 6 + n * 16
    entries = b""
    for img, raw in zip(frames, raw_images):
        w, h = img.size
        bw = w if w < 256 else 0   # 0 means 256 in ICO spec
        bh = h if h < 256 else 0
        entries += struct.pack("<BBBBHHII", bw, bh, 0, 0, 1, 32, len(raw), offset)
        offset += len(raw)

    return header + entries + b"".join(raw_images)


def main() -> None:
    frames = [_make_frame(s) for s in SIZES]
    out = os.path.join(os.path.dirname(__file__), "aura.ico")
    with open(out, "wb") as fh:
        fh.write(_pack_ico(frames))
    print(f"Icon saved → {out}  ({os.path.getsize(out)} bytes, {len(SIZES)} resolutions)")


if __name__ == "__main__":
    main()
