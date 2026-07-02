"""Background removal with a local U^2-Net human-segmentation ONNX model.

The model file (~176 MB) is fetched once by rembg into ~/.u2net and used
offline afterwards. Everything runs on-device via onnxruntime CPU.
"""
from __future__ import annotations

import threading

import numpy as np
from PIL import Image, ImageFilter

_session = None
_session_lock = threading.Lock()

MODEL_NAME = "u2net_human_seg"


def get_session():
    global _session
    if _session is None:
        # Double-checked lock: the web server handles requests on a thread
        # pool, and two concurrent first requests must not both build the
        # ~176 MB ONNX session (or race the one-time model download).
        with _session_lock:
            if _session is None:
                from rembg import new_session

                _session = new_session(MODEL_NAME)
    return _session


def remove_background(img: Image.Image) -> Image.Image:
    """Return an RGBA image of the subject with transparent background."""
    from rembg import remove

    cutout = remove(img.convert("RGB"), session=get_session())

    # Soften the matte edge a touch so hair doesn't look razor-cut.
    r, g, b, a = cutout.split()
    a = a.filter(ImageFilter.GaussianBlur(1.2))
    # Re-harden interior: anything that was fully opaque stays fully opaque.
    a_np = np.asarray(a, dtype=np.float32)
    a_np = np.clip((a_np - 8.0) * (255.0 / 239.0), 0, 255).astype(np.uint8)
    cutout.putalpha(Image.fromarray(a_np))
    return cutout


def composite_on_color(cutout: Image.Image, color: tuple[int, int, int] | None) -> Image.Image:
    """Place an RGBA cutout on a solid color. color=None keeps transparency."""
    if color is None:
        return cutout.copy()
    bg = Image.new("RGBA", cutout.size, (*color, 255))
    bg.alpha_composite(cutout)
    return bg
