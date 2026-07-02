"""PyInstaller runtime hook: point rembg at the bundled ONNX model.

If the model was packed into the bundle (see PhotoClaude.spec), copy it to
the user's model dir on first launch so rembg never needs the network.
"""
import os
import shutil
import sys

if getattr(sys, "frozen", False):
    bundled = os.path.join(sys._MEIPASS, "u2net", "u2net_human_seg.onnx")
    target_dir = os.path.join(os.path.expanduser("~"), ".u2net")
    target = os.path.join(target_dir, "u2net_human_seg.onnx")
    if os.path.exists(bundled) and not os.path.exists(target):
        os.makedirs(target_dir, exist_ok=True)
        shutil.copy2(bundled, target)
