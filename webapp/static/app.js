/* Photo Studio by Asad — web edition frontend.
 * Vanilla JS, no dependencies. Talks to the FastAPI backend described in
 * docs/web_contract.md via relative URLs.
 */
"use strict";

(() => {
  // ------------------------------------------------------------------
  // Constants (contract: "Overlay math" + "Suit template convention")
  // ------------------------------------------------------------------
  const SUIT_WIDTH_FACTOR = 3.1;      // template width = 3.1 x face width @ scale 1.0
  const SUIT_ANCHOR_Y_FRAC = 0.075;   // chin anchor at 7.5% of template height
  const CHIN_DROP_FACTOR = 0.04;      // anchor sits 0.04 * face.h below chin_y
  const EXPORT_W = 413;               // 35 mm @ 300 DPI
  const EXPORT_H = 531;               // 45 mm @ 300 DPI

  const SWATCHES = [
    { name: "White",         color: "#ffffff" },
    { name: "Off-white",     color: "#f4f0e6" },
    { name: "Light blue",    color: "#d9e9f7" },
    { name: "Passport blue", color: "#4a7ebb" },
    { name: "Light gray",    color: "#d8dbde" },
    { name: "Red",           color: "#b83a3a" },
  ];

  const IMAGE_EXT_RE = /\.(jpe?g|png|heic|heif|tiff?|webp|bmp)$/i;

  // ------------------------------------------------------------------
  // DOM
  // ------------------------------------------------------------------
  const $ = (id) => document.getElementById(id);

  const landingEl   = $("landing");
  const editorEl    = $("editor");
  const processing  = $("processing");
  const landingErr  = $("landing-error");
  const dropzone    = $("dropzone");
  const fileInput   = $("file-input");
  const btnSample   = $("btn-sample");

  const canvas      = $("canvas");
  const ctx         = canvas.getContext("2d");
  const stageHint   = $("stage-hint");

  const swatchesEl  = $("swatches");
  const customColor = $("custom-color");
  const btnTransparent = $("btn-transparent");

  const suitGallery = $("suit-gallery");
  const sliderSize  = $("slider-size");
  const sliderDx    = $("slider-dx");
  const sliderDy    = $("slider-dy");
  const valSize     = $("val-size");
  const valDx       = $("val-dx");
  const valDy       = $("val-dy");
  const btnReset    = $("btn-reset");

  const paperSelect  = $("paper-select");
  const copiesSelect = $("copies-select");
  const barStatus    = $("bar-status");
  const btnPhoto     = $("btn-download-photo");
  const btnSheetPdf  = $("btn-sheet-pdf");
  const btnSheetPng  = $("btn-sheet-png");
  const btnStartOver = $("btn-start-over");

  // ------------------------------------------------------------------
  // State
  // ------------------------------------------------------------------
  const state = {
    cutoutImg: null,          // HTMLImageElement of the RGBA cutout
    cutoutW: 0,
    cutoutH: 0,
    face: null,               // {x, y, w, h, cx, chin_y} in cutout pixel coords
    bg: "#ffffff",            // css color string, or "transparent"
    suit: null,               // {name, file, url, img} or null
    scale: 100,               // 70..140 (percent)
    dx: 0,                    // -20..20
    dy: 0,                    // -20..20
    papers: {},               // {"4x6\"": {copies:[...]}, ...}
  };

  const suitImageCache = new Map();   // url -> HTMLImageElement
  let drawQueued = false;
  let statusTimer = null;

  // ------------------------------------------------------------------
  // Small helpers
  // ------------------------------------------------------------------
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

  function isImageFile(file) {
    if (!file) return false;
    if (file.type && file.type.startsWith("image/")) return true;
    return IMAGE_EXT_RE.test(file.name || "");
  }

  function showLandingError(msg) {
    landingErr.textContent = msg;
    landingErr.hidden = false;
  }

  function clearLandingError() {
    landingErr.hidden = true;
    landingErr.textContent = "";
  }

  function setBarStatus(msg, isError) {
    clearTimeout(statusTimer);
    barStatus.textContent = msg || "";
    barStatus.classList.toggle("is-error", !!isError);
    if (msg) {
      statusTimer = setTimeout(() => {
        barStatus.textContent = "";
        barStatus.classList.remove("is-error");
      }, 6000);
    }
  }

  function triggerDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  }

  async function errorDetail(res, fallback) {
    try {
      const data = await res.json();
      if (data && typeof data.detail === "string" && data.detail) return data.detail;
    } catch (_) { /* not JSON */ }
    return fallback;
  }

  // ------------------------------------------------------------------
  // View switching
  // ------------------------------------------------------------------
  function showLanding() {
    landingEl.hidden = false;
    editorEl.hidden = true;
    processing.hidden = true;
  }

  function showProcessing() {
    processing.hidden = false;
  }

  function hideProcessing() {
    processing.hidden = true;
  }

  function showEditor() {
    landingEl.hidden = true;
    editorEl.hidden = false;
    processing.hidden = true;
  }

  // ------------------------------------------------------------------
  // Face fallback (contract: desktop fallback box when face is null)
  // ------------------------------------------------------------------
  function fallbackFace(cutoutW, cutoutH) {
    const fw = 0.34 * cutoutW;
    return {
      x: (cutoutW - fw) / 2,
      y: 0.18 * cutoutH,
      w: fw,
      h: 1.25 * fw,
      cx: cutoutW / 2,
      chin_y: 0.18 * cutoutH + 1.08 * 1.25 * fw,
    };
  }

  // ------------------------------------------------------------------
  // Compositing.
  // Order (contract): background -> cutout -> suit, with the exact
  // overlay math from docs/web_contract.md.
  // bg: css color string | "checker" | null (leave transparent)
  // ------------------------------------------------------------------
  function drawCheckerboard(c2d, w, h) {
    const s = Math.max(8, Math.round(w / 28));
    c2d.fillStyle = "#e9e9ee";
    c2d.fillRect(0, 0, w, h);
    c2d.fillStyle = "#c8c8d2";
    for (let y = 0, row = 0; y < h; y += s, row++) {
      for (let x = row % 2 ? s : 0; x < w; x += 2 * s) {
        c2d.fillRect(x, y, s, s);
      }
    }
  }

  function composite(c2d, outW, outH, bg) {
    c2d.clearRect(0, 0, outW, outH);

    if (bg === "checker") {
      drawCheckerboard(c2d, outW, outH);
    } else if (bg) {
      c2d.fillStyle = bg;
      c2d.fillRect(0, 0, outW, outH);
    }

    if (!state.cutoutImg) return;
    c2d.drawImage(state.cutoutImg, 0, 0, outW, outH);

    const suit = state.suit;
    if (!suit || !suit.img || !suit.img.complete || !suit.img.naturalWidth) return;

    const face = state.face;
    const scale = state.scale / 100;                 // slider 70..140 -> 0.70..1.40

    // --- exact contract math, in cutout pixel coordinates ---
    const suitW = face.w * SUIT_WIDTH_FACTOR * scale;
    const suitH = suitW * (suit.img.naturalHeight / suit.img.naturalWidth);
    const anchorX = face.cx + state.dx * state.cutoutW / 100;
    const anchorY = face.chin_y + CHIN_DROP_FACTOR * face.h + state.dy * state.cutoutH / 100;
    const drawX = anchorX - suitW / 2;
    const drawY = anchorY - suitH * SUIT_ANCHOR_Y_FRAC;

    // Map cutout coords -> output coords (identity for the live canvas).
    const sx = outW / state.cutoutW;
    const sy = outH / state.cutoutH;
    c2d.drawImage(suit.img, drawX * sx, drawY * sy, suitW * sx, suitH * sy);
  }

  function draw() {
    const bg = state.bg === "transparent" ? "checker" : state.bg;
    composite(ctx, canvas.width, canvas.height, bg);
  }

  function scheduleDraw() {
    if (drawQueued) return;
    drawQueued = true;
    requestAnimationFrame(() => {
      drawQueued = false;
      draw();
    });
  }

  // ------------------------------------------------------------------
  // Photo processing
  // ------------------------------------------------------------------
  async function processFile(file) {
    clearLandingError();
    if (!isImageFile(file)) {
      showLandingError("That file doesn't look like a photo. Please drop a JPG, PNG, HEIC, TIFF, WEBP or BMP image.");
      return;
    }

    showProcessing();
    try {
      const fd = new FormData();
      fd.append("file", file, file.name || "photo.jpg");
      const res = await fetch("/api/process", { method: "POST", body: fd });
      if (!res.ok) {
        const detail = await errorDetail(res, "We couldn't read that photo.");
        throw new Error(detail);
      }
      const data = await res.json();
      await loadCutout(data);
      resetEditorControls();
      showEditor();
      scheduleDraw();
    } catch (err) {
      hideProcessing();
      showLanding();
      showLandingError(
        (err && err.message ? err.message : "Something went wrong.") +
        " Please try a different photo."
      );
    }
  }

  function loadCutout(data) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        state.cutoutImg = img;
        state.cutoutW = data.width;
        state.cutoutH = data.height;
        state.face = data.face ? data.face : fallbackFace(data.width, data.height);
        canvas.width = data.width;
        canvas.height = data.height;
        resolve();
      };
      img.onerror = () => reject(new Error("The processed image could not be displayed."));
      img.src = "data:image/png;base64," + data.cutout;
    });
  }

  function resetEditorControls() {
    state.bg = "#ffffff";
    state.suit = null;
    state.scale = 100;
    state.dx = 0;
    state.dy = 0;
    syncSliders();
    updateSwatchSelection();
    updateSuitSelection();
    updateStageCursor();
    setBarStatus("");
  }

  // ------------------------------------------------------------------
  // Landing wiring (drop zone, browse, sample)
  // ------------------------------------------------------------------
  function initLanding() {
    // Never let the browser navigate away on a stray drop.
    ["dragover", "drop"].forEach((ev) =>
      window.addEventListener(ev, (e) => e.preventDefault())
    );

    dropzone.addEventListener("click", () => fileInput.click());
    dropzone.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        fileInput.click();
      }
    });

    dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropzone.classList.add("is-dragover");
    });
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("is-dragover"));
    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.classList.remove("is-dragover");
      const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (file) processFile(file);
      else showLandingError("Nothing droppable found — try dropping an image file.");
    });

    fileInput.addEventListener("change", () => {
      const file = fileInput.files && fileInput.files[0];
      if (file) processFile(file);
      fileInput.value = "";
    });

    btnSample.addEventListener("click", async () => {
      clearLandingError();
      try {
        const res = await fetch("/static/sample.jpg");
        if (!res.ok) throw new Error();
        const blob = await res.blob();
        const file = new File([blob], "sample.jpg", { type: "image/jpeg" });
        processFile(file);
      } catch (_) {
        showLandingError("Couldn't load the sample photo. Try dropping your own image instead.");
      }
    });
  }

  // ------------------------------------------------------------------
  // Background panel
  // ------------------------------------------------------------------
  function initBackgroundPanel() {
    SWATCHES.forEach((s) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "swatch";
      btn.style.background = s.color;
      btn.dataset.color = s.color;
      btn.title = s.name;
      btn.setAttribute("aria-label", "Background: " + s.name);
      btn.addEventListener("click", () => setBackground(s.color));
      swatchesEl.appendChild(btn);
    });

    customColor.addEventListener("input", () => setBackground(customColor.value));
    btnTransparent.addEventListener("click", () => setBackground("transparent"));
    updateSwatchSelection();
  }

  function setBackground(color) {
    state.bg = color;
    updateSwatchSelection();
    scheduleDraw();
  }

  function updateSwatchSelection() {
    const current = state.bg;
    swatchesEl.querySelectorAll(".swatch").forEach((el) => {
      el.classList.toggle("is-selected", el.dataset.color.toLowerCase() === String(current).toLowerCase());
    });
    btnTransparent.classList.toggle("is-selected", current === "transparent");
  }

  // ------------------------------------------------------------------
  // Suit panel
  // ------------------------------------------------------------------
  async function loadSuits() {
    try {
      const res = await fetch("/api/suits");
      if (!res.ok) throw new Error();
      const suits = await res.json();
      renderSuitGallery(suits);
    } catch (_) {
      suitGallery.innerHTML = "";
      const note = document.createElement("div");
      note.className = "panel-note";
      note.textContent = "Couldn't load suit templates.";
      suitGallery.appendChild(note);
    }
  }

  function renderSuitGallery(suits) {
    suitGallery.innerHTML = "";

    const noneTile = document.createElement("button");
    noneTile.type = "button";
    noneTile.className = "suit-tile is-selected";
    noneTile.dataset.suit = "";
    noneTile.innerHTML =
      '<span class="suit-thumb suit-thumb-none" aria-hidden="true">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">' +
      '<circle cx="12" cy="12" r="9"/><path d="M5.5 5.5l13 13"/></svg></span>' +
      '<span class="suit-name">None</span>';
    noneTile.addEventListener("click", () => selectSuit(null));
    suitGallery.appendChild(noneTile);

    suits.forEach((s) => {
      const tile = document.createElement("button");
      tile.type = "button";
      tile.className = "suit-tile";
      tile.dataset.suit = s.url;

      const thumb = document.createElement("span");
      thumb.className = "suit-thumb";
      const img = document.createElement("img");
      img.src = s.url;
      img.alt = s.name;
      img.loading = "lazy";
      thumb.appendChild(img);

      const label = document.createElement("span");
      label.className = "suit-name";
      label.textContent = s.name;

      tile.appendChild(thumb);
      tile.appendChild(label);
      tile.addEventListener("click", () => selectSuit(s));
      suitGallery.appendChild(tile);
    });
  }

  function selectSuit(s) {
    if (!s) {
      state.suit = null;
      updateSuitSelection();
      updateStageCursor();
      scheduleDraw();
      return;
    }

    let img = suitImageCache.get(s.url);
    if (!img) {
      img = new Image();
      img.src = s.url;
      suitImageCache.set(s.url, img);
    }
    state.suit = { name: s.name, file: s.file, url: s.url, img };

    if (!img.complete) {
      img.addEventListener("load", () => {
        if (state.suit && state.suit.img === img) scheduleDraw();
      }, { once: true });
    }

    updateSuitSelection();
    updateStageCursor();
    scheduleDraw();
  }

  function updateSuitSelection() {
    const currentUrl = state.suit ? state.suit.url : "";
    suitGallery.querySelectorAll(".suit-tile").forEach((el) => {
      el.classList.toggle("is-selected", el.dataset.suit === currentUrl);
    });
  }

  // ------------------------------------------------------------------
  // Sliders + canvas drag / wheel
  // ------------------------------------------------------------------
  function fmtOffset(v) {
    const n = Math.round(v * 2) / 2;
    return n > 0 ? "+" + n : String(n);
  }

  function syncSliders() {
    sliderSize.value = state.scale;
    sliderDx.value = state.dx;
    sliderDy.value = state.dy;
    valSize.textContent = Math.round(state.scale) + "%";
    valDx.textContent = fmtOffset(state.dx);
    valDy.textContent = fmtOffset(state.dy);
  }

  function initAdjustments() {
    sliderSize.addEventListener("input", () => {
      state.scale = clamp(parseFloat(sliderSize.value), 70, 140);
      syncSliders();
      scheduleDraw();
    });
    sliderDx.addEventListener("input", () => {
      state.dx = clamp(parseFloat(sliderDx.value), -20, 20);
      syncSliders();
      scheduleDraw();
    });
    sliderDy.addEventListener("input", () => {
      state.dy = clamp(parseFloat(sliderDy.value), -20, 20);
      syncSliders();
      scheduleDraw();
    });
    btnReset.addEventListener("click", () => {
      state.scale = 100;
      state.dx = 0;
      state.dy = 0;
      syncSliders();
      scheduleDraw();
    });

    // Drag the suit directly on the canvas -> updates dx/dy.
    let dragging = false;
    let startX = 0, startY = 0, baseDx = 0, baseDy = 0;

    canvas.addEventListener("pointerdown", (e) => {
      if (!state.suit) return;
      dragging = true;
      startX = e.clientX;
      startY = e.clientY;
      baseDx = state.dx;
      baseDy = state.dy;
      canvas.setPointerCapture(e.pointerId);
      canvas.classList.add("is-dragging");
      e.preventDefault();
    });

    canvas.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      const rect = canvas.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      // Slider units are percent of the cutout, so a full canvas width == 100.
      const du = (e.clientX - startX) * 100 / rect.width;
      const dv = (e.clientY - startY) * 100 / rect.height;
      state.dx = clamp(Math.round((baseDx + du) * 2) / 2, -20, 20);
      state.dy = clamp(Math.round((baseDy + dv) * 2) / 2, -20, 20);
      syncSliders();
      scheduleDraw();
    });

    const endDrag = (e) => {
      if (!dragging) return;
      dragging = false;
      canvas.classList.remove("is-dragging");
      try { canvas.releasePointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    };
    canvas.addEventListener("pointerup", endDrag);
    canvas.addEventListener("pointercancel", endDrag);

    // Wheel over the canvas -> suit size.
    canvas.addEventListener("wheel", (e) => {
      if (!state.suit) return;           // let the page scroll normally
      e.preventDefault();
      const step = e.deltaY < 0 ? 2 : -2;
      state.scale = clamp(state.scale + step, 70, 140);
      syncSliders();
      scheduleDraw();
    }, { passive: false });
  }

  function updateStageCursor() {
    canvas.classList.toggle("is-draggable", !!state.suit);
    stageHint.style.visibility = state.suit ? "visible" : "hidden";
  }

  // ------------------------------------------------------------------
  // Papers + copies
  // ------------------------------------------------------------------
  async function loadPapers() {
    try {
      const res = await fetch("/api/papers");
      if (!res.ok) throw new Error();
      state.papers = await res.json();
    } catch (_) {
      // Contract-defined fallback so the UI stays usable if the call fails.
      state.papers = {
        '4x6"': { copies: [2, 4, 6, 8] },
        '5x7"': { copies: [2, 4, 6, 8, 9] },
        "A4":   { copies: [2, 4, 6, 8, 10, 12, 30] },
      };
    }
    populatePapers();
  }

  function populatePapers() {
    paperSelect.innerHTML = "";
    const names = Object.keys(state.papers);
    names.forEach((name) => {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      paperSelect.appendChild(opt);
    });
    paperSelect.value = names.includes('4x6"') ? '4x6"' : names[0] || "";
    populateCopies();
    paperSelect.addEventListener("change", populateCopies);
  }

  function populateCopies() {
    const paper = state.papers[paperSelect.value];
    const copies = (paper && paper.copies) || [4];
    const previous = copiesSelect.value;
    copiesSelect.innerHTML = "";
    copies.forEach((n) => {
      const opt = document.createElement("option");
      opt.value = String(n);
      opt.textContent = String(n);
      copiesSelect.appendChild(opt);
    });
    if (copies.map(String).includes(previous)) copiesSelect.value = previous;
    else if (copies.includes(4)) copiesSelect.value = "4";
    else copiesSelect.value = String(copies[0]);
  }

  // ------------------------------------------------------------------
  // Downloads
  // ------------------------------------------------------------------
  function renderFlattened(outW, outH, bg) {
    const off = document.createElement("canvas");
    off.width = outW;
    off.height = outH;
    composite(off.getContext("2d"), outW, outH, bg);
    return off;
  }

  function downloadPhoto() {
    // Transparent background stays transparent in the photo download;
    // the checkerboard is a display-only stand-in.
    const bg = state.bg === "transparent" ? null : state.bg;
    const off = renderFlattened(EXPORT_W, EXPORT_H, bg);
    off.toBlob((blob) => {
      if (blob) triggerDownload(blob, "passport_photo.png");
      else setBarStatus("Couldn't export the photo.", true);
    }, "image/png");
  }

  function setSheetBusy(busy) {
    [btnPhoto, btnSheetPdf, btnSheetPng].forEach((b) => (b.disabled = busy));
  }

  async function downloadSheet(format) {
    // Sheets are always opaque: "Keep transparent" is forced to white.
    const bg = state.bg === "transparent" ? "#ffffff" : state.bg;
    const off = renderFlattened(state.cutoutW, state.cutoutH, bg);
    const photoB64 = off.toDataURL("image/png").split(",")[1];

    setSheetBusy(true);
    setBarStatus("Building your sheet…");
    try {
      const res = await fetch("/api/sheet", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          photo: photoB64,
          paper: paperSelect.value,
          copies: parseInt(copiesSelect.value, 10),
          format,
        }),
      });
      if (!res.ok) {
        const detail = await errorDetail(res, "The sheet could not be generated.");
        throw new Error(detail);
      }
      const blob = await res.blob();
      const cd = res.headers.get("Content-Disposition") || "";
      const m = cd.match(/filename="?([^";]+)"?/i);
      triggerDownload(blob, m ? m[1] : "passport_sheet." + format);
      setBarStatus("Sheet downloaded.");
    } catch (err) {
      setBarStatus(err && err.message ? err.message : "Sheet download failed.", true);
    } finally {
      setSheetBusy(false);
    }
  }

  function startOver() {
    state.cutoutImg = null;
    state.face = null;
    resetEditorControls();
    clearLandingError();
    showLanding();
  }

  // ------------------------------------------------------------------
  // Init
  // ------------------------------------------------------------------
  function init() {
    initLanding();
    initBackgroundPanel();
    initAdjustments();

    btnPhoto.addEventListener("click", downloadPhoto);
    btnSheetPdf.addEventListener("click", () => downloadSheet("pdf"));
    btnSheetPng.addEventListener("click", () => downloadSheet("png"));
    btnStartOver.addEventListener("click", startOver);

    // Fetch catalogs up front so the editor is ready the moment
    // processing finishes.
    loadSuits();
    loadPapers();

    syncSliders();
    updateStageCursor();
  }

  init();
})();
