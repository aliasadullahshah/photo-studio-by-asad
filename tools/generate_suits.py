"""Generate suit/blazer overlay templates as transparent PNGs.

Run once (build step): python tools/generate_suits.py
Templates follow the convention in photoclaude/core/suit.py: 1200x900 px,
collar opening centered at x=50%, y=7.5% of height.

Rendered procedurally with curved shoulders, vertical gradient shading and a
light fabric-noise texture so they read as cloth rather than flat vector art.
Users can also import real suit photos (transparent PNGs) in the app via
"Add Custom Suit..." — same convention.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H = 2400, 1800  # drawn at 2x, saved at 1200x900
CX = W // 2

OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "suits"

rng = np.random.default_rng(7)


def shade(color, factor):
    return tuple(max(0, min(255, int(c * factor))) for c in color)


def bezier(p0, p1, p2, n=24):
    """Sample a quadratic bezier curve."""
    t = np.linspace(0, 1, n)
    x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t**2 * p2[0]
    y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t**2 * p2[1]
    return list(zip(x, y))


def gradient_polygon(img, polygon, color_top, color_bottom, y0=None, y1=None):
    """Fill a polygon with a vertical gradient."""
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).polygon(polygon, fill=255)
    ys = [p[1] for p in polygon]
    y0 = min(ys) if y0 is None else y0
    y1 = max(ys) if y1 is None else y1
    grad_col = np.linspace(color_top, color_bottom, max(2, int(y1 - y0)))
    ramp = np.zeros((img.height, img.width, 3), dtype=np.float32)
    yy = np.clip(np.arange(img.height) - y0, 0, len(grad_col) - 1).astype(int)
    ramp[:] = grad_col[yy][:, None, :]
    fill = Image.fromarray(ramp.astype(np.uint8), "RGB").convert("RGBA")
    img.paste(fill, (0, 0), mask)


def add_fabric_noise(img, polygon_mask_poly, strength=5):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).polygon(polygon_mask_poly, fill=255)
    m = np.asarray(mask, dtype=bool)
    arr = np.asarray(img).copy()
    noise = rng.normal(0, strength, size=(img.height, img.width, 1))
    rgb = arr[:, :, :3].astype(np.int16) + noise.astype(np.int16)
    arr[:, :, :3] = np.where(m[:, :, None], np.clip(rgb, 0, 255), arr[:, :, :3])
    return Image.fromarray(arr)


def silhouette_points():
    """Jacket outline with curved shoulders and flared arms."""
    right = (
        bezier((CX + 290, 62), (CX + 700, 90), (CX + 950, 330))      # shoulder
        + bezier((CX + 950, 330), (CX + 1110, 700), (CX + 1170, 1800))  # arm
    )
    left = [(2 * CX - x, y) for x, y in right]
    top = [(CX - 290, 62), (CX - 180, 96), (CX, 112), (CX + 180, 96), (CX + 290, 62)]
    return top[2:] + right + [(CX + 1170, 1800), (CX - 1170, 1800)] + left[::-1] + top[:3]


def draw_suit(jacket, shirt, tie=None, collar_style="tie", pinstripe=False):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    sil = silhouette_points()
    gradient_polygon(img, sil, shade(jacket, 1.25), shade(jacket, 0.62))

    # underarm/side shadows
    for sign in (1, -1):
        side = (
            bezier((CX + sign * 950, 330), (CX + sign * 1110, 700), (CX + sign * 1170, 1800))
            + [(CX + sign * 900, 1800)]
            + bezier((CX + sign * 900, 1800), (CX + sign * 840, 760), (CX + sign * 800, 420))[::-1]
        )
        gradient_polygon(img, side, shade(jacket, 0.95), shade(jacket, 0.5))

    if pinstripe:
        for x in range(CX - 1100, CX + 1100, 56):
            d.line([(x, 100), (x, 1800)], fill=(*shade(jacket, 1.5), 60), width=3)

    # shirt V with soft vertical shading
    shirt_poly = [(CX - 285, 72), (CX - 180, 104), (CX, 120), (CX + 180, 104),
                  (CX + 285, 72), (CX + 118, 570), (CX, 750), (CX - 118, 570)]
    gradient_polygon(img, shirt_poly, shirt, shade(shirt, 0.82))

    # collar flaps
    for sign in (1, -1):
        flap = [(CX + sign * 285, 72), (CX + sign * 42, 155),
                (CX + sign * 122, 335), (CX + sign * 300, 165)]
        gradient_polygon(img, flap, shade(shirt, 1.0), shade(shirt, 0.86))
        d.line(flap + [flap[0]], fill=(*shade(shirt, 0.7), 200), width=4)

    # tie
    if collar_style == "tie" and tie:
        knot = [(CX - 60, 168), (CX + 60, 168), (CX + 82, 300), (CX, 345), (CX - 82, 300)]
        gradient_polygon(img, knot, shade(tie, 1.25), shade(tie, 0.8))
        blade = [(CX - 56, 322), (CX + 56, 322), (CX + 106, 880), (CX, 1000), (CX - 106, 880)]
        gradient_polygon(img, blade, shade(tie, 1.05), shade(tie, 0.65))
        d.line([(CX - 20, 350), (CX - 44, 870)], fill=(*shade(tie, 1.35), 90), width=14)
        d.line([(CX - 60, 168), (CX + 60, 168)], fill=(*shade(tie, 0.6), 255), width=6)

    # lapels with curved inner edge and notch
    lapel_top, lapel_bot = shade(jacket, 1.45), shade(jacket, 0.85)
    edge = shade(jacket, 0.5)
    for sign in (1, -1):
        outer = bezier((CX + sign * 285, 62), (CX + sign * 560, 300), (CX + sign * 315, 930))
        inner = bezier((CX + sign * 315, 930), (CX + sign * 60, 740), (CX + sign * 120, 340))
        notch = [(CX + sign * 120, 340), (CX + sign * 200, 260), (CX + sign * 150, 210)]
        lapel = outer + inner + notch
        gradient_polygon(img, lapel, lapel_top, lapel_bot)
        d.line(lapel + [lapel[0]], fill=(*edge, 160), width=4)

    # closed jacket below the button point
    front = [(CX - 315, 930), (CX - 30, 710), (CX + 30, 710), (CX + 315, 930),
             (CX + 250, 1800), (CX - 250, 1800)]
    gradient_polygon(img, front, shade(jacket, 0.98), shade(jacket, 0.6))
    d.line([(CX, 780), (CX, 1800)], fill=(*shade(jacket, 0.55), 200), width=7)
    d.ellipse([CX - 24, 775, CX + 24, 823], fill=(*shade(jacket, 0.4), 255))
    d.ellipse([CX - 24, 775, CX + 12, 805], fill=(*shade(jacket, 0.9), 120))

    img = add_fabric_noise(img, sil, strength=4)
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    return img.resize((W // 2, H // 2), Image.LANCZOS)


SUITS = {
    "navy_suit_red_tie": dict(jacket=(28, 40, 78), shirt=(248, 248, 250),
                              tie=(152, 26, 36)),
    "black_suit_silver_tie": dict(jacket=(26, 26, 30), shirt=(250, 250, 252),
                                  tie=(150, 155, 165)),
    "charcoal_suit_blue_tie": dict(jacket=(56, 58, 64), shirt=(244, 247, 252),
                                   tie=(32, 68, 130)),
    "navy_pinstripe_gold_tie": dict(jacket=(30, 36, 60), shirt=(250, 249, 245),
                                    tie=(168, 130, 42), pinstripe=True),
    "gray_blazer_open_collar": dict(jacket=(102, 106, 114), shirt=(232, 240, 250),
                                    tie=None, collar_style="open"),
}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, kw in SUITS.items():
        img = draw_suit(**kw)
        img.save(OUT_DIR / f"{name}.png")
        print("wrote", OUT_DIR / f"{name}.png")


if __name__ == "__main__":
    main()
