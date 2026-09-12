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

# Start backend
python3 server.py &

# Start frontend
cd frontend
npm run dev &

wait
