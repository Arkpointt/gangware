"""
Template matching strategies (multi-scale, multi-variant) extracted from the controller.

This module provides pure functions that take numpy arrays and return scores
and match metadata. Controllers can compose these to implement feature flows.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import logging
import cv2
import numpy as np

from .preprocess import screen_variants, tpl_variants, resize_tpl

logger = logging.getLogger(__name__)


def match_methods(
    modes: List[str],
    screen_v: Dict[str, np.ndarray],
    tpl_v: Dict[str, np.ndarray],
    scale: float,
) -> Tuple[float, Optional[Tuple[int, int]], Optional[Dict]]:
    """Try multiple method variants and return best score and metadata."""
    best_local_score = -1.0
    best_local_loc = None
    best_local_meta = None
    for m in modes:
        scr = screen_v.get("edges" if m == "edges_center" else m)
        tp = tpl_v.get(m)
        if scr is None or tp is None:
            continue
        try:
            res = cv2.matchTemplate(scr, tp, cv2.TM_CCOEFF_NORMED)
            _, sc, _, loc = cv2.minMaxLoc(res)
            if sc > best_local_score:
                best_local_score = sc
                best_local_loc = loc
                best_local_meta = {"method": m, "scale": float(scale)}
        except Exception:
            continue
    return best_local_score, best_local_loc, best_local_meta


def best_match_multi(
    screenshot_gray: np.ndarray,
    template_gray: np.ndarray,
    scales: List[float],
    modes: Optional[List[str]] = None,
):
    """Return (score, loc, (w,h), meta) for best match across strategies and scales.

    modes: list in {"gray_blur", "gray_eq", "edges", "gray_clahe", "grad", "edges_center"}
    """
    if not modes:
        modes = ["gray_blur", "gray_eq", "edges"]
    screen_v = screen_variants(screenshot_gray)

    best_score = -1.0
    best_loc = None
    best_wh = None
    best_meta = None

    for s in scales:
        try:
            tpl_scaled = resize_tpl(template_gray, s)
            if tpl_scaled.shape[0] < 8 or tpl_scaled.shape[1] < 8:
                continue
            tpl_v = tpl_variants(tpl_scaled)
            sc, loc, meta = match_methods(modes, screen_v, tpl_v, s)
            if sc > best_score and loc is not None:
                best_score = sc
                best_loc = loc
                best_wh = (tpl_scaled.shape[1], tpl_scaled.shape[0])
                best_meta = meta
        except Exception:
            continue
    return best_score, best_loc, best_wh, (best_meta or {})
