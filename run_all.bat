@echo off
REM ============================================================
REM AutoVerify NG — Phase 2 — Windows quick-start script
REM ============================================================
REM Usage: double-click this file, or run "run_all.bat" from a
REM Command Prompt inside the autoverify\ folder.

echo ============================================
echo  AutoVerify NG - Phase 2 Setup ^& Launch
echo ============================================

REM 1. Create a virtual environment if it doesn't exist yet
IF NOT EXIST venv (
    echo Creating virtual environment...
    python -m venv venv
)

REM 2. Activate it
call venv\Scripts\activate.bat

REM 3. Install/upgrade dependencies
echo Installing dependencies (this can take a few minutes the first time)...
pip install --upgrade pip >nul
pip install -r requirements.txt

REM 4. Reminder about Tesseract OCR system binary
echo.
echo IMPORTANT: Real plate OCR requires the Tesseract-OCR system binary.
echo If you haven't installed it yet, download it from:
echo   https://github.com/UB-Mannheim/tesseract/wiki
echo and make sure "tesseract" is on your PATH.
echo (Without it, plate reading falls back to demo placeholder values.)
echo.

REM 5. Run the app
echo Starting AutoVerify NG on http://localhost:5000 ...
python app.py

pause
