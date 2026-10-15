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

# ── Check Python ─────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 is required. Install it with:"
  echo "       sudo apt install python3        (Debian/Ubuntu/WSL)"
  echo "       brew install python             (macOS)"
  exit 1
fi

echo "  Python: $(python3 --version)"

# ── Virtual environment ───────────────────────────────────────
# If .venv exists but has no activate script it is stale (created
# before python3-venv was installed). Delete and rebuild.
if [ -d ".venv" ] && [ ! -f ".venv/bin/activate" ]; then
  echo "  Removing incomplete .venv (python3-venv was missing when it was created)..."
  rm -rf .venv
fi

if [ ! -d ".venv" ]; then
  echo "  Creating virtual environment (.venv)..."
  if ! python3 -m venv .venv 2>/tmp/venv_err; then
    echo ""
    echo "  Could not create virtual environment. Fix with:"
    echo "    sudo apt install python3-venv    (Debian/Ubuntu/WSL)"
    echo "  Then rerun: bash run.sh"
    echo ""
    cat /tmp/venv_err 2>/dev/null || true
    exit 1
  fi
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "  Installing / updating dependencies..."
pip install -q -r requirements.txt

# ── Data directories ─────────────────────────────────────────
mkdir -p data/fhir_store

# ── Start ────────────────────────────────────────────────────
echo ""
echo "  ┌─────────────────────────────────────────┐"
echo "  │  App:      http://localhost:8000         │"
echo "  │  API docs: http://localhost:8000/docs    │"
echo "  │  Press Ctrl+C to stop                   │"
echo "  └─────────────────────────────────────────┘"
echo ""

python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
