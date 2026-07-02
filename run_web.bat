@echo off
rem Photo Studio by Asad — web edition. Starts the local server and opens the browser.
cd /d "%~dp0"
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:8317"
python -m uvicorn webapp.server:app --host 127.0.0.1 --port 8317
