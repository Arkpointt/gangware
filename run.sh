#!/bin/bash
# Gangware Application Launcher Script for Unix-like systems
# This script runs the application using the virtual environment

echo "Starting Gangware..."
"$(dirname "$0")/.venv/bin/python" "$(dirname "$0")/main.py" "$@"
