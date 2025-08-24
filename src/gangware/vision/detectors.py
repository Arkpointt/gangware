"""
Pure vision detectors (no IO):

- Header divider detector for the server list: identifies the first strong
  horizontal divider line below the header within a provided ROI.

Usage pattern in controllers:
  1) Use a controller (e.g., VisionController) to capture a BGR frame of the
     Ark window or a sub-ROI.
  2) Pass the appropriate crop (numpy array) into these functions.
  3) Use returned Y offsets to constrain subsequent searches.

All functions here are side-effect free and suitable for unit tests using
"golden" frames.
"""
from __future__ import annotations

from typing import Optional, Tuple
import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def _find_horizontal_lines(binary: np.ndarray, min_len_frac: float = 0.35) -> list[Tuple[int, int, int, int]]:
    """Return horizontal line segments using HoughLinesP on a binary edge/mask image.

    binary: 8-bit single-channel image (edges or morphological mask)
    min_len_frac: minimum line length as a fraction of image width
    """
    h, w = binary.shape[:2]
    min_len = max(10, int(w * float(min_len_frac)))
    try:
        lines = cv2.HoughLinesP(binary, rho=1, theta=np.pi/180, threshold=max(30, min_len//6),
                                minLineLength=min_len, maxLineGap=8)
    except Exception:
        lines = None
    out: list[Tuple[int, int, int, int]] = []
    if lines is not None:
        for line in lines.reshape(-1, 4):
            x1, y1, x2, y2 = map(int, line)
            # Keep near-horizontal segments (|dy| small relative to |dx|)
            dx, dy = abs(x2 - x1), abs(y2 - y1)
            if dx < min_len:
                continue
            if dy <= max(1, dx // 20):  # ~ |slope| <= 0.05
                out.append((x1, y1, x2, y2))
    return out


def detect_header_bottom_y(crop_bgr: np.ndarray) -> Optional[int]:
    """Detect the first strong horizontal divider below a header within crop_bgr.

    Returns the Y coordinate (int) relative to crop_bgr's top for the bottom of
    the header area (i.e., the first significant horizontal divider), or None if
    no reliable candidate is found.

    Heuristics:
    - Focus on the upper half of the crop (headers live near top of list panel)
    - Combine Canny edges and a horizontal morphological filter to enhance lines
    - Use HoughLinesP to extract long, near-horizontal segments
    - Return the smallest Y among strong lines that appear near the top band
    """
    if crop_bgr is None or crop_bgr.size == 0:
        return None
    try:
        gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    except Exception:
        return None
    h, w = gray.shape[:2]
    if h < 20 or w < 40:
        return None

    # Restrict to upper portion; keep enough height to tolerate UI shifts
    roi_top = 0
    roi_bottom = max(10, int(h * 0.55))
    roi = gray[roi_top:roi_bottom, :]

    # Enhance horizontal structures: slight blur -> edges -> horizontal morph
    try:
        blur = cv2.GaussianBlur(roi, (3, 3), 0)
    except Exception:
        blur = roi
    try:
        edges = cv2.Canny(blur, 40, 120)
    except Exception:
        edges = cv2.Canny(roi, 60, 160)

    # Morphological horizontal emphasis
    try:
        k = max(9, w // 20)  # kernel width scales with image width
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, 3))
        horiz = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=1)
    except Exception:
        horiz = edges

    # Find long horizontal line segments
    lines = _find_horizontal_lines(horiz, min_len_frac=0.30)
    if not lines:
        return None

    # Score lines by length and proximity to the top
    scored: list[Tuple[float, Tuple[int, int, int, int]]] = []
    for (x1, y1, x2, y2) in lines:
        y = int(0.5 * (y1 + y2))
        length = float(abs(x2 - x1))
        # Prefer lines closer to the top, but still meaningful in length
        score = length - 0.5 * y  # longer and nearer to top is better
        scored.append((score, (x1, y1, x2, y2)))

    scored.sort(key=lambda t: t[0], reverse=True)
    # Take the top candidate's Y
    best = scored[0][1]
    y_best = int(0.5 * (best[1] + best[3]))
    return int(roi_top + y_best)


def detect_header_bottom_abs(full_bgr: np.ndarray, roi_rect: Tuple[int, int, int, int]) -> Optional[int]:
    """Convenience wrapper to return absolute Y within full_bgr.

    roi_rect: (left, top, right, bottom) in full_bgr coordinate space
    """
    if full_bgr is None or full_bgr.size == 0:
        return None
    L, T, R, B = map(int, roi_rect)
    if R <= L or B <= T:
        return None
    L = max(0, L)
    T = max(0, T)
    R = min(full_bgr.shape[1], R)
    B = min(full_bgr.shape[0], B)
    if R <= L or B <= T:
        return None
    crop = full_bgr[T:B, L:R]
    rel_y = detect_header_bottom_y(crop)
    if rel_y is None:
        return None
    return int(T + rel_y)
