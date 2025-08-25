#!/usr/bin/env python3
"""
Test AutoSim logging functionality.

This script demonstrates how the AutoSim feature logs menu detection events
for end-user visibility and troubleshooting.
"""
import sys
import time
from pathlib import Path

# Add src to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from gangware.core.config import ConfigManager
from gangware.core.logging_setup import setup_logging
from gangware.core.state import StateManager
from gangware.features.autosim import MenuWatcher

def main():
    # Setup logging to console and file
    config = ConfigManager()
    setup_logging(config)

    # Create a simple state manager
    state = StateManager()

    # Create menu watcher with logging enabled
    watcher = MenuWatcher(state, interval=1.0)  # Slower for demo

    print("Starting AutoSim with logging enabled...")
    print("Check logs at: %APPDATA%\\Gangware\\logs\\session-<timestamp>\\gangware.log")
    print("Press Ctrl+C to stop")

    try:
        watcher.start()
        time.sleep(30)  # Run for 30 seconds
    except KeyboardInterrupt:
        print("\nStopping AutoSim...")
    finally:
        watcher.stop()
        print("AutoSim stopped.")

if __name__ == "__main__":
    main()
