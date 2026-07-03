# Web app contract — Photo Studio by Asad (web edition)

Single source of truth for the FastAPI backend, the browser frontend, and the
real-suit template pipeline. All three must match this exactly.

## File layout

```
webapp/server.py          FastAPI app (serves API + static + suits)
webapp/static/index.html  single-page UI
webapp/static/app.js
webapp/static/style.css
webapp/static/sample.jpg  bundled sample portrait ("Try a sample" button)
run_web.bat               starts uvicorn on http://127.0.0.1:8317
assets/suits/*.png        suit templates (shared with the desktop app)
assets_raw/               downloaded source photos + manifest.json (not shipped)
```

## Suit template convention (identical to desktop)

- RGBA PNG, transparent background, suit/torso only (no head, no neck).
- The chin anchor point is at (50% of width, 7.5% of height).
- Template width represents 3.1 x the wearer's face width at scale = 1.0.

## Overlay math (JS port of photoclaude/core/suit.py + face.py)

Server returns face = {x, y, w, h, cx, chin_y} in cutout pixel coords, where
cx = x + w/2 and chin_y = y + 1.08*h. Frontend draws the suit as:

```
suitW    = face.w * 3.1 * scale          // scale slider: 0.70 .. 1.40, default 1.0
suitH    = suitW * (imgH_of_template / imgW_of_template)
anchorX  = face.cx + dx * cutoutW / 100  // dx slider: -20 .. 20, default 0
anchorY  = face.chin_y + 0.04 * face.h + dy * cutoutH / 100
drawX    = anchorX - suitW / 2
drawY    = anchorY - suitH * 0.075
```

If face is null, frontend synthesizes the desktop fallback box:
fw = 0.34*cutoutW; face = { x: (cutoutW-fw)/2, y: 0.18*cutoutH, w: fw,
h: 1.25*fw, cx: cutoutW/2, chin_y: 0.18*cutoutH + 1.08*1.25*fw }.

## HTTP API (all local, no auth)

### POST /api/process — multipart form, field name `file`
Accepts jpg/png/heic/tiff/webp/bmp. Pipeline: EXIF-rotate, face detect,
passport crop (35:45), AI background removal.
200 JSON:
```
{ "cutout": "<base64 PNG, RGBA, transparent bg>",
  "width": int, "height": int,
  "face": {"x":int,"y":int,"w":int,"h":int,"cx":float,"chin_y":float} }
```
`face` is never null: when detection fails the server synthesizes the desktop
fallback box (fw = 0.34*W; x=(W-fw)/2, y=0.18*H, h=1.25*fw) so clients need no
fallback logic of their own.
```
```
400 JSON {"detail": "..."} on unreadable file.

### POST /api/enhance — JSON body
One-click enhancements applied server-side to the ORIGINAL cutout (client
must not stack calls on already-enhanced output). Alpha is preserved.
```
{ "cutout": "<base64 PNG RGBA>", "face": {"x","y","w","h"},
  "fix_light": bool, "smooth_skin": bool, "brighten_face": bool }
```
200: `{ "cutout": "<base64 PNG RGBA>" }` — 400 on undecodable input.
Backed by photoclaude.core.enhance.apply_enhancements().

### GET /api/suits
```
[ {"name": "Navy Suit Red Tie", "file": "navy_suit_red_tie.png",
   "url": "/suits/navy_suit_red_tie.png"}, ... ]
```
Sorted by name. Backed by photoclaude.core.suit.list_suits().

### GET /api/papers
```
{ "4x6\"": {"copies": [2,4,6,8]}, "5x7\"": {"copies": [2,4,6,8,9]},
  "A4": {"copies": [2,4,6,8,10,12,30]} }
```
Backed by photoclaude.core.sheet PAPERS/copy_options().

### POST /api/sheet — JSON body
```
{ "photo": "<base64 PNG, the flattened final photo from the canvas>",
  "paper": "4x6\"" | "5x7\"" | "A4", "copies": int, "format": "pdf" | "png" }
```
Returns the binary sheet (300 DPI, cut guides) with
Content-Disposition: attachment; filename=passport_sheet.<ext>.
Backed by photoclaude.core.sheet.build_sheet()/save_sheet().

### Static
- `/` -> index.html, `/static/*` -> webapp/static, `/suits/<file>` -> assets/suits.

## Frontend UX requirements

- Center stage: large drag-&-drop zone ("Drag & drop your photo here — or
  click to browse"), also a "Try a sample photo" button loading /static/sample.jpg.
- After processing: canvas editor in the center showing bg color + cutout +
  suit, live. Suit is also draggable directly on the canvas (mousedown/move);
  dragging updates the dx/dy sliders.
- Right/left panels: background swatches (White, Off-white, Light blue,
  Passport blue, Light gray, Red, custom color picker, Keep transparent);
  suit gallery as thumbnails (None + each suit, images from /suits/...);
  sliders Size/Horizontal/Vertical; paper size + copies selects (populated
  from /api/papers); buttons: Download Photo (PNG 413x531 via canvas),
  Download Sheet (PDF), Download Sheet (PNG), Start Over.
- Status/progress line during AI processing (takes a few seconds).
- Professional look, responsive >= 1024px, works in Chrome/Edge.
- No external CDNs — everything self-contained, vanilla JS.

## Ports / processes

- Dev server: `uvicorn webapp.server:app --host 127.0.0.1 --port 8317`
- Frontend must use relative URLs (fetch("/api/...")) so the port is irrelevant.
