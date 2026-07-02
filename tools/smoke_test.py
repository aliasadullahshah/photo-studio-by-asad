"""Headless end-to-end test of the processing pipeline (no GUI).

Uses scikit-image's bundled astronaut portrait so no external files are
needed. Outputs land in the given directory (default: ./smoke_out).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from photoclaude.core import background, face as face_mod, sheet as sheet_mod, suit as suit_mod

out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("smoke_out")
out_dir.mkdir(parents=True, exist_ok=True)

import skimage.data

img = Image.fromarray(skimage.data.astronaut())
img = img.resize((1024, 1024), Image.LANCZOS)
print("1. loaded sample portrait", img.size)

face = face_mod.detect_face(img)
assert face, "face not detected"
print(f"2. face detected at x={face.x} y={face.y} w={face.w} h={face.h}")

box = face_mod.passport_crop_box(img, face)
cropped = face_mod.crop_with_padding(img.convert("RGB"), box)
face_c = face_mod.FaceBox(face.x - box[0], face.y - box[1], face.w, face.h)
ar = cropped.width / cropped.height
print(f"3. passport crop {cropped.size}, aspect {ar:.3f} (target {35/45:.3f})")
assert abs(ar - 35 / 45) < 0.02
cropped.save(out_dir / "1_cropped.png")

print("4. removing background (downloads model on first run)…")
cutout = background.remove_background(cropped)
cutout.save(out_dir / "2_cutout.png")
photo = background.composite_on_color(cutout, (185, 213, 240))
photo.save(out_dir / "3_bg_lightblue.png")
print("   background replaced")

suits = suit_mod.list_suits()
assert suits, "no suit templates found — run tools/generate_suits.py first"
suited = suit_mod.apply_suit(photo, face_c, suits[0])
suited.convert("RGB").save(out_dir / "4_suited.png")
print(f"5. suit applied: {suits[0].name}")

for paper_name, copies in [('4x6"', 4), ('4x6"', 8), ('5x7"', 6), ("A4", 8)]:
    paper = sheet_mod.PAPERS[paper_name]
    s = sheet_mod.build_sheet(suited.convert("RGB"), paper, copies)
    fname = f"5_sheet_{paper_name.replace(chr(34), 'in').replace('x', 'x')}_{copies}.png"
    sheet_mod.save_sheet(s, out_dir / fname)
    print(f"6. sheet {paper_name} x{copies}: {s.size}px (max fit {sheet_mod.max_copies(paper)})")

print("\nALL STEPS PASSED — outputs in", out_dir.resolve())
