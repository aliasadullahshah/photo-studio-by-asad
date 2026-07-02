"""Overlay a suit/blazer template on a portrait.

Templates are RGBA PNGs in assets/suits. Convention: the neck opening is
centered at x = 50% of the template width, y = NECK_ANCHOR_Y of its height,
and the template is designed to be scaled to ~3.1x the detected face width.
Users can drop their own PNGs into the folder; the same convention applies.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PIL import Image

from .face import FaceBox

NECK_ANCHOR_Y = 0.075  # fraction of template height where the collar opening sits
WIDTH_PER_FACE = 3.1   # template width relative to detected face width


def assets_dir() -> Path:
    if getattr(sys, "frozen", False):  # PyInstaller bundle
        return Path(sys._MEIPASS) / "assets" / "suits"
    return Path(__file__).resolve().parent.parent.parent / "assets" / "suits"


def user_suits_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "Photo Studio by Asad" / "suits"


def list_suits() -> list[Path]:
    suits: dict[str, Path] = {}
    for d in (assets_dir(), user_suits_dir()):
        if d.is_dir():
            for p in sorted(d.glob("*.png")):
                suits[p.stem] = p  # user template overrides bundled same-name one
    return [suits[k] for k in sorted(suits)]


def add_custom_suit(src: str | Path) -> Path:
    """Import a transparent suit PNG into the user template folder."""
    src = Path(src)
    img = Image.open(src)
    if img.mode != "RGBA":
        raise ValueError(
            "The image has no transparency. Use a PNG with a transparent "
            "background around the suit (collar centered near the top).")
    dst_dir = user_suits_dir()
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / (src.stem + ".png")
    img.save(dst)
    return dst


def apply_suit(
    photo: Image.Image,
    face: FaceBox,
    suit_path: str | Path,
    scale: float = 1.0,
    dx: int = 0,
    dy: int = 0,
) -> Image.Image:
    """Composite the suit under the chin. photo must be RGBA.

    scale/dx/dy are user fine-tuning controls (1.0 / 0 / 0 = automatic fit).
    dx/dy are in units of 1/100 of the photo width/height.
    """
    suit = Image.open(suit_path).convert("RGBA")

    target_w = int(round(face.w * WIDTH_PER_FACE * scale))
    target_h = int(round(suit.height * target_w / suit.width))
    suit = suit.resize((target_w, target_h), Image.LANCZOS)

    # Anchor the collar just above the chin so the shirt tucks under the jaw.
    anchor_x = face.cx + dx * photo.width / 100
    anchor_y = face.chin_y + face.h * 0.04 + dy * photo.height / 100
    left = int(round(anchor_x - target_w / 2))
    top = int(round(anchor_y - target_h * NECK_ANCHOR_Y))

    out = photo.convert("RGBA")
    # paste with the suit's own alpha as mask tolerates the template
    # overhanging the photo edges (alpha_composite would not).
    out.paste(suit, (left, top), suit)
    return out
