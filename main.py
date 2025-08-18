#!/usr/bin/env python3
"""
Gangware Application Launcher

This is the main entry point for the Gangware application.
It launches the application from the src/gangware package.
"""

import sys
from pathlib import Path

# Add the src directory to Python path so we can import from src.gangware
project_root = Path(__file__).parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

# Import and run the main application
from gangware.main import main

if __name__ == "__main__":
    main()
