from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QPushButton, QSlider, QTabWidget, QVBoxLayout,
    QWidget,
)

from photoclaude import APP_NAME, COPYRIGHT
from photoclaude.core import background, face as face_mod, imageio, sheet as sheet_mod, suit as suit_mod

BG_PRESETS = [
    ("White", (255, 255, 255)),
    ("Off-white", (245, 245, 245)),
    ("Light blue", (185, 213, 240)),
    ("Passport blue", (70, 130, 200)),
    ("Light gray", (215, 215, 215)),
    ("Red", (190, 30, 40)),
]


def pil_to_pixmap(img: Image.Image) -> QPixmap:
    img = img.convert("RGBA")
    qimg = QImage(img.tobytes(), img.width, img.height,
                  img.width * 4, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


class RemoveBgWorker(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, img: Image.Image):
        super().__init__()
        self.img = img

    def run(self):
        try:
            self.done.emit(background.remove_background(self.img))
        except Exception as e:  # noqa: BLE001 - surfaced to the user
            self.failed.emit(str(e))


class PreviewLabel(QLabel):
    def __init__(self):
        super().__init__("Open a photo to begin")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(420, 480)
        self._pix: QPixmap | None = None

    def set_image(self, img: Image.Image | None):
        self._pix = pil_to_pixmap(img) if img else None
        self._rescale()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._rescale()

    def _rescale(self):
        if self._pix:
            self.setPixmap(self._pix.scaled(
                self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1180, 760)

        # pipeline state
        self.cropped: Image.Image | None = None   # passport-framed source (RGB)
        self.face: face_mod.FaceBox | None = None  # face box in crop coords
        self.cutout: Image.Image | None = None     # RGBA after bg removal
        self.bg_color: tuple | None = (255, 255, 255)
        self.final_photo: Image.Image | None = None
        self.worker: RemoveBgWorker | None = None

        self._build_ui()
        self.statusBar().showMessage("Ready — open a photo from your phone or camera.")

    # ---------------- UI construction ----------------
    def _build_ui(self):
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.addLayout(self._build_controls(), 0)
        layout.addWidget(self._build_previews(), 1)
        self.setCentralWidget(root)

    def _build_controls(self):
        col = QVBoxLayout()

        open_btn = QPushButton("Open Photo…")
        open_btn.clicked.connect(self.open_photo)
        col.addWidget(open_btn)
        self.file_label = QLabel("No photo loaded")
        self.file_label.setWordWrap(True)
        col.addWidget(self.file_label)

        # background group
        bg_box = QGroupBox("2. Background")
        bg_lay = QVBoxLayout(bg_box)
        self.remove_bg_btn = QPushButton("Remove Background (AI)")
        self.remove_bg_btn.clicked.connect(self.remove_bg)
        bg_lay.addWidget(self.remove_bg_btn)
        self.bg_combo = QComboBox()
        for name, _ in BG_PRESETS:
            self.bg_combo.addItem(name)
        self.bg_combo.addItem("Custom…")
        self.bg_combo.addItem("Keep original")
        self.bg_combo.currentIndexChanged.connect(self.on_bg_changed)
        bg_lay.addWidget(self.bg_combo)
        col.addWidget(bg_box)

        # suit group
        suit_box = QGroupBox("3. Suit / Blazer")
        suit_lay = QVBoxLayout(suit_box)
        self.suit_combo = QComboBox()
        self.suit_combo.currentIndexChanged.connect(self.recompose)
        self.suit_paths: list = []
        self._reload_suits()
        suit_lay.addWidget(self.suit_combo)

        add_suit_btn = QPushButton("Add Custom Suit…")
        add_suit_btn.setToolTip(
            "Import any suit image as a transparent PNG.\n"
            "Convention: suit centered, collar opening at the top-center\n"
            "(about 7% from the top edge), background fully transparent.")
        add_suit_btn.clicked.connect(self.add_custom_suit)
        suit_lay.addWidget(add_suit_btn)

        self.suit_scale = self._slider(suit_lay, "Size", 70, 140, 100)
        self.suit_dx = self._slider(suit_lay, "Horizontal", -20, 20, 0)
        self.suit_dy = self._slider(suit_lay, "Vertical", -20, 20, 0)
        col.addWidget(suit_box)

        # output group
        out_box = QGroupBox("4. Print Sheet")
        out_lay = QVBoxLayout(out_box)
        self.paper_combo = QComboBox()
        for name in sheet_mod.PAPERS:
            self.paper_combo.addItem(name)
        self.paper_combo.currentIndexChanged.connect(self.on_paper_changed)
        out_lay.addWidget(QLabel("Paper size"))
        out_lay.addWidget(self.paper_combo)
        self.copies_combo = QComboBox()
        out_lay.addWidget(QLabel("Passport photos per sheet (35 × 45 mm)"))
        out_lay.addWidget(self.copies_combo)
        self.on_paper_changed()

        save_photo_btn = QPushButton("Save Single Photo…")
        save_photo_btn.clicked.connect(self.save_photo)
        out_lay.addWidget(save_photo_btn)
        save_sheet_btn = QPushButton("Save Sheet (PNG / PDF)…")
        save_sheet_btn.clicked.connect(self.save_sheet)
        out_lay.addWidget(save_sheet_btn)
        print_btn = QPushButton("Print Sheet")
        print_btn.clicked.connect(self.print_sheet)
        out_lay.addWidget(print_btn)
        col.addWidget(out_box)

        col.addStretch(1)
        copyright_label = QLabel(COPYRIGHT)
        copyright_label.setStyleSheet("color: gray; font-size: 10px;")
        copyright_label.setAlignment(Qt.AlignCenter)
        col.addWidget(copyright_label)
        wrapper = QVBoxLayout()
        box = QGroupBox("1. Photo")
        box.setLayout(col)
        wrapper.addWidget(box)
        return wrapper

    def _slider(self, layout, label, lo, hi, val):
        layout.addWidget(QLabel(label))
        s = QSlider(Qt.Horizontal)
        s.setRange(lo, hi)
        s.setValue(val)
        s.valueChanged.connect(self.recompose)
        layout.addWidget(s)
        return s

    def _build_previews(self):
        tabs = QTabWidget()
        self.photo_preview = PreviewLabel()
        self.sheet_preview = PreviewLabel()
        tabs.addTab(self.photo_preview, "Passport Photo")
        tabs.addTab(self.sheet_preview, "Print Sheet")
        tabs.currentChanged.connect(self.on_tab_changed)
        self.tabs = tabs
        return tabs

    # ---------------- actions ----------------
    def _reload_suits(self, select: str | None = None):
        self.suit_paths = suit_mod.list_suits()
        self.suit_combo.blockSignals(True)
        current = select or self.suit_combo.currentText()
        self.suit_combo.clear()
        self.suit_combo.addItem("None")
        for p in self.suit_paths:
            self.suit_combo.addItem(p.stem.replace("_", " ").title())
        idx = self.suit_combo.findText(current)
        self.suit_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.suit_combo.blockSignals(False)

    def add_custom_suit(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a transparent suit PNG", "", "PNG images (*.png)")
        if not path:
            return
        try:
            dst = suit_mod.add_custom_suit(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Could not import suit", str(e))
            return
        self._reload_suits(select=dst.stem.replace("_", " ").title())
        self.statusBar().showMessage(
            f"Suit added to {dst.parent} — use the sliders to fine-tune the fit.")
        self.recompose()

    def open_photo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open photo", "", imageio.file_dialog_filter())
        if not path:
            return
        try:
            img = imageio.load_image(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Could not open", str(e))
            return
        self.file_label.setText(Path(path).name)
        self.cutout = None
        self._auto_crop(img)
        self.recompose()

    def _auto_crop(self, img: Image.Image):
        detected = face_mod.detect_face(img)
        if detected:
            box = face_mod.passport_crop_box(img, detected)
            self.cropped = face_mod.crop_with_padding(img.convert("RGB"), box)
            self.face = face_mod.FaceBox(
                detected.x - box[0], detected.y - box[1], detected.w, detected.h)
            self.statusBar().showMessage(
                "Face detected — auto-framed to 35 × 45 mm passport ratio.")
        else:
            # centered fallback crop at passport aspect
            w, h = img.size
            ar = face_mod.PHOTO_ASPECT
            cw = min(w, int(h * ar))
            ch = int(cw / ar)
            left, top = (w - cw) // 2, max(0, (h - ch) // 3)
            self.cropped = img.convert("RGB").crop((left, top, left + cw, top + ch))
            # pseudo face box so the suit still lands somewhere sensible
            fw = int(cw * 0.34)
            self.face = face_mod.FaceBox((cw - fw) // 2, int(ch * 0.18), fw, int(fw * 1.25))
            self.statusBar().showMessage(
                "No face detected — centered crop used. Suit position may need the sliders.")

    def remove_bg(self):
        if not self.cropped:
            QMessageBox.information(self, APP_NAME, "Open a photo first.")
            return
        if self.worker and self.worker.isRunning():
            return
        self.remove_bg_btn.setEnabled(False)
        self.statusBar().showMessage(
            "Removing background with local AI model… (first run downloads the model once)")
        self.worker = RemoveBgWorker(self.cropped)
        self.worker.done.connect(self.on_bg_removed)
        self.worker.failed.connect(self.on_bg_failed)
        self.worker.start()

    def on_bg_removed(self, cutout):
        self.cutout = cutout
        self.remove_bg_btn.setEnabled(True)
        self.statusBar().showMessage("Background removed.")
        self.recompose()

    def on_bg_failed(self, msg):
        self.remove_bg_btn.setEnabled(True)
        self.statusBar().showMessage("Background removal failed.")
        QMessageBox.warning(self, "Background removal failed", msg)

    def on_bg_changed(self):
        idx = self.bg_combo.currentIndex()
        text = self.bg_combo.currentText()
        if text == "Custom…":
            c = QColorDialog.getColor(parent=self)
            if c.isValid():
                self.bg_color = (c.red(), c.green(), c.blue())
        elif text == "Keep original":
            self.bg_color = None
        else:
            self.bg_color = BG_PRESETS[idx][1]
        self.recompose()

    def on_paper_changed(self):
        paper = sheet_mod.PAPERS[self.paper_combo.currentText()]
        current = self.copies_combo.currentText()
        self.copies_combo.clear()
        for n in sheet_mod.copy_options(paper):
            self.copies_combo.addItem(str(n))
        preferred = current or "4"
        if self.copies_combo.findText(preferred) >= 0:
            self.copies_combo.setCurrentText(preferred)
        self.on_tab_changed(self.tabs.currentIndex() if hasattr(self, "tabs") else 0)

    # ---------------- composition ----------------
    def recompose(self):
        if not self.cropped:
            return
        if self.cutout is not None and self.bg_color is not None:
            base = background.composite_on_color(self.cutout, self.bg_color)
        elif self.cutout is not None and self.bg_color is None:
            base = self.cropped.convert("RGBA")
        else:
            base = self.cropped.convert("RGBA")

        idx = self.suit_combo.currentIndex()
        if idx > 0 and self.face:
            base = suit_mod.apply_suit(
                base, self.face, self.suit_paths[idx - 1],
                scale=self.suit_scale.value() / 100.0,
                dx=self.suit_dx.value(), dy=self.suit_dy.value())

        self.final_photo = base.convert("RGB")
        self.photo_preview.set_image(self.final_photo)
        if self.tabs.currentIndex() == 1:
            self._update_sheet_preview()

    def _current_sheet(self) -> Image.Image | None:
        if not self.final_photo:
            return None
        paper = sheet_mod.PAPERS[self.paper_combo.currentText()]
        copies = int(self.copies_combo.currentText() or "4")
        return sheet_mod.build_sheet(self.final_photo, paper, copies)

    def on_tab_changed(self, idx):
        if idx == 1:
            self._update_sheet_preview()

    def _update_sheet_preview(self):
        s = self._current_sheet()
        if s:
            preview = s.copy()
            preview.thumbnail((1000, 1000))
            self.sheet_preview.set_image(preview)

    # ---------------- output ----------------
    def save_photo(self):
        if not self.final_photo:
            QMessageBox.information(self, APP_NAME, "Nothing to save yet.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save passport photo", "passport_photo.png",
            "PNG (*.png);;JPEG (*.jpg)")
        if not path:
            return
        out = self.final_photo.resize(
            (sheet_mod.mm_to_px(35), sheet_mod.mm_to_px(45)), Image.LANCZOS)
        out.save(path, dpi=(sheet_mod.DPI, sheet_mod.DPI))
        self.statusBar().showMessage(f"Saved {path}")

    def save_sheet(self):
        s = self._current_sheet()
        if not s:
            QMessageBox.information(self, APP_NAME, "Nothing to save yet.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save print sheet", "passport_sheet.pdf",
            "PDF (*.pdf);;PNG (*.png);;JPEG (*.jpg)")
        if not path:
            return
        sheet_mod.save_sheet(s, path)
        self.statusBar().showMessage(f"Saved {path} — print at 100% scale.")

    def print_sheet(self):
        s = self._current_sheet()
        if not s:
            QMessageBox.information(self, APP_NAME, "Nothing to print yet.")
            return
        tmp = Path(tempfile.gettempdir()) / "photoclaude_sheet.pdf"
        sheet_mod.save_sheet(s, tmp)
        try:
            os.startfile(tmp, "print")
            self.statusBar().showMessage(
                "Sent to printer — make sure scaling is set to 100% / actual size.")
        except OSError:
            os.startfile(tmp)
            self.statusBar().showMessage(
                "Opened the sheet PDF — print it at 100% scale from your PDF viewer.")
