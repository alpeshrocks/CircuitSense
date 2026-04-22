#!/usr/bin/env bash
# CircuitSense — one-shot setup script
# Usage: bash setup.sh

set -e

echo ""
echo "================================="
echo "  CircuitSense Setup"
echo "================================="

# ── Python version check ─────────────────────────────────────────────────────
REQUIRED_MAJOR=3
REQUIRED_MINOR=11
PYTHON=$(command -v python3 || command -v python)

if [ -z "$PYTHON" ]; then
    echo "[ERROR] Python not found. Install Python 3.11+ and retry."
    exit 1
fi

PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")
PY_MINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")

if [ "$PY_MAJOR" -lt "$REQUIRED_MAJOR" ] || \
   ([ "$PY_MAJOR" -eq "$REQUIRED_MAJOR" ] && [ "$PY_MINOR" -lt "$REQUIRED_MINOR" ]); then
    echo "[ERROR] Python $PY_VERSION found, but 3.11+ is required."
    exit 1
fi
echo "[+] Python $PY_VERSION OK"

# ── Virtual environment ───────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "[*] Creating virtual environment..."
    $PYTHON -m venv .venv
    echo "[+] Virtual environment created."
else
    echo "[+] Virtual environment already exists."
fi

source .venv/bin/activate

# ── Python dependencies ───────────────────────────────────────────────────────
echo "[*] Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r requirements-dev.txt -q
echo "[+] Python dependencies installed."

# ── C++ tools ─────────────────────────────────────────────────────────────────
if ! command -v g++ &> /dev/null; then
    echo "[ERROR] g++ not found."
    echo "  macOS : xcode-select --install"
    echo "  Ubuntu: sudo apt install build-essential"
    exit 1
fi

echo "[*] Compiling C++ tools..."
make -C parser
echo "[+] C++ tools compiled."

# ── Yosys (optional) ──────────────────────────────────────────────────────────
if command -v yosys &> /dev/null; then
    echo "[+] Yosys found — RTL synthesis enabled."
else
    echo "[!] Yosys not found (optional)."
    echo "    macOS : brew install yosys"
    echo "    Ubuntu: sudo apt install yosys"
fi

# ── Smoke test ────────────────────────────────────────────────────────────────
echo ""
echo "[*] Running smoke test..."
python main.py --no-llm --no-report --no-floor > /dev/null
echo "[+] Smoke test passed."

echo ""
echo "================================="
echo "  Setup complete!"
echo "================================="
echo ""
echo "  Activate env : source .venv/bin/activate"
echo "  Quick run    : python main.py --no-llm"
echo "  Full run     : ANTHROPIC_API_KEY=sk-... python main.py"
echo "  Run tests    : python -m pytest tests/ -v"
echo ""
