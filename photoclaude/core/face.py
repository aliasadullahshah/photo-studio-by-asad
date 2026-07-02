"""Face detection and passport-style auto framing (OpenCV Haar cascade)."""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

# ICAO-style framing for a 35x45 mm photo: head height ~70% of photo height,
# eye line ~45% from the top.
PHOTO_ASPECT = 35 / 45  # width / height
HEAD_FRACTION = 0.70
HEAD_TOP_FRACTION = 0.10  # gap above crown

_cascade = None


@dataclass
class FaceBox:
    x: int
    y: int
    w: int
    h: int

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def chin_y(self) -> float:
        # Haar box ends around the mouth/chin; nudge down slightly.
        return self.y + self.h * 1.08

    @property
    def crown_y(self) -> float:
        # Haar box starts near the eyebrows/forehead; hair sits above it.
        return self.y - self.h * 0.45


def _get_cascade():
    global _cascade
    if _cascade is None:
        _cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
    return _cascade


def detect_face(img: Image.Image) -> FaceBox | None:
    gray = cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
    min_side = max(60, int(min(img.size) * 0.1))
    # Raw grayscale first: equalizeHist wrecks detection on bright studio
    # shots, but rescues genuinely low-contrast photos — so it is the fallback.
    for g in (gray, cv2.equalizeHist(gray)):
        faces = _get_cascade().detectMultiScale(
            g, scaleFactor=1.08, minNeighbors=6, minSize=(min_side, min_side)
        )
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])  # largest face
            return FaceBox(int(x), int(y), int(w), int(h))
    return None


def passport_crop_box(img: Image.Image, face: FaceBox) -> tuple[int, int, int, int]:
    """Crop rectangle (left, top, right, bottom) framing the face per ICAO ratios.

    May extend past the image; callers should pad (see crop_with_padding).
    """
    head_h = face.chin_y - face.crown_y
    crop_h = head_h / HEAD_FRACTION
    crop_w = crop_h * PHOTO_ASPECT
    top = face.crown_y - crop_h * HEAD_TOP_FRACTION
    left = face.cx - crop_w / 2
    return (int(round(left)), int(round(top)),
            int(round(left + crop_w)), int(round(top + crop_h)))


def crop_with_padding(img: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    """Crop, padding with edge-replicated pixels where the box leaves the image."""
    left, top, right, bottom = box
    w, h = img.size
    pad_l = max(0, -left)
    pad_t = max(0, -top)
    pad_r = max(0, right - w)
    pad_b = max(0, bottom - h)
    if pad_l or pad_t or pad_r or pad_b:
        arr = np.asarray(img)
        arr = np.pad(arr, ((pad_t, pad_b), (pad_l, pad_r), (0, 0)), mode="edge")
        img = Image.fromarray(arr)
        left += pad_l
        right += pad_l
        top += pad_t
        bottom += pad_t
    return img.crop((left, top, right, bottom))
