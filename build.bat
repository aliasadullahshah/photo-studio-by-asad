@echo off
rem Build a distributable Windows app in dist\PhotoClaude\
cd /d "%~dp0"
pip install pyinstaller
python tools\generate_suits.py
python tools\predownload_model.py
pyinstaller PhotoClaude.spec --noconfirm
if errorlevel 1 exit /b 1

rem End-to-end self-test of the frozen bundle — a build that fails this
rem must never be shipped (see %TEMP%\photostudio_selftest.log for details).
set PHOTOSTUDIO_SELFTEST=1
dist\PhotoStudio\PhotoStudio.exe
if errorlevel 1 (
    echo FROZEN SELF-TEST FAILED - do not ship this build.
    set PHOTOSTUDIO_SELFTEST=
    exit /b 1
)
set PHOTOSTUDIO_SELFTEST=
echo Frozen self-test passed.
echo.
echo Done. App folder: dist\PhotoStudio\PhotoStudio.exe
echo To build a setup.exe installer, install Inno Setup and run:
echo   "%%LOCALAPPDATA%%\Programs\Inno Setup 6\ISCC.exe" installer.iss
