<#
Windows setup helper for AutoVerify NG

Run this from the project root in PowerShell (non-elevated is fine):

  powershell -ExecutionPolicy Bypass -File .\scripts\windows_setup.ps1

What it does:
- Checks whether `tesseract` is on PATH; if not, prints the UB-Mannheim
  download URL and offers to open it in your default browser.
- Ensures `TESSDATA_PREFIX` is set (uses system tessdata if present,
  otherwise falls back to repository `tessdata/`).
- Creates a Python venv named `venv` if missing and installs the minimal
  image-processing deps (`opencv-python-headless`, `pytesseract`, `Pillow`, `numpy`).
- Optionally installs full `requirements.txt` (prompts interactively).
- Runs a quick Python diagnostic that prints `tesseract` path,
  `TESSDATA_PREFIX`, and `ocr.is_ocr_available()`.

Note: this script cannot run the Tesseract installer for you. If Tesseract
is missing, follow the installer link the script prints and re-run it after
installing and restarting your terminal.
#>

Set-StrictMode -Version Latest

function Write-Info($msg){ Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Warn($msg){ Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg){ Write-Host "[ERROR] $msg" -ForegroundColor Red }

Write-Info "AutoVerify Windows setup helper starting..."

# 1) Check for tesseract on PATH
$t = Get-Command tesseract -ErrorAction SilentlyContinue
if ($null -eq $t) {
    Write-Warn "Tesseract binary not found on PATH."
    Write-Host "Download the UB-Mannheim Windows build (recommended):"
    Write-Host "  https://github.com/UB-Mannheim/tesseract/wiki"
    $open = Read-Host "Open the download page in your browser now? (Y/n)"
    if ($open -ne 'n' -and $open -ne 'N') {
        Start-Process "https://github.com/UB-Mannheim/tesseract/wiki"
    }
    Write-Host "After installing Tesseract, re-run this script. Exiting."
    exit 0
} else {
    Write-Info "Found tesseract at: $($t.Path)"
}

# 2) Ensure TESSDATA_PREFIX points to a valid tessdata with eng.traineddata
$systemTess = Join-Path (Split-Path $t.Path -Parent) "tessdata"
$projectTess = Join-Path (Get-Location) "tessdata"

if (Test-Path (Join-Path $systemTess 'eng.traineddata')) {
    Write-Info "Using system tessdata: $systemTess"
    setx TESSDATA_PREFIX $systemTess | Out-Null
    Write-Info "TESSDATA_PREFIX set persistently to $systemTess (restart shells to apply)"
} elseif (Test-Path (Join-Path $projectTess 'eng.traineddata')) {
    Write-Info "Using project tessdata: $projectTess"
    setx TESSDATA_PREFIX $projectTess | Out-Null
    Write-Info "TESSDATA_PREFIX set persistently to $projectTess (restart shells to apply)"
} else {
    Write-Warn "No eng.traineddata found in system or project tessdata folders."
    Write-Host "The repository includes a copy at ./tessdata/eng.traineddata; ensure it's present."
    Write-Host "You can also download language files from https://github.com/tesseract-ocr/tessdata"
}

# 3) Create Python venv if missing
if (-Not (Test-Path .\venv)) {
    Write-Info "Creating virtual environment 'venv'..."
    python -m venv venv
} else {
    Write-Info "Virtual environment 'venv' already exists."
}

$venvPython = Join-Path (Get-Location) "venv\Scripts\python.exe"
if (-Not (Test-Path $venvPython)) {
    Write-Err "Could not find venv python at $venvPython. Make sure Python is installed and venv was created."
    exit 1
}

Write-Info "Upgrading pip inside venv..."
& $venvPython -m pip install --upgrade pip | Out-Null

Write-Info "Installing minimal image dependencies into venv (opencv-python-headless, pytesseract, Pillow, numpy)..."
& $venvPython -m pip install --no-cache-dir opencv-python-headless pytesseract Pillow numpy

$installFull = Read-Host "Install full requirements.txt (includes TensorFlow, can be large)? (y/N)"
if ($installFull -eq 'y' -or $installFull -eq 'Y') {
    Write-Info "Installing full requirements.txt (this may take several minutes)..."
    & $venvPython -m pip install --no-cache-dir -r requirements.txt
}

# 4) Run Python diagnostic
Write-Info "Running quick diagnostic using the venv python..."
$diag = & $venvPython -c "import shutil,os; from utils import ocr; print('shutil.which(tesseract)=', shutil.which('tesseract')); print('_TESSERACT_PATH=', getattr(ocr,'_TESSERACT_PATH', None)); print('TESSDATA_PREFIX=', os.environ.get('TESSDATA_PREFIX')); print('ocr.is_ocr_available()=', ocr.is_ocr_available())"
Write-Host $diag

Write-Info "Setup script finished. If you changed PATH/TESSDATA_PREFIX with setx, restart your terminal and re-run the diagnostic command below in the same repo root (or start the app):"
Write-Host "venv\Scripts\activate`npython -c \"import shutil,os; from utils import ocr; print(shutil.which('tesseract'), os.environ.get('TESSDATA_PREFIX'), ocr.is_ocr_available())\""

Write-Info "Start the app: `python app.py` or use run_all.bat and visit http://localhost:5000/health and /diag"
