#!/usr/bin/env python3
"""Test script to verify Connection_Failed detection implementation."""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from gangware.core.config import ConfigManager
from gangware.features.autosim.automation import AutoSimWorkflow


def test_connection_failed_detection():
    """Test that Connection_Failed detection works."""
    print("Testing Connection_Failed detection...")

    # Create instances
    config = ConfigManager()
    workflow = AutoSimWorkflow(config)

    # Test template path resolution
    base = Path(__file__).resolve().parents[2]  # Go up 2 levels to project root
    template_path = base / "assets" / "menus" / "connection_failed.jpg"

    print(f"Template path: {template_path}")
    print(f"Template exists: {template_path.exists()}")

    # Test detection method (won't find anything on desktop, but should not error)
    try:
        detected = workflow._detect_connection_failed()
        print(f"Detection call successful: {detected}")
    except Exception as e:
        print(f"Detection error: {e}")
        return False

    # Test menu detection methods
    try:
        main_menu = workflow._detect_menu("MAIN_MENU")
        select_game = workflow._detect_menu("SELECT_GAME")
        server_browser = workflow._detect_menu("SERVER_BROWSER")
        print(f"Menu detection tests - Main: {main_menu}, Select: {select_game}, Browser: {server_browser}")
    except Exception as e:
        print(f"Menu detection error: {e}")
        return False

    print("✅ All tests passed!")
    return True


if __name__ == "__main__":
    success = test_connection_failed_detection()
    sys.exit(0 if success else 1)
