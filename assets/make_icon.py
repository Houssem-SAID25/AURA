"""
assets/make_icon.py
===================
Generates ``aura.ico`` for the Windows EXE using Pillow.

Run once before building with PyInstaller:

    python assets/make_icon.py
"""

import os

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    raise SystemExit("Pillow is required: pip install Pillow")

SIZES = [16, 32,48, 64, 128, 256]
BG   = (6, 13, 26, 255)        # deep navy
CYAN = (0, 212, 255, 255)       # neon cyan


def _make_frame(size: int) -> Image.Image:
    img  = Image.new("RGBA", (size, size), BG)
    draw = ImageDraw.Draw(img)
    cx = cy = size // 2
    r = int(size * 0.38)

    # Outer ring
    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        outline=CYAN,
        width=max(1, size // 32),
    )

    # Inner dot
    rd = max(2, int(size * 0.18))
    draw.ellipse(
        [cx - rd, cy - rd, cx + rd, cy + rd],
        fill=CYAN,
    )

    # Cross-hair marks (top, right, bottom, left)
    tick = max(1, size // 12)
    lw   = max(1, size // 40)
    draw.line([(cx, cy - r - tick), (cx, cy - r + tick)], fill=CYAN, width=lw)
    draw.line([(cx, cy + r - tick), (cx, cy + r + tick)], fill=CYAN, width=lw)
    draw.line([(cx - r - tick, cy), (cx - r + tick, cy)], fill=CYAN, width=lw)
    draw.line([(cx + r - tick, cy), (cx + r + tick, cy)], fill=CYAN, width=lw)

    return img


def main() -> None:
    frames = [_make_frame(s) for s in SIZES]
    out = os.path.join(os.path.dirname(__file__), "aura.ico")
    frames[0].save(
        out,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=frames[1:],
    )
    print(f"Icon saved → {out}")


if __name__ == "__main__":
    main()
