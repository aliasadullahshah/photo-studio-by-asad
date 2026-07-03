"""FastAPI backend for the web edition — implements docs/web_contract.md.

Serves the single-page UI, the suit templates, and a JSON API that reuses
the exact desktop pipeline (photoclaude.core): EXIF-aware loading, face
detection + passport framing, AI background removal, print-sheet layout.
"""
from __future__ import annotations

import base64
import io
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps
from pydantic import BaseModel

from photoclaude import APP_NAME, __version__
# Importing imageio also registers the HEIC/HEIF opener when available.
from photoclaude.core import (
    background, enhance as enhance_mod, face as face_mod, imageio,
    sheet as sheet_mod, suit as suit_mod)

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)  # frontend files land here

app = FastAPI(title=f"{APP_NAME} — web edition", version=__version__)


# ---------------- pipeline helpers ----------------

def _load_upload(data: bytes) -> Image.Image:
    """In-memory twin of imageio.load_image: EXIF-rotate, normalize mode, cap size."""
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    if max(img.size) > imageio.MAX_WORKING_DIM:
        img.thumbnail((imageio.MAX_WORKING_DIM, imageio.MAX_WORKING_DIM), Image.LANCZOS)
    return img


def _auto_crop(img: Image.Image) -> tuple[Image.Image, face_mod.FaceBox]:
    """Passport-frame the image (mirrors MainWindow._auto_crop).

    Returns the 35:45 crop and the face box in crop coordinates — a pseudo
    box when detection fails, so the suit overlay always has an anchor.
    """
    detected = face_mod.detect_face(img)
    if detected:
        box = face_mod.passport_crop_box(img, detected)
        cropped = face_mod.crop_with_padding(img.convert("RGB"), box)
        face = face_mod.FaceBox(
            detected.x - box[0], detected.y - box[1], detected.w, detected.h)
    else:
        # centered fallback crop at passport aspect
        w, h = img.size
        ar = face_mod.PHOTO_ASPECT
        cw = min(w, int(h * ar))
        ch = int(cw / ar)
        left, top = (w - cw) // 2, max(0, (h - ch) // 3)
        cropped = img.convert("RGB").crop((left, top, left + cw, top + ch))
        # pseudo face box so the suit still lands somewhere sensible
        fw = int(cw * 0.34)
        face = face_mod.FaceBox((cw - fw) // 2, int(ch * 0.18), fw, int(fw * 1.25))
    return cropped, face


# ---------------- API ----------------

@app.post("/api/process")
def process_photo(file: UploadFile = File(...)) -> dict:
    """Full pipeline: EXIF-rotate -> face detect -> passport crop -> AI cutout.

    Plain (non-async) def so FastAPI runs the heavy AI call in a threadpool
    instead of blocking the event loop.
    """
    data = file.file.read()
    if not data:
        raise HTTPException(400, "The uploaded file is empty.")
    try:
        img = _load_upload(data)
    except Exception as e:  # noqa: BLE001 - surfaced to the user
        raise HTTPException(
            400, f"Could not read '{file.filename}' as an image "
                 f"(supported: jpg/png/heic/tiff/webp/bmp): {e}") from e

    cropped, face = _auto_crop(img)
    cutout = background.remove_background(cropped)

    buf = io.BytesIO()
    cutout.save(buf, "PNG")
    return {
        "cutout": base64.b64encode(buf.getvalue()).decode("ascii"),
        "width": cutout.width,
        "height": cutout.height,
        "face": {"x": face.x, "y": face.y, "w": face.w, "h": face.h,
                 "cx": face.cx, "chin_y": face.chin_y},
    }


class EnhanceRequest(BaseModel):
    cutout: str          # base64 PNG (RGBA) — always the ORIGINAL cutout
    face: dict           # {x, y, w, h} as returned by /api/process
    fix_light: bool = False
    smooth_skin: bool = False
    brighten_face: bool = False


@app.post("/api/enhance")
def enhance_photo(req: EnhanceRequest) -> dict:
    """Apply one-click enhancements to a cutout; alpha channel is preserved.

    Plain def: bilateral filtering is CPU work, keep it off the event loop.
    """
    try:
        img = Image.open(io.BytesIO(base64.b64decode(req.cutout))).convert("RGBA")
        face = face_mod.FaceBox(int(req.face["x"]), int(req.face["y"]),
                                int(req.face["w"]), int(req.face["h"]))
    except Exception as e:  # noqa: BLE001 - surfaced to the user
        raise HTTPException(400, f"Bad enhance request: {e}") from e

    out = enhance_mod.apply_enhancements(
        img, face, req.fix_light, req.smooth_skin, req.brighten_face)
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return {"cutout": base64.b64encode(buf.getvalue()).decode("ascii")}


@app.get("/api/suits")
def list_suits() -> list[dict]:
    items = [{"name": p.stem.replace("_", " ").title(),
              "file": p.name, "url": f"/suits/{p.name}"}
             for p in suit_mod.list_suits()]
    return sorted(items, key=lambda s: s["name"])


@app.get("/api/papers")
def list_papers() -> dict:
    return {name: {"copies": sheet_mod.copy_options(paper)}
            for name, paper in sheet_mod.PAPERS.items()}


class SheetRequest(BaseModel):
    photo: str          # base64 PNG, the flattened final photo
    paper: str          # key into sheet.PAPERS
    copies: int
    format: str = "pdf"  # "pdf" | "png"


@app.post("/api/sheet")
def make_sheet(req: SheetRequest) -> Response:
    """Lay out the photo on a print sheet and return it as a download."""
    if req.paper not in sheet_mod.PAPERS:
        raise HTTPException(
            400, f"Unknown paper size {req.paper!r}. Options: {list(sheet_mod.PAPERS)}")
    if req.copies < 1:
        raise HTTPException(400, "copies must be at least 1.")
    fmt = req.format.lower()
    if fmt not in ("pdf", "png"):
        raise HTTPException(400, "format must be 'pdf' or 'png'.")
    try:
        photo = Image.open(io.BytesIO(base64.b64decode(req.photo)))
        photo.load()
    except Exception as e:  # noqa: BLE001 - surfaced to the user
        raise HTTPException(400, f"Could not decode the photo: {e}") from e

    sheet = sheet_mod.build_sheet(photo, sheet_mod.PAPERS[req.paper], req.copies)
    with tempfile.TemporaryDirectory() as tmp:  # save_sheet wants a real path
        out = Path(tmp) / f"passport_sheet.{fmt}"
        sheet_mod.save_sheet(sheet, out)
        payload = out.read_bytes()
    media_type = "application/pdf" if fmt == "pdf" else "image/png"
    return Response(payload, media_type=media_type, headers={
        "Content-Disposition": f"attachment; filename=passport_sheet.{fmt}"})


# ---------------- static ----------------

@app.get("/suits/{filename}", include_in_schema=False)
def get_suit(filename: str) -> FileResponse:
    # Resolve via list_suits() so user templates (and their overrides) are
    # served too, and arbitrary paths can't be requested.
    for p in suit_mod.list_suits():
        if p.name == filename:
            return FileResponse(p, media_type="image/png")
    raise HTTPException(404, f"No suit template named {filename!r}.")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    index_html = STATIC_DIR / "index.html"
    if not index_html.is_file():
        raise HTTPException(404, "Frontend missing: webapp/static/index.html not found.")
    return FileResponse(index_html)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
