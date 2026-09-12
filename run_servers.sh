#!/usr/bin/env bash
# Transmute Dev Server Launcher
# Runs both the Backend Synthesis API (port 8000) and Vite Frontend (port 5173)

cleanup() {
    echo ""
    echo "[!] Stopping all servers..."
    kill $(jobs -p) 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "=================================================="
echo " Starting Transmute System"
echo " Backend:  http://localhost:8000"
echo " Frontend: http://localhost:5173"
echo "=================================================="

# Ensure backend finds common package environment
SNAP_PY_PACKAGES="/home/samyakjain/snap/antigravity-cli/common/local/lib/python3.12/dist-packages"
SNAP_PY_SITE="/home/samyakjain/snap/antigravity-cli/common/local/lib/python3.12/site-packages"
if [ -d "$SNAP_PY_PACKAGES" ]; then
    export PYTHONPATH="$SNAP_PY_SITE:$SNAP_PY_PACKAGES:$PYTHONPATH"
fi

# Start backend if not already active
if python3 -c "import socket; s = socket.socket(); s.settimeout(0.5); exit(0 if s.connect_ex(('127.0.0.1', 8000)) == 0 else 1)" 2>/dev/null; then
    echo "[*] Backend is already running on http://localhost:8000"
else
    echo "[*] Starting backend synthesis server on port 8000..."
    python3 server.py &
fi

# Start frontend
cd frontend
if [ ! -d "node_modules/firebase" ] || [ ! -d "node_modules/rehype-raw" ]; then
    echo "[*] Installing missing frontend dependencies (including firebase)..."
    npm install
fi
npm run dev &

wait
