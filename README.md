# Photo Studio by Asad

Copyright © 2026 Ali Asad. All rights reserved.

A Windows desktop app for making print-ready passport photos, fully offline
(Windows 10 64-bit version 1809 or later, and Windows 11):

1. **Open photos from any source** — JPG/PNG from Android, HEIC from iPhone,
   JPG/TIFF from a DSLR. EXIF rotation is applied automatically and the face is
   auto-framed to the 35 × 45 mm passport ratio (ICAO-style head size and eye line).
2. **AI background removal** — a local U²-Net human-segmentation model
   (ONNX, runs on-device, no internet needed after first model download).
   Replace the background with white, blue, red, a custom color, or keep the original.
3. **Suit / blazer overlay** — pick a suit template and it is auto-fitted under
   the detected chin; fine-tune with size / horizontal / vertical sliders.
   Use **Add Custom Suit…** to import any transparent suit PNG (e.g. a real
   suit photo with the background erased) — it is stored in
   `%LOCALAPPDATA%\Photo Studio by Asad\suits` and appears in the list permanently.
   Convention: suit centered, collar opening at top-center ~7% from the top.
4. **Print sheets** — lay out 2 / 4 / 6 / 8 / … copies of the 35 × 45 mm photo on
   4×6", 5×7" or A4 paper at 300 DPI with cut guides, then save as PNG/PDF or
   print directly. 8 copies on 4×6" use the lab-style rotated layout. Always
   print at **100% scale / actual size**.

## Run from source

```bat
pip install -r requirements.txt
python tools\generate_suits.py    :: one-time: create suit templates
run.bat
```

The first "Remove Background" click downloads the segmentation model
(~176 MB) to `%USERPROFILE%\.u2net`; everything after that is offline.

## Build the installable app

```bat
build.bat                         :: PyInstaller -> dist\PhotoStudio\
iscc installer.iss                :: (Inno Setup 6) -> installer_output\PhotoStudio-Setup.exe
```

`build.bat` pre-downloads the AI model and bundles it, so the installed app
never needs the network.

## Typical workflow

Open Photo → Remove Background → choose background color → choose a suit →
adjust sliders if needed → pick paper size and copy count → Save Sheet (PDF)
or Print Sheet.

## Notes

- Camera RAW files (.CR2/.NEF/.ARW) are not read directly — export to JPG in
  your camera app first.
- If no face is detected (e.g. side profile), a centered crop is used and the
  suit position can be corrected with the sliders.
