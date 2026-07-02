"""Image loading that copes with phone (Android/iOS) and DSLR output.

Handles JPEG/PNG/TIFF/BMP/WebP, HEIC/HEIF when pillow-heif is present,
and applies the EXIF orientation tag so portrait phone shots come in upright.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps

try:  # iOS photos are commonly HEIC
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF_SUPPORTED = True
except ImportError:
    HEIF_SUPPORTED = False

SUPPORTED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"]
if HEIF_SUPPORTED:
    SUPPORTED_EXTENSIONS += [".heic", ".heif"]

# Cap the working resolution: segmentation runs on 320px internally anyway and
# 24MP DSLR frames just waste memory. Keep plenty for a 300-DPI passport crop.
MAX_WORKING_DIM = 3000


def file_dialog_filter() -> str:
    exts = " ".join(f"*{e}" for e in SUPPORTED_EXTENSIONS)
    return f"Images ({exts})"


def load_image(path: str | Path) -> Image.Image:
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    if max(img.size) > MAX_WORKING_DIM:
        img.thumbnail((MAX_WORKING_DIM, MAX_WORKING_DIM), Image.LANCZOS)
    return img
