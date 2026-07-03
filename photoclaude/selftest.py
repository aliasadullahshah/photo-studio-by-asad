"""Headless end-to-end self-test of the full pipeline.

Run automatically by main.py when PHOTOSTUDIO_SELFTEST=1 — used to verify a
frozen (PyInstaller) build actually works: bundled sample photo -> face
detection -> passport crop -> AI background removal -> suit overlay -> sheet.
Exits 0 on success, 1 with a traceback on any failure.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path


def _sample_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "assets" / "sample.jpg"
    return Path(__file__).resolve().parent.parent / "webapp" / "static" / "sample.jpg"


def run() -> int:
    # Windowed (console=False) frozen builds have no usable stdout — mirror
    # everything to a log file so the result is inspectable either way.
    import os
    import tempfile

    log_path = os.environ.get(
        "PHOTOSTUDIO_SELFTEST_LOG",
        str(Path(tempfile.gettempdir()) / "photostudio_selftest.log"))
    log = open(log_path, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stdout is None or getattr(sys.stdout, "fileno", None) is None:
        sys.stdout = sys.stderr = log
    else:
        class _Tee:
            def write(self, s):
                sys.__stdout__.write(s)
                log.write(s)

            def flush(self):
                sys.__stdout__.flush()
                log.flush()

        sys.stdout = sys.stderr = _Tee()
    try:
        from photoclaude.core import (
            background, enhance, face as face_mod, imageio, sheet, suit)

        img = imageio.load_image(_sample_path())
        print(f"1. sample loaded {img.size}")

        face = face_mod.detect_face(img)
        assert face is not None, "face not detected in sample"
        print(f"2. face detected w={face.w}")

        box = face_mod.passport_crop_box(img, face)
        crop = face_mod.crop_with_padding(img.convert("RGB"), box)
        fc = face_mod.FaceBox(face.x - box[0], face.y - box[1], face.w, face.h)
        print(f"3. passport crop {crop.size}")

        cutout = background.remove_background(crop)
        photo = background.composite_on_color(cutout, (255, 255, 255))
        print("4. background removed")

        photo = enhance.apply_enhancements(photo, fc, True, True, True)
        print("4b. enhancements applied")

        suits = suit.list_suits()
        assert suits, "no suit templates found"
        suited = suit.apply_suit(photo, fc, suits[0])
        print(f"5. suit applied ({suits[0].name}, {len(suits)} available)")

        s = sheet.build_sheet(suited.convert("RGB"), sheet.PAPERS['4x6"'], 8)
        print(f"6. sheet built {s.size}")
        print("SELFTEST PASSED")
        return 0
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        print("SELFTEST FAILED")
        return 1
