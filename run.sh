#!/usr/bin/env bash
# ============================================================
# NZ FHIR Demo Platform — startup script
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "  NZ FHIR Clinical Demo Platform"
echo "  FHIR R4  |  SNOMED-CT  |  NZ Base IG  |  LOINC"
echo "  ================================================"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 is required"
  exit 1
fi

# Try to use a virtualenv if we can create one; fall back to system pip
USE_VENV=false
if python3 -m venv --help &>/dev/null 2>&1; then
  if python3 -c "import ensurepip" &>/dev/null 2>&1; then
    USE_VENV=true
  fi
fi

if $USE_VENV; then
  if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
  fi
  source .venv/bin/activate
  echo "Installing / checking dependencies..."
  pip install -q -r requirements.txt
else
  echo "Checking dependencies (no venv available — using system/user Python)..."
  # Try pip in order of preference
  PIP_CMD=""
  if command -v pip3 &>/dev/null; then PIP_CMD="pip3"
  elif python3 -m pip --version &>/dev/null 2>&1; then PIP_CMD="python3 -m pip"
  else
    # Bootstrap pip
    echo "Bootstrapping pip..."
    curl -sS https://bootstrap.pypa.io/get-pip.py | python3 - --break-system-packages --quiet
    export PATH="$HOME/.local/bin:$PATH"
    PIP_CMD="pip3"
  fi
  $PIP_CMD install -q --break-system-packages -r requirements.txt 2>/dev/null || \
  $PIP_CMD install -q -r requirements.txt 2>/dev/null || true
fi

export PATH="$HOME/.local/bin:$PATH"

# Create data directories
mkdir -p data/fhir_store

echo ""
echo "  Starting server..."
echo "  App:      http://localhost:8000"
echo "  API docs: http://localhost:8000/docs"
echo "  Press Ctrl+C to stop"
echo ""

# Run
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
