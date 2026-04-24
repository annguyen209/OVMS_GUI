"""
icon.py - App icon generator.

Creates a multi-resolution ICO file at assets/icon.ico using Pillow.
The icon is a dark square with a blue left accent bar and "OV" monogram.
Call build_icon() once at startup; it skips regeneration if the file exists.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ICON_PATH = Path(__file__).parent.parent / "assets" / "icon.ico"

# Enterprise palette
_BG      = (27,  31,  35)    # #1b1f23  near-black
_BLUE    = (0,  120, 212)    # #0078d4  Microsoft blue
_WHITE   = (248, 250, 252)   # #f8fafc
_GRAY    = (107, 114, 128)   # #6b7280


def _draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    pad    = max(1, size // 16)
    radius = max(2, size // 10)

    # Background rounded rect
    d.rounded_rectangle(
        [pad, pad, size - pad - 1, size - pad - 1],
        radius=radius,
        fill=_BG,
    )

    # Blue accent bar (left edge, ~18% width)
    bar_w = max(2, size // 6)
    d.rounded_rectangle(
        [pad, pad, pad + bar_w, size - pad - 1],
        radius=radius,
        fill=_BLUE,
    )

    # "OV" monogram — pick font size relative to icon size
    fs = max(6, int(size * 0.38))
    try:
        font = ImageFont.truetype("segoeui.ttf", fs)
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", fs)
        except Exception:
            font = ImageFont.load_default()

    text  = "OV"
    bbox  = d.textbbox((0, 0), text, font=font)
    tw    = bbox[2] - bbox[0]
    th    = bbox[3] - bbox[1]

    # Centre in the area to the right of the accent bar
    right_start = pad + bar_w + max(1, size // 16)
    right_width = size - pad - right_start
    tx = right_start + (right_width - tw) // 2
    ty = pad + (size - pad * 2 - th) // 2

    d.text((tx, ty), text, fill=_WHITE, font=font)

    # Small blue dot below text (visual accent)
    dot_r = max(1, size // 20)
    dot_x = tx + tw // 2
    dot_y = ty + th + dot_r + max(1, size // 20)
    if dot_y + dot_r < size - pad:
        d.ellipse(
            [dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r],
            fill=_BLUE,
        )

    return img


def build_icon(force: bool = False) -> Path:
    """
    Build the .ico file at ICON_PATH. Returns the path.
    Skips if the file already exists unless force=True.
    """
    ICON_PATH.parent.mkdir(parents=True, exist_ok=True)

    if ICON_PATH.exists() and not force:
        return ICON_PATH

    sizes   = [16, 24, 32, 48, 64, 128, 256]
    frames  = [_draw_icon(s) for s in sizes]

    # Save largest first; append remaining sizes
    frames[-1].save(
        ICON_PATH,
        format="ICO",
        append_images=frames[:-1],
    )
    return ICON_PATH


def get_tray_image(size: int = 64) -> Image.Image:
    """Return a PIL Image suitable for the system tray icon."""
    return _draw_icon(size)
