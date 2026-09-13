#!/usr/bin/env bash
# Transmute Dev Server Launcher
# Runs both the Backend Synthesis API (port 8000) and Vite Frontend (port 5173)

cleanup() {
    echo ""
    echo "[!] Stopping all Transmute servers..."
    kill $(jobs -p) 2>/dev/null || true
    fuser -k 8000/tcp 2>/dev/null || true
    fuser -k 5173/tcp 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "=================================================="
echo " Starting Transmute Unified System"
echo " Backend Target:  http://localhost:8000"
echo " Frontend Target: http://localhost:5173"
echo "=================================================="

# 1. Clean up any lingering or stale processes on ports 8000 and 5173
echo "[*] Checking and clearing ports 8000 and 5173..."
fuser -k 8000/tcp 2>/dev/null || true
fuser -k 5173/tcp 2>/dev/null || true
pkill -f "python.*server.py" 2>/dev/null || true
pkill -f "node.*vite" 2>/dev/null || true
sleep 1

# 2. Locate project virtual environment python
if [ -f "$ROOT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif command -v uv >/dev/null 2>&1; then
    PYTHON_BIN="uv run python"
else
    PYTHON_BIN="python3"
fi

# 3. Start Backend FastAPI Server
echo "[*] Starting Transmute Backend on port 8000 using $PYTHON_BIN..."
$PYTHON_BIN server.py &
BACKEND_PID=$!

# 4. Wait for backend to be ready
echo "[*] Waiting for backend to initialize database and report healthy..."
READY=0
for i in {1..30}; do
    if curl -s http://127.0.0.1:8000/health >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 0.5
done

if [ $READY -eq 1 ]; then
    echo "=================================================="
    echo " [✓] Backend is READY:       http://localhost:8000"
    echo " [✓] Backend Health API:    http://localhost:8000/health"
    echo " [✓] Interactive API Docs:   http://localhost:8000/docs"
    echo "=================================================="
else
    echo "[!] Warning: Backend health endpoint did not respond yet. Continuing with frontend..."
fi

# 5. Start Frontend
cd "$ROOT_DIR/frontend"
if [ ! -d "node_modules/firebase" ] || [ ! -d "node_modules/rehype-raw" ]; then
    echo "[*] Installing missing frontend dependencies..."
    npm install
fi

echo "=================================================="
echo " Starting Frontend Vite Dev Server..."
echo " Web UI: http://localhost:5173"
echo "=================================================="
npm run dev
