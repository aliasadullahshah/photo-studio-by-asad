"""One-click photo enhancements: lighting fix, skin smoothing, face brighten.

All functions accept RGB or RGBA PIL images; alpha is preserved untouched so
they can run on background-removed cutouts without disturbing the matte.
Face-targeted operations take the FaceBox detected earlier in the pipeline
and blend through a feathered elliptical mask so edits never show a seam.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from .face import FaceBox


def _split(img: Image.Image) -> tuple[np.ndarray, np.ndarray | None]:
    if img.mode == "RGBA":
        arr = np.asarray(img)
        return arr[:, :, :3].copy(), arr[:, :, 3].copy()
    return np.asarray(img.convert("RGB")).copy(), None


def _join(rgb: np.ndarray, alpha: np.ndarray | None) -> Image.Image:
    if alpha is None:
        return Image.fromarray(rgb, "RGB")
    return Image.fromarray(np.dstack([rgb, alpha]), "RGBA")


def _face_mask(shape: tuple[int, int], face: FaceBox) -> np.ndarray:
    """Feathered elliptical mask (float 0..1) over the face incl. forehead/chin."""
    h, w = shape
    mask = np.zeros((h, w), dtype=np.uint8)
    center = (int(face.cx), int(face.y + face.h * 0.45))
    axes = (int(face.w * 0.62), int(face.h * 0.85))
    cv2.ellipse(mask, center, axes, 0, 0, 360, 255, -1)
    feather = max(3, int(face.w * 0.12)) | 1  # odd kernel
    mask = cv2.GaussianBlur(mask, (feather, feather), 0)
    return mask.astype(np.float32) / 255.0


def _blend(base: np.ndarray, edited: np.ndarray, mask: np.ndarray,
           strength: float) -> np.ndarray:
    m = (mask * strength)[:, :, None]
    out = base.astype(np.float32) * (1 - m) + edited.astype(np.float32) * m
    return np.clip(out, 0, 255).astype(np.uint8)


def fix_light(img: Image.Image) -> Image.Image:
    """Auto lighting: adaptive contrast (CLAHE) + gentle exposure correction.

    Statistics come from the subject only (alpha > 0), so a transparent or
    already-replaced background never skews the correction.
    """
    rgb, alpha = _split(img)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    l_chan = lab[:, :, 0]

    clahe = cv2.createCLAHE(clipLimit=1.2, tileGridSize=(8, 8))
    # Half-strength blend: full CLAHE punches up freckles and skin noise.
    l_eq = cv2.addWeighted(clahe.apply(l_chan), 0.5, l_chan, 0.5, 0)

    subject = alpha > 16 if alpha is not None else np.ones(l_chan.shape, bool)
    mean_l = float(l_eq[subject].mean()) if subject.any() else 128.0
    # Pull the subject's mean luminance toward a pleasant exposure (~135),
    # but never by more than a mild gamma so it can't blow out.
    gamma = np.clip(np.log(135 / 255) / np.log(max(mean_l, 1) / 255), 0.8, 1.25)
    lut = (np.linspace(0, 1, 256) ** (1 / gamma) * 255).astype(np.uint8)
    lab[:, :, 0] = lut[l_eq]

    out = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    return _join(out, alpha)


def smooth_skin(img: Image.Image, face: FaceBox, strength: float = 0.75) -> Image.Image:
    """Remove scars, spots and color blotches (redness/blueness) on the face.

    Edge-preserving bilateral filtering evens out skin texture and local
    discoloration while eyes, brows and the face outline stay crisp; a median
    pass on the color channels clears larger bruise-like patches.
    """
    rgb, alpha = _split(img)
    d = max(5, int(face.w * 0.045)) | 1
    smoothed = cv2.bilateralFilter(rgb, d, 45, d * 2)
    smoothed = cv2.bilateralFilter(smoothed, d, 35, d * 2)

    # Even out larger discolored patches in the chroma channels only, so
    # brightness detail (dimples, nose shading) survives.
    lab = cv2.cvtColor(smoothed, cv2.COLOR_RGB2LAB)
    k = max(5, int(face.w * 0.06)) | 1
    lab[:, :, 1] = cv2.medianBlur(lab[:, :, 1], k)
    lab[:, :, 2] = cv2.medianBlur(lab[:, :, 2], k)
    smoothed = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)

    out = _blend(rgb, smoothed, _face_mask(rgb.shape[:2], face), strength)
    return _join(out, alpha)


def brighten_face(img: Image.Image, face: FaceBox, amount: float = 0.16) -> Image.Image:
    """Lift the face luminance through a feathered mask (no hard edges)."""
    rgb, alpha = _split(img)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    lab[:, :, 0] = np.clip(lab[:, :, 0] * (1 + amount), 0, 255)
    brightened = cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2RGB)
    out = _blend(rgb, brightened, _face_mask(rgb.shape[:2], face), 1.0)
    return _join(out, alpha)


def apply_enhancements(
    img: Image.Image,
    face: FaceBox | None,
    do_fix_light: bool = False,
    do_smooth_skin: bool = False,
    do_brighten_face: bool = False,
) -> Image.Image:
    """Apply the selected enhancements in a sensible order."""
    out = img
    if do_fix_light:
        out = fix_light(out)
    if do_smooth_skin and face is not None:
        out = smooth_skin(out, face)
    if do_brighten_face and face is not None:
        out = brighten_face(out, face)
    return out
