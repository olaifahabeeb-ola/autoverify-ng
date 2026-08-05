#!/usr/bin/env bash
# ============================================================
# AutoVerify NG — Phase 2 — Linux/macOS quick-start script
# ============================================================
# Usage: run "./run_all.sh" from inside the autoverify/ folder.
#         (chmod +x run_all.sh once if needed)

set -e

echo "============================================"
echo " AutoVerify NG - Phase 2 Setup & Launch"
echo "============================================"

# 1. Create a virtual environment if it doesn't exist yet
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# 2. Activate it
source venv/bin/activate

# 3. Install/upgrade dependencies
echo "Installing dependencies (this can take a few minutes the first time)..."
pip install --upgrade pip -q
pip install -r requirements.txt

# 4. Check for the Tesseract OCR system binary
if ! command -v tesseract &> /dev/null; then
    echo ""
    echo "WARNING: Tesseract-OCR system binary not found on PATH."
    echo "Real plate reading needs it. Install with:"
    echo "  Ubuntu/Debian: sudo apt-get install tesseract-ocr"
    echo "  macOS:         brew install tesseract"
    echo "Without it, plate reading falls back to demo placeholder values."
    echo ""
fi

# 5. Run the app
echo "Starting AutoVerify NG on http://localhost:5000 ..."
python app.py
