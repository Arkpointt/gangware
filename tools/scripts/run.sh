#!/bin/bash
# Gangware Application Launcher Script for Unix-like systems
# This script runs the application using the virtual environment

echo "Starting Gangware..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
"$SCRIPT_DIR/../../.venv/bin/python" "$SCRIPT_DIR/main.py" "$@"
