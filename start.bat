@echo off
title NASDAQ Flow Terminal

REM ── Build frontend ─────────────────────────────────────────────────────────
echo [1/2] Building frontend...
cd /d "%~dp0frontend"
call npm run build
if errorlevel 1 (
    echo ERROR: Frontend build failed. Check Node/npm is installed.
    pause
    exit /b 1
)

REM ── Start backend ──────────────────────────────────────────────────────────
echo [2/2] Starting backend on port 8000...
cd /d "%~dp0backend"

REM Activate virtualenv if present
if exist "%~dp0venv\Scripts\activate.bat" (
    call "%~dp0venv\Scripts\activate.bat"
)

python -m uvicorn main:app --host 0.0.0.0 --port 8000
