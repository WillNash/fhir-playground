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
  echo "ERROR: python3 is required. Install it with:"
  echo "       sudo apt install python3  (Debian/Ubuntu)"
  echo "       brew install python       (macOS)"
  exit 1
fi

echo "  Python: $(python3 --version)"

# ── Dependency installation ──────────────────────────────────
# Strategy: try venv first (cleanest), fall back to --user install.
# A venv requires python3-venv on Debian/Ubuntu:
#   sudo apt install python3-venv

install_deps_venv() {
  if [ ! -d ".venv" ]; then
    echo "  Creating virtual environment (.venv)..."
    python3 -m venv .venv
  fi
  # Guard: venv creation can silently produce an incomplete dir
  if [ ! -f ".venv/bin/activate" ]; then
    echo "  WARNING: venv incomplete — python3-venv may not be installed."
    echo "  To fix: sudo apt install python3-venv  (then rerun)"
    return 1
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  echo "  Installing dependencies into venv..."
  pip install -q -r requirements.txt
  return 0
}

install_deps_user() {
  echo "  Installing dependencies (user install — no venv)..."
  # Try pip3 or python3 -m pip; pass --break-system-packages where needed (PEP 668)
  if python3 -m pip install -q --user -r requirements.txt 2>/dev/null; then
    :
  elif python3 -m pip install -q --user --break-system-packages -r requirements.txt 2>/dev/null; then
    :
  else
    echo ""
    echo "  ERROR: Could not install Python dependencies."
    echo "  Options:"
    echo "    1. Install python3-venv and retry:  sudo apt install python3-venv"
    echo "    2. Install pip if missing:           sudo apt install python3-pip"
    exit 1
  fi
  export PATH="$HOME/.local/bin:$PATH"
}

# Try venv; fall back to user install if venv is broken/unavailable
USING_VENV=false
if python3 -c "import venv" &>/dev/null 2>&1; then
  if install_deps_venv 2>/dev/null; then
    USING_VENV=true
  else
    install_deps_user
  fi
else
  install_deps_user
fi

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
