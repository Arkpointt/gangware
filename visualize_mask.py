#!/usr/bin/env python3
"""
Visual test for the server button mask functionality.

This script creates a visual representation of how the mask works
on the server button templates, helping to understand and debug
the masking behavior.
"""

import sys
import os
from pathlib import Path
import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

try:
    import cv2
    from src.gangware.controllers.vision import VisionController
except ImportError as e:
    print(f"Error importing dependencies: {e}")
    print("Make sure OpenCV and the project modules are installed.")
    sys.exit(1)

def visualize_mask():
    """Create a visual representation of the masking effect."""
    print("Server Button Mask Visualization")
    print("=" * 50)

    vision = VisionController()

    # Template paths
    templates = [
        Path("assets/auto sim/click_server.png"),
        Path("assets/auto sim/click_server2.png")
    ]

    for template_path in templates:
        if not template_path.exists():
            print(f"❌ Template not found: {template_path}")
            continue

        print(f"\nProcessing {template_path.name}:")
        print("-" * 30)

        # Load template
        template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
        if template is None:
            print(f"❌ Could not load template: {template_path}")
            continue

        h, w = template.shape
        print(f"Template size: {w} x {h}")

        # Create mask
        mask = vision._create_server_button_mask(template.shape)

        # Calculate mask statistics
        total_pixels = mask.size
        masked_pixels = (mask == 0).sum()
        unmasked_pixels = (mask == 255).sum()
        mask_percentage = (masked_pixels / total_pixels) * 100

        print(f"Mask statistics:")
        print(f"  Total pixels: {total_pixels}")
        print(f"  Masked pixels: {masked_pixels} ({mask_percentage:.1f}%)")
        print(f"  Unmasked pixels: {unmasked_pixels}")

        # Create visualization
        # Original template in color
        template_bgr = cv2.cvtColor(template, cv2.COLOR_GRAY2BGR)

        # Mask visualization (red overlay on masked areas)
        mask_overlay = template_bgr.copy()
        mask_overlay[mask == 0] = [0, 0, 255]  # Red for masked areas

        # Masked template (what actually gets used for matching)
        masked_template = cv2.bitwise_and(template, template, mask=mask)
        masked_template_bgr = cv2.cvtColor(masked_template, cv2.COLOR_GRAY2BGR)

        # Create combined visualization
        if w > 0 and h > 0:
            # Scale up for better visibility if template is small
            scale = max(1, 200 // min(w, h))

            # Resize all images
            template_scaled = cv2.resize(template_bgr, (w * scale, h * scale), interpolation=cv2.INTER_NEAREST)
            overlay_scaled = cv2.resize(mask_overlay, (w * scale, h * scale), interpolation=cv2.INTER_NEAREST)
            masked_scaled = cv2.resize(masked_template_bgr, (w * scale, h * scale), interpolation=cv2.INTER_NEAREST)

            # Create labels
            label_height = 30
            label = np.zeros((label_height, w * scale, 3), dtype=np.uint8)

            # Combine images horizontally
            combined = np.vstack([
                np.hstack([template_scaled, overlay_scaled, masked_scaled]),
                np.hstack([
                    np.zeros((label_height, w * scale, 3), dtype=np.uint8),
                    np.zeros((label_height, w * scale, 3), dtype=np.uint8),
                    np.zeros((label_height, w * scale, 3), dtype=np.uint8)
                ])
            ])

            # Add text labels
            cv2.putText(combined, "Original", (10, h * scale + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(combined, "Mask Overlay", (w * scale + 10, h * scale + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(combined, "Masked Result", (2 * w * scale + 10, h * scale + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            # Save visualization
            output_path = Path(f"mask_visualization_{template_path.stem}.png")
            cv2.imwrite(str(output_path), combined)
            print(f"  ✅ Saved visualization: {output_path}")

            # Display image if possible
            try:
                cv2.imshow(f"Mask Visualization - {template_path.name}", combined)
                print(f"  👀 Displaying visualization (press any key to continue)")
                cv2.waitKey(0)
                cv2.destroyAllWindows()
            except Exception:
                print(f"  📁 Visualization saved to file (display not available)")

    print(f"\n" + "=" * 50)
    print("Mask visualization complete!")
    print("\nMask Legend:")
    print("  - Original: The source template image")
    print("  - Mask Overlay: Red areas will be ignored during matching")
    print("  - Masked Result: What the template matcher actually sees")
    print("\nThe red areas in the mask overlay show where dynamic text")
    print("(like server names and player counts) will be ignored.")

def test_different_mask_settings():
    """Test how different mask settings affect the result."""
    print("\n" + "=" * 50)
    print("Testing Different Mask Settings")
    print("=" * 50)

    vision = VisionController()
    test_shape = (100, 200)  # height, width

    settings = [
        {"name": "Default", "left": "0.2", "right": "0.8", "top": "0.3", "bottom": "0.7"},
        {"name": "Conservative", "left": "0.3", "right": "0.7", "top": "0.4", "bottom": "0.6"},
        {"name": "Aggressive", "left": "0.1", "right": "0.9", "top": "0.2", "bottom": "0.8"},
        {"name": "Text Only", "left": "0.4", "right": "0.6", "top": "0.45", "bottom": "0.55"},
    ]

    for setting in settings:
        # Set environment variables
        os.environ["GW_SERVER_MASK_LEFT"] = setting["left"]
        os.environ["GW_SERVER_MASK_RIGHT"] = setting["right"]
        os.environ["GW_SERVER_MASK_TOP"] = setting["top"]
        os.environ["GW_SERVER_MASK_BOTTOM"] = setting["bottom"]

        # Create mask
        mask = vision._create_server_button_mask(test_shape)

        # Calculate statistics
        total = mask.size
        masked = (mask == 0).sum()
        percentage = (masked / total) * 100

        print(f"{setting['name']:>12}: {masked:>4} pixels masked ({percentage:>5.1f}%)")

    # Clean up environment variables
    for key in ["GW_SERVER_MASK_LEFT", "GW_SERVER_MASK_RIGHT", "GW_SERVER_MASK_TOP", "GW_SERVER_MASK_BOTTOM"]:
        if key in os.environ:
            del os.environ[key]

if __name__ == "__main__":
    try:
        visualize_mask()
        test_different_mask_settings()
    except KeyboardInterrupt:
        print("\n\nVisualization interrupted by user.")
    except Exception as e:
        print(f"\n\nError during visualization: {e}")

    print("\nVisualization complete!")
