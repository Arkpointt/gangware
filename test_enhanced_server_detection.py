#!/usr/bin/env python3
"""
Test script for enhanced server detection functionality.

This script tests the new find_server_template_enhanced function
to ensure it properly detects click_server and click_server2 templates
with improved reliability across different resolutions and UI scales.
"""

import sys
import os
from pathlib import Path

# Add src to path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.gangware.controllers.vision import VisionController
import logging

# Configure logging to see debug output
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

def test_enhanced_detection():
    """Test the enhanced server detection functionality."""
    print("Testing Enhanced Server Detection")
    print("=" * 50)

    # Initialize vision controller
    vision = VisionController()

    # Test template paths
    click_server_path = Path("assets/auto sim/click_server.png")
    click_server2_path = Path("assets/auto sim/click_server2.png")

    # Check if template files exist
    if not click_server_path.exists():
        print(f"❌ Template file not found: {click_server_path}")
        return False

    if not click_server2_path.exists():
        print(f"❌ Template file not found: {click_server2_path}")
        return False

    print(f"✅ Found template files:")
    print(f"   - {click_server_path}")
    print(f"   - {click_server2_path}")
    print()

    # Test confidence levels
    confidence_levels = [0.3, 0.35, 0.4, 0.45, 0.5]

    success_count = 0
    total_tests = 0

    for template_path in [click_server_path, click_server2_path]:
        template_name = template_path.stem
        print(f"Testing {template_name}:")
        print("-" * 30)

        for confidence in confidence_levels:
            total_tests += 1
            print(f"  Testing with confidence {confidence}...")

            try:
                # Test enhanced detection
                result = vision.find_server_template_enhanced(str(template_path), confidence=confidence)

                if result:
                    x, y = result
                    print(f"    ✅ Enhanced detection found match at ({x}, {y})")
                    success_count += 1

                    # Compare with standard detection
                    standard_result = vision.find_template(str(template_path), confidence=confidence)
                    if standard_result:
                        sx, sy = standard_result
                        print(f"    📊 Standard detection also found match at ({sx}, {sy})")
                    else:
                        print(f"    📊 Standard detection failed (enhanced method is better!)")
                    break  # Found a match, no need to test higher confidences
                else:
                    print(f"    ❌ Enhanced detection failed")

            except Exception as e:
                print(f"    💥 Error during enhanced detection: {e}")

        print()

    # Summary
    print("Test Summary:")
    print("=" * 50)
    print(f"Templates tested: 2")
    print(f"Confidence levels tested per template: {len(confidence_levels)}")
    print(f"Total successful detections: {success_count}")
    print(f"Success rate: {success_count}/{len([click_server_path, click_server2_path])} templates")

    # Test mask creation functionality
    print("\nTesting Mask Creation:")
    print("-" * 30)

    try:
        # Test mask with default parameters
        test_shape = (100, 200)  # height, width
        mask = vision._create_server_button_mask(test_shape)
        print(f"✅ Created mask for shape {test_shape}")
        print(f"   Mask shape: {mask.shape}")
        print(f"   Mask dtype: {mask.dtype}")
        print(f"   Non-zero pixels: {(mask > 0).sum()}")
        print(f"   Zero pixels (masked): {(mask == 0).sum()}")

        # Test with environment variables
        os.environ["GW_SERVER_MASK_LEFT"] = "0.1"
        os.environ["GW_SERVER_MASK_RIGHT"] = "0.9"
        os.environ["GW_SERVER_MASK_TOP"] = "0.2"
        os.environ["GW_SERVER_MASK_BOTTOM"] = "0.8"

        mask_custom = vision._create_server_button_mask(test_shape)
        print(f"✅ Created custom mask with env vars")
        print(f"   Custom mask non-zero pixels: {(mask_custom > 0).sum()}")

        # Clean up env vars
        for key in ["GW_SERVER_MASK_LEFT", "GW_SERVER_MASK_RIGHT", "GW_SERVER_MASK_TOP", "GW_SERVER_MASK_BOTTOM"]:
            if key in os.environ:
                del os.environ[key]

    except Exception as e:
        print(f"💥 Error testing mask creation: {e}")

    print("\n" + "=" * 50)
    print("Enhanced Server Detection Test Complete!")

    return success_count > 0

if __name__ == "__main__":
    print("Enhanced Server Detection Test")
    print("Make sure ARK is running and visible for best results")
    print("Press Enter to start testing...")
    input()

    success = test_enhanced_detection()

    if success:
        print("\n🎉 Test completed with some successful detections!")
    else:
        print("\n⚠️  No detections found - this may be normal if no server buttons are currently visible")

    print("\nTip: You can configure the mask area using environment variables:")
    print("  GW_SERVER_MASK_LEFT, GW_SERVER_MASK_RIGHT, GW_SERVER_MASK_TOP, GW_SERVER_MASK_BOTTOM")
    print("  Values should be between 0.0 and 1.0 (percentages)")
