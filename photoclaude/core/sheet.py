"""Compose passport photos (35x45 mm) onto printable sheets at 300 DPI.

Layouts are adaptive: if the requested copy count doesn't fit upright with
comfortable margins, the tiles are rotated 90 deg and/or margins tightened —
that's how photo labs fit 8 passport photos on a 4x6" print.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

DPI = 300
MM_PER_INCH = 25.4

PHOTO_MM = (35, 45)  # standard passport size


def mm_to_px(mm: float) -> int:
    return int(round(mm / MM_PER_INCH * DPI))


@dataclass(frozen=True)
class Paper:
    name: str
    width_px: int
    height_px: int


PAPERS = {
    '4x6"': Paper('4x6"', 4 * DPI, 6 * DPI),
    '5x7"': Paper('5x7"', 5 * DPI, 7 * DPI),
    "A4": Paper("A4", mm_to_px(210), mm_to_px(297)),
}

# (margin_mm, gap_mm): comfortable first, compact fallback
_SPACINGS = [(5, 3), (2, 2)]
# preference order: upright/standard, rotated/standard, upright/compact, rotated/compact
_CONFIGS = [(False, _SPACINGS[0]), (True, _SPACINGS[0]),
            (False, _SPACINGS[1]), (True, _SPACINGS[1])]


def _tile_size(rotated: bool) -> tuple[int, int]:
    pw, ph = mm_to_px(PHOTO_MM[0]), mm_to_px(PHOTO_MM[1])
    return (ph, pw) if rotated else (pw, ph)


def _grid(paper: Paper, rotated: bool, spacing: tuple[int, int]) -> tuple[int, int]:
    margin, gap = mm_to_px(spacing[0]), mm_to_px(spacing[1])
    tw, th = _tile_size(rotated)
    cols = (paper.width_px - 2 * margin + gap) // (tw + gap)
    rows = (paper.height_px - 2 * margin + gap) // (th + gap)
    return max(0, int(cols)), max(0, int(rows))


def max_copies(paper: Paper) -> int:
    return max(c * r for c, r in (_grid(paper, rot, sp) for rot, sp in _CONFIGS))


def copy_options(paper: Paper) -> list[int]:
    m = max_copies(paper)
    opts = [n for n in (2, 4, 6, 8, 10, 12) if n <= m]
    if m not in opts:
        opts.append(m)
    return opts


def build_sheet(photo: Image.Image, paper: Paper, copies: int) -> Image.Image:
    """Lay out `copies` passport prints on white paper with cut guides."""
    copies = min(copies, max_copies(paper))
    rotated, spacing = next(
        (rot, sp) for rot, sp in _CONFIGS
        if (g := _grid(paper, rot, sp))[0] * g[1] >= copies)
    margin, gap = mm_to_px(spacing[0]), mm_to_px(spacing[1])

    pw, ph = mm_to_px(PHOTO_MM[0]), mm_to_px(PHOTO_MM[1])
    tile = photo.convert("RGB").resize((pw, ph), Image.LANCZOS)
    if rotated:
        tile = tile.rotate(90, expand=True)
    tw, th = tile.size

    cols_cap, _ = _grid(paper, rotated, spacing)
    cols = min(cols_cap, copies)
    rows = -(-copies // cols)  # ceil

    grid_w = cols * tw + (cols - 1) * gap
    grid_h = rows * th + (rows - 1) * gap
    x0 = (paper.width_px - grid_w) // 2
    y0 = (paper.height_px - grid_h) // 2
    assert x0 >= margin - 1 and y0 >= margin - 1

    sheet = Image.new("RGB", (paper.width_px, paper.height_px), "white")
    draw = ImageDraw.Draw(sheet)
    placed = 0
    for r in range(rows):
        for c in range(cols):
            if placed >= copies:
                break
            x = x0 + c * (tw + gap)
            y = y0 + r * (th + gap)
            sheet.paste(tile, (x, y))
            draw.rectangle([x - 1, y - 1, x + tw, y + th], outline=(180, 180, 180))
            placed += 1
    return sheet


def save_sheet(sheet: Image.Image, path: str | Path) -> None:
    """Save with DPI metadata so it prints at true size. PNG, JPG or PDF."""
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        sheet.save(path, "PDF", resolution=DPI)
    else:
        sheet.save(path, dpi=(DPI, DPI))
