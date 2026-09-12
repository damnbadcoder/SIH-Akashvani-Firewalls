#!/usr/bin/env python3
"""
Transmute Backend Server Entrypoint.
Usage:
    python server.py
"""
import os
import sys

# Auto-switch to project virtual environment if executed with system/global python
venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
if os.path.exists(venv_python) and os.path.realpath(sys.executable) != os.path.realpath(venv_python):
    os.execv(venv_python, [venv_python] + sys.argv)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Ensure packages installed in common environment are discoverable by system python
for extra_pkg_path in [
    "/home/samyakjain/snap/antigravity-cli/common/local/lib/python3.12/dist-packages",
    "/home/samyakjain/snap/antigravity-cli/common/local/lib/python3.12/site-packages",
    os.path.expanduser("~/snap/antigravity-cli/common/local/lib/python3.12/dist-packages"),
    os.path.expanduser("~/snap/antigravity-cli/common/local/lib/python3.12/site-packages"),
    os.path.expanduser("~/.local/lib/python3.12/site-packages"),
]:
    if os.path.isdir(extra_pkg_path) and extra_pkg_path not in sys.path:
        sys.path.insert(0, extra_pkg_path)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from enhancements.sensitivity_checker import scan_and_redact
except ImportError:
    def scan_and_redact(text: str, is_organization: bool = False):
        return text, []

from pipelines.synthesis.server import run_server

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    try:
        from backend.main import start_server
        print(f"[+] Starting Transmute FastAPI Backend with Uvicorn on port {port}...")
        start_server(port=port)
    except Exception as e:
        print(f"[!] FastAPI startup failed ({e}), falling back to standard synthesis server...")
        run_server(port)
