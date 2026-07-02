"""Turn real photos of people in professional attire into suit overlay templates.

For each input photo:
  1. AI background removal (same local model as the app).
  2. Face detection to find the chin line and face width.
  3. Erase everything above the chin (head + neck) with a feathered edge.
  4. Re-canvas to the template convention: chin anchor at (50% w, 7.5% h),
     canvas width = 3.1 x face width — so scale=1.0 fits automatically.

Usage:
  python tools/make_real_suits.py assets_raw\photo1.jpg [more...]
  python tools/make_real_suits.py assets_raw            (whole folder)
  python tools/make_real_suits.py --offset 0.3 photo.jpg
      (--offset lowers the cut by a fraction of the face height — use when a
       beard or jaw shadow survives the default chin-line cut)

Output: assets/suits/real_<stem>.png
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from photoclaude.core import background, face as face_mod, imageio
from photoclaude.core.suit import NECK_ANCHOR_Y, WIDTH_PER_FACE

OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "suits"
CANVAS_RATIO = 900 / 1200  # height / width, matches drawn templates
FEATHER_PX_FRac = 0.012    # feather at the chin cut, relative to canvas width


def make_template(src: Path, offset: float = 0.0) -> Path | None:
    img = imageio.load_image(src)
    face = face_mod.detect_face(img)
    if face is None:
        print(f"  SKIP {src.name}: no face found")
        return None

    cutout = background.remove_background(img)
    a = np.asarray(cutout.getchannel("A"), dtype=np.float32)

    # Feathered cut just above the chin: kill head and neck. The optional
    # offset deepens the cut only near the face center (Gaussian falloff) so
    # a beard can be removed without slicing a straight line into the
    # shoulders at the sides.
    cut_y = face.chin_y
    feather = max(4.0, img.width * FEATHER_PX_FRac)
    yy = np.arange(cutout.height, dtype=np.float32)[:, None]
    xx = np.arange(cutout.width, dtype=np.float32)[None, :]
    bump = offset * face.h * np.exp(-(((xx - face.cx) / (0.8 * face.w)) ** 2))
    ramp = np.clip((yy - (cut_y + bump)) / feather, 0.0, 1.0)  # 0 above -> 1 below
    a *= ramp
    cutout.putalpha(Image.fromarray(a.astype(np.uint8)))

    # Canvas normalized to the template convention.
    canvas_w = int(round(face.w * WIDTH_PER_FACE))
    canvas_h = int(round(canvas_w * CANVAS_RATIO))
    anchor_y = int(round(canvas_h * NECK_ANCHOR_Y))
    left = int(round(face.cx - canvas_w / 2))
    top = int(round(cut_y - anchor_y))

    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    canvas.paste(cutout, (-left, -top), cutout)

    # Drop templates whose suit content is too sparse (bad segmentation, or
    # the subject is cropped right below the chin).
    coverage = np.asarray(canvas.getchannel("A"))[canvas_h // 3 :, :].mean() / 255
    if coverage < 0.25:
        print(f"  SKIP {src.name}: suit area too sparse ({coverage:.0%})")
        return None

    canvas = canvas.filter(ImageFilter.SMOOTH)
    out = OUT_DIR / f"real_{src.stem}.png"
    canvas.save(out)
    print(f"  wrote {out.name}  ({canvas_w}x{canvas_h}, coverage {coverage:.0%})")
    return out


def main(argv: list[str]) -> int:
    offset = 0.0
    if "--offset" in argv:
        i = argv.index("--offset")
        offset = float(argv[i + 1])
        argv = argv[:i] + argv[i + 2 :]
    if not argv:
        print(__doc__)
        return 2
    files: list[Path] = []
    for arg in argv:
        p = Path(arg)
        if p.is_dir():
            files += [f for f in sorted(p.iterdir())
                      if f.suffix.lower() in imageio.SUPPORTED_EXTENSIONS]
        elif p.is_file():
            files.append(p)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    made = [make_template(f, offset=offset) for f in files]
    ok = [m for m in made if m]
    print(f"{len(ok)}/{len(files)} templates created")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
