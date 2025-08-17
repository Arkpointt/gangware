
"""Vision system helpers used by the app.

This module provides a minimal VisionController that captures the
primary monitor and performs template matching using OpenCV. The
implementation is intentionally small and defensive so tests and
static analysis are straightforward.
"""

from typing import Optional, Tuple

import cv2
import numpy as np
import mss


class VisionController:
    """Main class for visual perception and template matching."""

    def __init__(self) -> None:
        self.sct = mss.mss()

    def find_template(self, template_path: str, confidence: float = 0.8) -> Optional[Tuple[int, int]]:
        """Find the template on the primary monitor.

        Args:
            template_path: Filesystem path to the template image.
            confidence: Matching threshold in [0.0, 1.0].

        Returns:
            Tuple of (center_x, center_y) when found, otherwise None.
        """
        # Capture the primary monitor as BGRA and convert to gray
        monitor = self.sct.monitors[1]
        screenshot = np.array(self.sct.grab(monitor))
        screenshot_gray = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2GRAY)

        # Load template and validate
        template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
        if template is None:
            raise FileNotFoundError(f"Template image not found: {template_path}")

        # Perform template matching
        result = cv2.matchTemplate(screenshot_gray, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val < confidence:
            return None

        t_height, t_width = template.shape
        center_x = max_loc[0] + t_width // 2
        center_y = max_loc[1] + t_height // 2
    return center_x, center_y






