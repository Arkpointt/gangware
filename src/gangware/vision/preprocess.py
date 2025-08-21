"""
Pure image preprocessing and template preparation utilities.

This module contains only stateless, side-effect-free functions used by
vision detectors. Extracted from the monolithic controller to enable unit
testing and reuse.

Logging: Functions here avoid heavy logging for performance; callers can
wrap them and log as needed at DEBUG level.
"""
from __future__ import annotations

from typing import Dict, Tuple
import os
import logging
import cv2
import numpy as np

logger = logging.getLogger(__name__)


def edges(img: np.ndarray) -> np.ndarray:
    """Robust Canny edge extraction with adaptive thresholds.

    Falls back to fixed thresholds on error. Pure function.
    """
    try:
        v = float(np.median(img))
        lo = int(max(0, 0.66 * v))
        hi = int(min(255, 1.33 * v))
        return cv2.Canny(img, lo, hi)
    except Exception:
        return cv2.Canny(img, 50, 150)


def screen_variants(gray: np.ndarray) -> Dict[str, np.ndarray]:
    """Compute multiple illumination-invariant representations of the screen.

    Returns a dict with keys:
    - gray_blur: lightly denoised grayscale
    - gray_eq: global histogram equalization
    - gray_clahe: local contrast-limited equalization
    - edges: Canny edges with adaptive thresholds
    - grad: gradient magnitude (normalized to 8-bit)
    """
    try:
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
    except Exception:
        blur = gray
    try:
        eq = cv2.equalizeHist(gray)
    except Exception:
        eq = gray
    try:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        cla = clahe.apply(gray)
    except Exception:
        cla = eq
    edg = edges(gray)
    try:
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        mag = cv2.magnitude(gx, gy)
        mmin, mmax = float(mag.min()), float(mag.max())
        if mmax > mmin:
            grad = cv2.convertScaleAbs((mag - mmin) * (255.0 / (mmax - mmin)))
        else:
            grad = np.zeros_like(gray)
    except Exception:
        grad = edg
    return {"gray_blur": blur, "gray_eq": eq, "gray_clahe": cla, "edges": edg, "grad": grad}


def make_tile_mask(shape: Tuple[int, int], left: float = 0.08, right: float = 0.08, top: float = 0.22, bottom: float = 0.18) -> np.ndarray:
    """Binary mask keeping the inner area of an item tile (ignores digits/shield).

    shape: (h, w)
    returns uint8 mask in {0,255}
    """
    h, w = shape
    mask = np.zeros((h, w), np.uint8)
    x0 = int(w * left)
    x1 = int(w * (1.0 - right))
    y0 = int(h * top)
    y1 = int(h * (1.0 - bottom))
    if y1 > y0 and x1 > x0:
        mask[y0:y1, x0:x1] = 255
    return mask


def apply_mask(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    try:
        return cv2.bitwise_and(img, img, mask=mask)
    except Exception:
        return img


def resize_tpl(tpl: np.ndarray, scale: float) -> np.ndarray:
    """Resize template with appropriate interpolation, clamped to min size 8x8."""
    h, w = tpl.shape[:2]
    if abs(scale - 1.0) < 1e-6:
        return tpl
    nh, nw = max(8, int(h * scale)), max(8, int(w * scale))
    return cv2.resize(tpl, (nw, nh), interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC)


def tpl_variants(tpl: np.ndarray) -> Dict[str, np.ndarray]:
    """Create multiple template variants to match under diverse conditions.

    Includes gray_blur, gray_eq, gray_clahe, edges, edges_center (masked center), grad.
    """
    try:
        blur = cv2.GaussianBlur(tpl, (3, 3), 0)
    except Exception:
        blur = tpl
    try:
        eq = cv2.equalizeHist(tpl)
    except Exception:
        eq = tpl
    try:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        cla = clahe.apply(tpl)
    except Exception:
        cla = eq
    edg = edges(tpl)
    # Gradient magnitude
    try:
        gx = cv2.Sobel(tpl, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(tpl, cv2.CV_32F, 0, 1, ksize=3)
        mag = cv2.magnitude(gx, gy)
        mmin, mmax = float(mag.min()), float(mag.max())
        if mmax > mmin:
            grad = cv2.convertScaleAbs((mag - mmin) * (255.0 / (mmax - mmin)))
        else:
            grad = edg
    except Exception:
        grad = edg
    # Center mask for inventory tiles; harmless for others
    try:
        mask = make_tile_mask(tpl.shape[:2])
        edges_center = apply_mask(edg, mask)
    except Exception:
        edges_center = edg
    return {"gray_blur": blur, "gray_eq": eq, "gray_clahe": cla, "edges": edg, "edges_center": edges_center, "grad": grad}


def create_server_button_mask(template_shape: Tuple[int, int]) -> np.ndarray:
    """Create a mask for server button templates.

    Masks out the center text area where dynamic content appears, focusing on
    borders. Tunable via environment variables:
    - GW_SERVER_MASK_LEFT (default 0.2)
    - GW_SERVER_MASK_RIGHT (default 0.8)
    - GW_SERVER_MASK_TOP (default 0.3)
    - GW_SERVER_MASK_BOTTOM (default 0.7)
    """
    h, w = template_shape
    mask = np.ones((h, w), dtype=np.uint8) * 255

    try:
        left_pct = float(os.environ.get("GW_SERVER_MASK_LEFT", "0.2"))
        right_pct = float(os.environ.get("GW_SERVER_MASK_RIGHT", "0.8"))
        top_pct = float(os.environ.get("GW_SERVER_MASK_TOP", "0.3"))
        bottom_pct = float(os.environ.get("GW_SERVER_MASK_BOTTOM", "0.7"))
    except (ValueError, TypeError):
        left_pct, right_pct, top_pct, bottom_pct = 0.2, 0.8, 0.3, 0.7

    text_left = int(w * left_pct)
    text_right = int(w * right_pct)
    text_top = int(h * top_pct)
    text_bottom = int(h * bottom_pct)

    text_left = max(0, min(text_left, w - 1))
    text_right = max(text_left + 1, min(text_right, w))
    text_top = max(0, min(text_top, h - 1))
    text_bottom = max(text_top + 1, min(text_bottom, h))

    mask[text_top:text_bottom, text_left:text_right] = 0
    return mask
