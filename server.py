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
    run_server(port)
