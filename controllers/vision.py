
"""
Vision System Module
Handles all computer vision tasks for GUI perception.
"""


import cv2
import numpy as np
import mss


class VisionController:
    """
    Main class for visual perception and template matching.
    """
    def __init__(self):
        self.sct = mss.mss()
        # Additional initialization as needed

    def find_template(self, template_path, confidence=0.8):
        """
        Finds the template on the screen using OpenCV.
        Args:
            template_path: Path to the template image file.
            confidence: Matching confidence threshold (default 0.8).
        Returns:
            (center_x, center_y) of match or None if not found.
        """
        # Capture the screen
        monitor = self.sct.monitors[1]  # Primary monitor
        screenshot = np.array(self.sct.grab(monitor))
        screenshot_gray = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2GRAY)

        # Load template
        template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
        if template is None:
            raise FileNotFoundError(f"Template image not found: {template_path}")

        # Template matching
        result = cv2.matchTemplate(screenshot_gray, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= confidence:
            # Calculate center coordinates of the match
            t_height, t_width = template.shape
            center_x = max_loc[0] + t_width // 2
            center_y = max_loc[1] + t_height // 2
            return center_x, center_y

        return None
 

