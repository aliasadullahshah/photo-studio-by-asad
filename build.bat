@echo off
rem Build a distributable Windows app in dist\PhotoClaude\
cd /d "%~dp0"
pip install pyinstaller
python tools\generate_suits.py
python tools\predownload_model.py
pyinstaller PhotoClaude.spec --noconfirm
echo.
echo Done. App folder: dist\PhotoStudio\PhotoStudio.exe
echo To build a setup.exe installer, install Inno Setup and run:
echo   "%%LOCALAPPDATA%%\Programs\Inno Setup 6\ISCC.exe" installer.iss
