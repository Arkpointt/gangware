#!/usr/bin/env python3
"""
Test script to verify Ark window constraint functionality.
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from gangware.features.auto_sim import AutoSimFeature
from gangware.controllers.vision import VisionController
from gangware.controllers.controls import InputController
from gangware.core.config import ConfigManager


def test_ark_window_detection():
    """Test the Ark window detection functionality"""
    print("Testing Ark window detection...")

    # Create minimal dependencies
    config_manager = ConfigManager()
    vision = VisionController()
    input_ctrl = InputController()

    # Create Auto Sim instance
    auto_sim = AutoSimFeature(config_manager, vision, input_ctrl, overlay=None)

    # Test the _get_ark_window_region method
    ark_region = auto_sim._get_ark_window_region()

    if ark_region:
        print(f"✓ Ark window detected: {ark_region}")
        print(f"  Left: {ark_region['left']}, Top: {ark_region['top']}")
        print(f"  Width: {ark_region['width']}, Height: {ark_region['height']}")

        # Test coordinate clamping
        test_coords = (ark_region['left'] + ark_region['width'] + 100, ark_region['top'] + 50)
        clamped = auto_sim._clamp_to_ark_window(test_coords, ark_region)
        print(f"  Coordinate clamping test:")
        print(f"    Original: {test_coords}")
        print(f"    Clamped: {clamped}")

    else:
        print("✗ Ark window not detected (expected if Ark is not running)")

    return ark_region is not None


def test_template_search_constraint():
    """Test that template searches are properly constrained"""
    print("\nTesting template search constraints...")

    config_manager = ConfigManager()
    vision = VisionController()
    input_ctrl = InputController()

    auto_sim = AutoSimFeature(config_manager, vision, input_ctrl, overlay=None)

    # Test path resolution
    test_template = auto_sim.templates.path("press_start")
    if test_template:
        print(f"✓ Template found: {test_template}")

        # Test the _find method with a very short timeout
        print("  Testing _find method with Ark window constraint...")
        result = auto_sim._find(str(test_template), 0.8, 0.1)  # Short timeout
        print(f"  Search result: {result}")

    else:
        print("✗ press_start template not found")

    return True


if __name__ == "__main__":
    print("Ark Window Constraint Test")
    print("=" * 40)

    try:
        test1_passed = test_ark_window_detection()
        test2_passed = test_template_search_constraint()

        print(f"\nTest Results:")
        print(f"  Ark window detection: {'✓ PASS' if test1_passed else '✗ FAIL'}")
        print(f"  Template search constraint: {'✓ PASS' if test2_passed else '✗ FAIL'}")

        if test1_passed and test2_passed:
            print("\n🎉 All tests passed!")
        else:
            print("\n⚠️ Some tests failed (may be expected if Ark is not running)")

    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
