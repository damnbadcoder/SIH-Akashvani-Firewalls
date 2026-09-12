#!/usr/bin/env bash
# Make sure uvicorn is installed: pip install uvicorn fastapi pydantic 
cd "$(dirname "$0")"
echo "Starting Standalone Test Server on port 8000..."
uvicorn app:app --reload --port 8000
