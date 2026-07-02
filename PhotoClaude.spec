# PyInstaller spec — build with:  pyinstaller PhotoClaude.spec
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

datas = [("assets/suits", "assets/suits")]
datas += collect_data_files("rembg")
datas += collect_data_files("onnxruntime")

# Ship the segmentation model inside the installer so the app is fully
# offline after install. Run tools/predownload_model.py before building.
u2net_dir = os.path.join(os.path.expanduser("~"), ".u2net")
model_file = os.path.join(u2net_dir, "u2net_human_seg.onnx")
if os.path.exists(model_file):
    datas.append((model_file, "u2net"))

hiddenimports = (
    collect_submodules("rembg")
    + collect_submodules("onnxruntime")
    + ["pillow_heif", "scipy.special._cdflib"]
)

a = Analysis(
    ["photoclaude\\main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=["tools\\runtime_hook_model.py"],
    excludes=["tkinter", "matplotlib"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PhotoStudio",
    console=False,
    icon=None,
    version="tools\\version_info.txt",
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="PhotoStudio")
