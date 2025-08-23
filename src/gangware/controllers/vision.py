"""Vision helpers used by the app.

Responsibility:
- Thin orchestration for screen capture (IO), region selection, and calling
  pure detectors/matching utilities from gangware.vision.
- Maintain public API for callers (VisionController and its methods).
- Centralize thresholds/scales via gangware.config.vision.
- Structured logging: INFO for state transitions, DEBUG for scores/ROIs.
- Save lightweight debug artifacts only on detection failure within the
  active log session directory (see core.logging_setup).

Detectors themselves remain pure functions in gangware.vision.* modules.
"""
from __future__ import annotations

from typing import Optional, Tuple
from pathlib import Path
import logging
import os
import threading
import time

import cv2
import numpy as np
import mss

from ..core.logging_setup import get_artifacts_dir
from ..config.vision import (
    FAST_SCALES,
    FULL_SCALES,
    SERVER_SCALES_DEFAULT,
    BLACK_STD_SKIP,
    FAST_ONLY,
    PERF_ENABLED,
    INVENTORY_ITEM_THRESHOLD,
    ARTIFACT_MAX_DIM,
)
from ..vision import (
    edges,
    make_tile_mask,
    apply_mask,
    resize_tpl,
    create_server_button_mask,
    best_match_multi,
)
from ..io.win import get_ark_window_region


def _ark_window_region() -> Optional[dict]:
    """Return region of the Ark window if it's the foreground window on Windows.

    Delegates to io.win to keep platform-specific code isolated.
    """
    return get_ark_window_region()


class VisionController:
    """Main class for visual perception and template matching.

    This class performs IO (screen capture) and composes pure vision utilities
    to implement detection workflows.
    """

    def __init__(self) -> None:
        self._tls = threading.local()
        self._last_debug = {}
        self._last_pos: Optional[Tuple[int, int]] = None
        self._last_perf = {}
        self.search_roi: Optional[dict] = None
        self.ui_scale: float = 1.0
        self.ui_scale_ts: float = 0.0  # timestamp when scale was last set

    # --------------------------- screen capture ---------------------------
    def _get_sct(self, force_new: bool = False):
        sct = getattr(self._tls, "sct", None)
        if force_new or sct is None:
            try:
                if sct is not None and hasattr(sct, "close"):
                    sct.close()
            except Exception:
                pass
            sct = mss.mss()
            try:
                setattr(self._tls, "sct", sct)
            except Exception:
                pass
        return sct

    def _safe_grab(self, region):
        sct = self._get_sct()
        try:
            return sct.grab(region)
        except AttributeError:
            sct = self._get_sct(force_new=True)
            return sct.grab(region)

    def capture_region_bgr(self, region: dict) -> np.ndarray:
        """Capture a BGR frame for an absolute region dict {left, top, width, height}."""
        logger = logging.getLogger(__name__)
        t0 = time.perf_counter()
        frame = np.array(self._safe_grab(region))  # BGRA
        t1 = time.perf_counter()
        if PERF_ENABLED or logger.isEnabledFor(logging.DEBUG):
            try:
                logger.debug("vision: grab (region) %.1fms region=%s", (t1 - t0) * 1000.0, str(region))
            except Exception:
                pass
        return frame[:, :, :3]

    # --------------------------- public API ---------------------------
    def find_template(self, template_path: str, confidence: float = 0.8) -> Optional[Tuple[int, int]]:
        """Find a template by multiscale matching within Ark window or full screen.

        Returns absolute screen coordinates (x, y) of the match center when
        found, otherwise None.
        """
        logger = logging.getLogger(__name__)

        sct = self._get_sct()
        # Prefer Ark window; fallback to virtual screen box
        r0 = _ark_window_region()
        base_region = r0 if r0 is not None else sct.monitors[0]

        # Apply ROI override: manual search ROI > env > inventory ROI
        env_roi = os.environ.get("GW_VISION_ROI", "").strip()
        roi_override = None
        if isinstance(self.search_roi, dict):
            roi_override = self.search_roi
        elif env_roi:
            try:
                parts = [int(p.strip()) for p in env_roi.split(",")]
                if len(parts) == 4:
                    roi_override = {"left": parts[0], "top": parts[1], "width": parts[2], "height": parts[3]}
            except Exception:
                roi_override = None
        if roi_override is None:
            inv = getattr(self, "inventory_roi", None)
            if isinstance(inv, dict) and inv.get("width", 0) > 0 and inv.get("height", 0) > 0:
                roi_override = inv
        # Optional sub-ROI relative to inventory ROI (env: GW_INV_SUBROI="l,t,w,h" in 0..1)
        if isinstance(roi_override, dict):
            sub_env = os.environ.get("GW_INV_SUBROI", "").strip()
            if sub_env and self.search_roi is None:  # don't override explicit manual ROI
                try:
                    parts = [float(p.strip()) for p in sub_env.split(",")]
                    if len(parts) == 4:
                        rl, rt, rw, rh = [max(0.0, min(1.0, v)) for v in parts]
                        L = int(roi_override.get("left", 0))
                        T = int(roi_override.get("top", 0))
                        W = int(roi_override.get("width", 0))
                        H = int(roi_override.get("height", 0))
                        sub = {
                            "left": L + int(W * rl),
                            "top": T + int(H * rt),
                            "width": max(0, int(W * rw)),
                            "height": max(0, int(H * rh)),
                        }
                        roi_override = sub
                except Exception:
                    pass
        if isinstance(roi_override, dict):
            base_region = {k: int(roi_override[k]) for k in ("left", "top", "width", "height") if k in roi_override}

        # Candidate regions: small window around last known pos, then base region
        regions = []
        lp = getattr(self, "_last_pos", None)
        if lp is not None:
            cx, cy = int(lp[0]), int(lp[1])
            left0, top0 = int(base_region["left"]), int(base_region["top"])
            right0 = left0 + int(base_region["width"])
            bottom0 = top0 + int(base_region["height"])
            if left0 <= cx <= right0 and top0 <= cy <= bottom0:
                roi_w, roi_h = 360, 140
                roi_left = max(left0, min(cx - roi_w // 2, right0 - roi_w))
                roi_top = max(top0, min(cy - roi_h // 2, bottom0 - roi_h))
                regions.append({"left": int(roi_left), "top": int(roi_top), "width": int(roi_w), "height": int(roi_h)})
        regions.append(base_region)

        # Load template
        template_gray = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
        if template_gray is None:
            raise FileNotFoundError(f"Template image not found: {template_path}")
        tpl_h, tpl_w = template_gray.shape[:2]

        fast_scales = FAST_SCALES
        full_scales = FULL_SCALES
        fast_scales_n = len(fast_scales)
        slow_scales_n = len(full_scales)
        fast_only = FAST_ONLY

        best_overall = -1.0
        best_overall_region = None
        best_overall_meta = None

        perf_enabled = PERF_ENABLED or logger.isEnabledFor(logging.DEBUG)
        t_call0 = time.perf_counter()

        for region in regions:
            t_grab0 = time.perf_counter()
            grab = np.array(self._safe_grab(region))  # BGRA
            t_grab1 = time.perf_counter()
            screenshot_gray = cv2.cvtColor(grab, cv2.COLOR_BGRA2GRAY)
            t_gray1 = time.perf_counter()
            std_val = float(screenshot_gray.std())
            # Skip likely-black frames (exclusive fullscreen)
            if std_val < BLACK_STD_SKIP:
                if perf_enabled:
                    # Keep minimal perf info when skipping
                    try:
                        self._last_perf = {
                            "grab_ms": (t_grab1 - t_grab0) * 1000.0,
                            "gray_ms": (t_gray1 - t_grab1) * 1000.0,
                            "skipped_black": True,
                            "std": std_val,
                            "region": dict(region),
                        }
                    except Exception:
                        pass
                logger.debug("vision: skipped region %s due to near-black frame (std=%.3f)", str(region), std_val)
                continue

            # Fast pass: few scales, emphasize illumination-invariant modes
            t_fast0 = time.perf_counter()
            best_score, best_loc, best_wh, meta = best_match_multi(
                screenshot_gray,
                template_gray,
                fast_scales,
                modes=["edges", "grad", "gray_clahe"],
            )
            t_fast1 = time.perf_counter()
            logger.debug("vision: fast pass best_score=%.3f meta=%s", float(best_score), str(meta))

            if best_score >= confidence and best_loc is not None and best_wh is not None:
                t_width, t_height = best_wh
                center_x = int(best_loc[0] + t_width // 2 + int(region["left"]))
                center_y = int(best_loc[1] + t_height // 2 + int(region["top"]))
                try:
                    self._last_pos = (center_x, center_y)
                except Exception:
                    pass
                if perf_enabled:
                    t_call1 = time.perf_counter()
                    try:
                        self._last_perf = {
                            "total_ms": (t_call1 - t_call0) * 1000.0,
                            "grab_ms": (t_grab1 - t_grab0) * 1000.0,
                            "gray_ms": (t_gray1 - t_grab1) * 1000.0,
                            "fast_ms": (t_fast1 - t_fast0) * 1000.0,
                            "roi_w": int(base_region.get("width", 0)),
                            "roi_h": int(base_region.get("height", 0)),
                            "tpl_wh": (int(tpl_w), int(tpl_h)),
                            "fast_scales_n": int(fast_scales_n),
                            "slow_scales_n": int(slow_scales_n),
                            "region": dict(region),
                            "path": str(template_path),
                            "phase": "fast",
                        }
                    except Exception:
                        self._last_perf = {"total_ms": (t_call1 - t_call0) * 1000.0, "phase": "fast"}
                return center_x, center_y

            if best_score > best_overall:
                best_overall = best_score
                best_overall_region = region
                best_overall_meta = meta

            # Slow fallback: full scales and broader methods (skip if fast-only mode is enabled)
            if not fast_only:
                t_slow0 = time.perf_counter()
                slow_score, slow_loc, slow_wh, slow_meta = best_match_multi(
                    screenshot_gray,
                    template_gray,
                    full_scales,
                    modes=["gray_blur", "gray_eq", "gray_clahe", "edges", "grad"],
                )
                t_slow1 = time.perf_counter()
                logger.debug("vision: slow pass best_score=%.3f meta=%s", float(slow_score), str(slow_meta))
                if slow_score >= confidence and slow_loc is not None and slow_wh is not None:
                    t_width, t_height = slow_wh
                    center_x = int(slow_loc[0] + t_width // 2 + int(region["left"]))
                    center_y = int(slow_loc[1] + t_height // 2 + int(region["top"]))
                    try:
                        self._last_pos = (center_x, center_y)
                    except Exception:
                        pass
                    if perf_enabled:
                        t_call1 = time.perf_counter()
                        try:
                            self._last_perf = {
                                "total_ms": (t_call1 - t_call0) * 1000.0,
                                "grab_ms": (t_grab1 - t_grab0) * 1000.0,
                                "gray_ms": (t_gray1 - t_grab1) * 1000.0,
                                "fast_ms": (t_fast1 - t_fast0) * 1000.0,
                                "slow_ms": (t_slow1 - t_slow0) * 1000.0,
                                "roi_w": int(base_region.get("width", 0)),
                                "roi_h": int(base_region.get("height", 0)),
                                "tpl_wh": (int(tpl_w), int(tpl_h)),
                                "fast_scales_n": int(fast_scales_n),
                                "slow_scales_n": int(slow_scales_n),
                                "region": dict(region),
                                "path": str(template_path),
                                "phase": "slow",
                            }
                        except Exception:
                            self._last_perf = {"total_ms": (t_call1 - t_call0) * 1000.0, "phase": "slow"}
                    return center_x, center_y
                if slow_score > best_overall:
                    best_overall = slow_score
                    best_overall_region = region
                    best_overall_meta = slow_meta

        # Save diagnostics for caller
        try:
            self._last_debug = {
                "best_score": float(best_overall),
                "region": dict(best_overall_region) if best_overall_region else None,
                "meta": dict(best_overall_meta) if isinstance(best_overall_meta, dict) else None,
            }
        except Exception:
            self._last_debug = {"best_score": float(best_overall)}

        # Persist debug artifacts on miss: downscaled screenshot and template
        try:
            art_dir = get_artifacts_dir(type("_Cfg", (), {"config_path": Path.home() / "AppData" / "Roaming" / "Gangware" / "config.ini"})())
            # Save last screenshot of best region
            if best_overall_region is not None:
                try:
                    grab = np.array(self._safe_grab(best_overall_region))
                    bgr = grab[:, :, :3]
                    # Downscale for manageable size
                    h, w, _ = bgr.shape
                    scale = ARTIFACT_MAX_DIM / max(1, max(h, w))
                    if scale < 1.0:
                        bgr = cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
                    cv2.imwrite(str(Path(art_dir) / "last_screenshot.png"), bgr)
                except Exception:
                    pass
            # Save template used
            try:
                tpl_color = cv2.imread(template_path, cv2.IMREAD_COLOR)
                if tpl_color is not None:
                    cv2.imwrite(str(Path(art_dir) / "last_template.png"), tpl_color)
            except Exception:
                pass
        except Exception:
            pass

        if PERF_ENABLED or logger.isEnabledFor(logging.DEBUG):
            t_call1 = time.perf_counter()
            try:
                self._last_perf = {
                    "total_ms": (t_call1 - t_call0) * 1000.0,
                    "regions": [],
                    "base_region": dict(base_region) if isinstance(base_region, dict) else None,
                    "roi_w": int(base_region.get("width", 0)) if isinstance(base_region, dict) else 0,
                    "roi_h": int(base_region.get("height", 0)) if isinstance(base_region, dict) else 0,
                    "fast_scales_n": int(fast_scales_n),
                    "slow_scales_n": int(slow_scales_n),
                    "best_overall": float(best_overall),
                    "path": str(template_path),
                    "phase": "miss",
                }
            except Exception:
                self._last_perf = {"total_ms": (t_call1 - t_call0) * 1000.0, "phase": "miss"}
        logger.info("vision: no match. best_score=%.3f meta=%s region=%s", float(best_overall), str(best_overall_meta), str(best_overall_region))
        return None

    def find_server_template_enhanced(self, template_path: str, confidence: float = 0.8) -> Optional[Tuple[int, int]]:
        """Enhanced server detection with masking and multiscale search.

        Specifically designed for click_server and click_server2 templates to handle:
        - Different UI scales and resolutions
        - Dynamic text areas that should be ignored (when supported)
        - Light preprocessing for better matching
        - Robust fallback to basic template matching

        Returns absolute screen coordinates (x, y) of the match center when found,
        otherwise None.
        """
        logger = logging.getLogger(__name__)
        logger.debug("vision: enhanced server detection for %s with confidence=%.3f", template_path, confidence)

        # Establish base region similar to find_template
        sct = self._get_sct()
        r0 = _ark_window_region()
        base_region = r0 if r0 is not None else sct.monitors[0]

        # Optional manual ROI override (env or self.search_roi)
        env_roi = os.environ.get("GW_VISION_ROI", "").strip()
        roi_override = None
        if isinstance(self.search_roi, dict):
            roi_override = self.search_roi
        elif env_roi:
            try:
                parts = [int(p.strip()) for p in env_roi.split(",")]
                if len(parts) == 4:
                    roi_override = {"left": parts[0], "top": parts[1], "width": parts[2], "height": parts[3]}
            except Exception:
                roi_override = None
        if isinstance(roi_override, dict):
            base_region = {k: int(roi_override[k]) for k in ("left", "top", "width", "height") if k in roi_override}

        regions = [base_region]

        # Load template as grayscale
        template_gray = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
        if template_gray is None:
            raise FileNotFoundError(f"Template image not found: {template_path}")

        # Default multiscale range; can be extended downwards dynamically if template doesn't fit
        scales = list(SERVER_SCALES_DEFAULT)
        logger.debug("vision: server detection using scales: %s", scales)

        best_score = -1.0
        best_location: Optional[Tuple[int, int]] = None
        best_scale: float = 1.0
        best_region = None

        for region in regions:
            logger.debug("vision: searching region %s", region)
            try:
                grab = np.array(self._safe_grab(region))  # BGRA
                screenshot_gray = cv2.cvtColor(grab, cv2.COLOR_BGRA2GRAY)
            except Exception as e:
                logger.debug("vision: failed to grab region %s: %s", region, e)
                continue

            # Skip near-black frames (exclusive fullscreen)
            if float(screenshot_gray.std()) < BLACK_STD_SKIP:
                logger.debug("vision: skipping near-black frame")
                continue

            # Preprocess screenshot once per region
            try:
                screenshot_processed = cv2.GaussianBlur(screenshot_gray, (3, 3), 0)
            except Exception:
                screenshot_processed = screenshot_gray

            # Ensure the scale list allows the template to fit inside the screenshot
            try:
                th0, tw0 = template_gray.shape[:2]
                sh, sw = screenshot_gray.shape[:2]
                max_fit_scale = min(sw / max(1, tw0), sh / max(1, th0))
                if max_fit_scale < scales[0]:
                    extra = []
                    s = max(0.4, round(max_fit_scale * 0.95, 2))
                    while s < scales[0]:
                        extra.append(round(s, 2))
                        s = round(s + 0.05, 2)
                    if extra:
                        scales = sorted(set(extra + scales))
                        logger.debug("vision: extended scales to fit: %s", scales)
            except Exception:
                pass

            for scale in scales:
                try:
                    scaled_template = resize_tpl(template_gray, scale)
                    th, tw = scaled_template.shape[:2]
                    if th < 8 or tw < 8:
                        continue
                    if th > screenshot_processed.shape[0] or tw > screenshot_processed.shape[1]:
                        continue

                    try:
                        scaled_template_processed = cv2.GaussianBlur(scaled_template, (3, 3), 0)
                    except Exception:
                        scaled_template_processed = scaled_template

                    # Build mask for the scaled template to ignore central text area
                    try:
                        base_mask = create_server_button_mask((th, tw))
                        mask = np.ascontiguousarray(base_mask)
                    except Exception:
                        mask = None

                    # Use a mask-capable method when possible; fall back to unmasked
                    try:
                        if mask is not None:
                            res = cv2.matchTemplate(
                                screenshot_processed,
                                scaled_template_processed,
                                cv2.TM_CCORR_NORMED,
                                mask=mask,
                            )
                        else:
                            res = cv2.matchTemplate(
                                screenshot_processed,
                                scaled_template_processed,
                                cv2.TM_CCORR_NORMED,
                            )
                        _, max_score, _, max_loc = cv2.minMaxLoc(res)
                    except Exception as e:
                        logger.debug("vision: masked match failed at scale %.2f: %s", scale, e)
                        try:
                            res = cv2.matchTemplate(
                                screenshot_gray,
                                scaled_template,
                                cv2.TM_CCORR_NORMED,
                            )
                            _, max_score, _, max_loc = cv2.minMaxLoc(res)
                        except Exception as e2:
                            logger.debug("vision: unmasked fallback failed at scale %.2f: %s", scale, e2)
                            continue

                    if float(max_score) > best_score:
                        best_score = float(max_score)
                        best_location = (int(max_loc[0]), int(max_loc[1]))
                        best_scale = float(scale)
                        best_region = region
                        logger.debug("vision: match at scale %.2f, score=%.3f", scale, best_score)
                        if best_score >= 0.9:
                            logger.debug("vision: excellent match found at scale %.2f, score=%.3f", scale, best_score)
                            break
                except Exception as e:
                    logger.debug("vision: error at scale %.2f: %s", scale, e)
                    continue

            if best_score >= confidence:
                break

        if best_score >= confidence and best_location is not None and best_region is not None:
            # Calculate match center in absolute coords
            scaled_h = int(template_gray.shape[0] * best_scale)
            scaled_w = int(template_gray.shape[1] * best_scale)
            center_x = int(best_location[0] + scaled_w // 2 + int(best_region["left"]))
            center_y = int(best_location[1] + scaled_h // 2 + int(best_region["top"]))
            logger.info(
                "vision: enhanced server detection SUCCESS. score=%.3f scale=%.2f pos=(%d,%d)",
                best_score,
                best_scale,
                center_x,
                center_y,
            )
            return center_x, center_y

        logger.info(
            "vision: enhanced server detection FAILED. best_score=%.3f (required=%.3f)",
            float(best_score),
            float(confidence),
        )
        return None

    def _create_server_button_mask(self, template_shape: Tuple[int, int]) -> np.ndarray:
        """Backward-compatible wrapper for tests; delegates to pure function."""
        return create_server_button_mask(template_shape)

    def get_last_debug(self):
        try:
            return dict(self._last_debug)
        except Exception:
            return {}

    def get_last_perf(self):
        try:
            return dict(self._last_perf)
        except Exception:
            return {}

    # ---------------- Inventory ROI calibration from search bar ----------------
    def calibrate_inventory_roi_from_search(self, search_template_path: str, min_conf: float = 0.75):
        """Locate the search bar robustly, derive inventory grid ROI, and store it.

        Uses a multi-scale matcher similar to find_template so it works under
        4K/UI scaling. Returns a region dict or None if not found.
        """
        logger = logging.getLogger(__name__)
        sct = self._get_sct()
        base_region = _ark_window_region() or sct.monitors[0]
        t0 = time.perf_counter()
        frame = np.array(self._safe_grab(base_region))  # BGRA
        t1 = time.perf_counter()
        if PERF_ENABLED or logger.isEnabledFor(logging.DEBUG):
            logger.debug("vision: grab (calibrate) %.1fms region=%s", (t1 - t0) * 1000.0, str(base_region))

        bgr = frame[:, :, :3]
        screenshot_gray = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
        tpl_gray = cv2.imread(search_template_path, cv2.IMREAD_GRAYSCALE)
        if tpl_gray is None:
            raise FileNotFoundError(search_template_path)

        # Focused scale set around detected UI scale if available, else broader fallback
        if hasattr(self, "ui_scale") and self.ui_scale and abs(self.ui_scale - 1.0) < 0.5:
            base_scale = float(self.ui_scale)
            fast_scales = [round(base_scale + 0.05 * i, 2) for i in range(-2, 3)]
            logger.debug("vision: calibrate using fast scales around %.2f: %s", base_scale, fast_scales)
        else:
            fast_scales = [round(0.7 + 0.1 * i, 2) for i in range(11)]  # 0.7..1.7 in 0.1 steps
            logger.debug("vision: calibrate using fallback scales: %s", fast_scales)

        cal_start = time.perf_counter()
        score, loc, wh, _meta = best_match_multi(screenshot_gray, tpl_gray, fast_scales)
        cal_time = (time.perf_counter() - cal_start) * 1000.0
        logger.info("vision: calibrate_roi matching took %.1fms with %d scales", cal_time, len(fast_scales))
        if score < float(min_conf) or loc is None or wh is None:
            return None

        # Cache UI scale based on matched search bar width
        try:
            tpl_w0 = int(tpl_gray.shape[1])
            matched_w = int(wh[0])
            s = max(0.5, min(2.0, matched_w / max(1, tpl_w0)))
            self.ui_scale = float(s)
            self.ui_scale_ts = time.time()
        except Exception:
            self.ui_scale = 1.0

        x, y = int(loc[0]), int(loc[1])
        w, h = int(wh[0]), int(wh[1])
        rect_rel = (x, y, w, h)

        # Derive ROI within the same frame, then convert to absolute coords
        l_rel, t_rel, r_rel, b_rel = self._derive_inventory_roi_from_search(bgr, rect_rel)
        left_abs = int(base_region["left"]) + int(l_rel)
        top_abs = int(base_region["top"]) + int(t_rel)
        right_abs = int(base_region["left"]) + int(r_rel)
        bottom_abs = int(base_region["top"]) + int(b_rel)
        roi = {"left": left_abs, "top": top_abs, "width": max(0, right_abs - left_abs), "height": max(0, bottom_abs - top_abs)}
        try:
            if roi.get("width", 0) <= 0 or roi.get("height", 0) <= 0:
                return None
        except Exception:
            return None
        self.inventory_roi = roi
        return dict(self.inventory_roi)

    def grab_inventory_bgr(self):
        """Grab and return (BGR, region) for the inventory ROI when available, else Ark/window."""
        logger = logging.getLogger(__name__)
        sct = self._get_sct()
        roi = getattr(self, "inventory_roi", None)
        region = roi if isinstance(roi, dict) else (_ark_window_region() or sct.monitors[0])
        # Apply optional relative sub-ROI when inventory ROI is present and no explicit manual ROI
        if isinstance(roi, dict) and self.search_roi is None:
            sub_env = os.environ.get("GW_INV_SUBROI", "").strip()
            if sub_env:
                try:
                    parts = [float(p.strip()) for p in sub_env.split(",")]
                    if len(parts) == 4:
                        rl, rt, rw, rh = [max(0.0, min(1.0, v)) for v in parts]
                        L = int(roi.get("left", 0))
                        T = int(roi.get("top", 0))
                        W = int(roi.get("width", 0))
                        H = int(roi.get("height", 0))
                        region = {
                            "left": L + int(W * rl),
                            "top": T + int(H * rt),
                            "width": max(0, int(W * rw)),
                            "height": max(0, int(H * rh)),
                        }
                except Exception:
                    pass
        t0 = time.perf_counter()
        frame = np.array(self._safe_grab(region))  # BGRA
        t1 = time.perf_counter()
        if PERF_ENABLED or logger.isEnabledFor(logging.DEBUG):
            logger.debug("vision: grab (inventory) %.1fms region=%s", (t1 - t0) * 1000.0, str(region))
        return frame[:, :, :3], region

    def match_item_in_inventory(self, roi_bgr: np.ndarray, template_path: str) -> tuple[bool, tuple[int, int], float]:
        """
        Match a single inventory icon inside roi_bgr using the cached UI scale
        and a center-masked edges template. Returns (found, (x,y), score) with (x,y)
        the top-left in ROI coords.
        """
        tpl = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
        if tpl is None:
            raise FileNotFoundError(template_path)
        # scale template to live UI scale from search-bar calibration
        s = float(getattr(self, "ui_scale", 1.0) or 1.0)
        if abs(s - 1.0) > 0.02:
            th, tw = tpl.shape[:2]
            tpl = cv2.resize(
                tpl,
                (max(8, int(tw * s)), max(8, int(th * s))),
                interpolation=cv2.INTER_AREA if s < 1.0 else cv2.INTER_CUBIC,
            )
        # edges + center mask (ignore digits/shield/borders)
        edges_tpl = edges(tpl)
        mask = make_tile_mask(edges_tpl.shape)
        edges_tpl = apply_mask(edges_tpl, mask)
        gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
        edges_roi = edges(gray)
        scr = np.ascontiguousarray(edges_roi)
        tp = np.ascontiguousarray(edges_tpl)
        # fast, single-scale match
        res = cv2.matchTemplate(scr, tp, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        return (float(score) >= float(INVENTORY_ITEM_THRESHOLD)), (int(loc[0]), int(loc[1])), float(score)

    def set_search_roi(self, region: Optional[dict]):
        """Set an absolute screen-space ROI dict {left, top, width, height} to restrict searches."""
        try:
            self.search_roi = dict(region) if isinstance(region, dict) else None
        except Exception:
            self.search_roi = None

    def clear_search_roi(self):
        """Clear any manually set search ROI."""
        self.search_roi = None

    def set_inventory_relative_subroi(self, rel_left: float, rel_top: float, rel_width: float, rel_height: float):
        """Set search ROI as a sub-rectangle relative to current inventory_roi.

        rel_* are fractions in [0,1] relative to inventory_roi width/height.
        """
        inv = getattr(self, "inventory_roi", None)
        if not isinstance(inv, dict):
            raise RuntimeError("inventory_roi not set; run calibrate_inventory_roi_from_search first")
        L = int(inv["left"])
        T = int(inv["top"])
        W = int(inv["width"])
        H = int(inv["height"])
        rl = max(0.0, min(1.0, float(rel_left)))
        rt = max(0.0, min(1.0, float(rel_top)))
        rw = max(0.0, min(1.0, float(rel_width)))
        rh = max(0.0, min(1.0, float(rel_height)))
        left = L + int(W * rl)
        top = T + int(H * rt)
        width = max(0, int(W * rw))
        height = max(0, int(H * rh))
        self.search_roi = {"left": left, "top": top, "width": width, "height": height}

    # --------------------------- ROI helpers ---------------------------
    @staticmethod
    def _locate_template_rect(full_bgr: np.ndarray, tpl_gray: np.ndarray, min_conf: float):
        gray = cv2.cvtColor(full_bgr, cv2.COLOR_BGR2GRAY)
        res = cv2.matchTemplate(gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        if score < float(min_conf):
            return None
        th, tw = tpl_gray.shape[:2]
        x, y = int(loc[0]), int(loc[1])
        return (x, y, int(tw), int(th))

    def _derive_inventory_roi_from_search(self, full_bgr: np.ndarray, search_rect):
        """Segment the inventory panel under the search bar; fallback to geometry-based box.

        Returns absolute-like (L, T, R, B) but relative to full_bgr's origin.
        """
        x, y, w, h = map(int, search_rect)
        height, width = full_bgr.shape[:2]

        # Look in a wide band below the search bar where the grid lives
        band_top = y + int(1.1 * h)
        band_bot = min(height, y + int(12.0 * h))
        band_left = max(0, x - int(0.6 * w))
        band_right = min(width, x + int(3.8 * w))
        if band_bot <= band_top or band_right <= band_left:
            return self._fallback_roi_from_bar((x, y, w, h), width, height)
        band = full_bgr[band_top:band_bot, band_left:band_right]

        # Blue/cyan segmentation in HSV
        try:
            hsv = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
            lower = np.array([85, 40, 40], np.uint8)
            upper = np.array([120, 255, 255], np.uint8)
            mask = cv2.inRange(hsv, lower, upper)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
            cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        except Exception:
            cnts = []

        if cnts:
            c = max(cnts, key=cv2.contourArea)
            x0, y0, ww, hh = cv2.boundingRect(c)
            pad = 8
            left_abs = band_left + x0 + pad
            top_abs = band_top + y0 + pad
            right_abs = band_left + x0 + ww - pad
            bottom_abs = band_top + y0 + hh - pad
            # Clamp
            left_abs, top_abs = max(0, left_abs), max(0, top_abs)
            right_abs, bottom_abs = min(width, right_abs), min(height, bottom_abs)
            return left_abs, top_abs, right_abs, bottom_abs
        # Fallback heuristic
        return self._fallback_roi_from_bar((x, y, w, h), width, height)

    @staticmethod
    def _fallback_roi_from_bar(bar_rect, width: int, height: int):
        x, y, w, h = map(int, bar_rect)
        left_abs = x - int(0.10 * w)
        top_abs = y + int(2.30 * h)
        right_abs = x + int(3.50 * w)
        bottom_abs = y + int(15.0 * h)
        # Clamp to bounds
        left_abs, top_abs = max(0, left_abs), max(0, top_abs)
        right_abs, bottom_abs = min(width, right_abs), min(height, bottom_abs)
        return left_abs, top_abs, right_abs, bottom_abs
