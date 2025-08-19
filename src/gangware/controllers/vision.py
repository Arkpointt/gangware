"""Vision helpers used by the app.

Provides a small VisionController that captures the primary monitor and
performs template matching using OpenCV. Kept minimal for testability.
"""

from typing import Optional, Tuple
import os
import ctypes

import cv2
import numpy as np
import mss
import logging
import threading
import time
from pathlib import Path
from ..core.logging_setup import get_artifacts_dir


class VisionController:
    """Main class for visual perception and template matching."""

    def __init__(self) -> None:
        self._tls = threading.local()
        self._last_debug = {}
        self._last_pos: Optional[Tuple[int, int]] = None
        self._last_perf = {}
        self.search_roi: Optional[dict] = None
        self.ui_scale: float = 1.0
        self.ui_scale_ts: float = 0.0  # timestamp when scale was last set

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

    def find_template(
        self, template_path: str, confidence: float = 0.8
    ) -> Optional[Tuple[int, int]]:
        """Find the template within the Ark window (if focused) or virtual screen.

        Returns absolute screen coordinates (x, y) of the match center when found,
        otherwise None.
        """
        # Prefer Ark window; fallback to virtual screen box
        sct = self._get_sct()
        # Choose base region: Ark window if active; else full virtual screen
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
        # This lets users constrain searches to a smaller area inside the inventory panel
        # without hard-coding absolute pixels. It only applies when no explicit manual ROI is set.
        if isinstance(roi_override, dict):
            sub_env = os.environ.get("GW_INV_SUBROI", "").strip()
            if sub_env and self.search_roi is None:  # don't override explicit manual ROI
                try:
                    parts = [float(p.strip()) for p in sub_env.split(",")]
                    if len(parts) == 4:
                        rl, rt, rw, rh = [max(0.0, min(1.0, v)) for v in parts]
                        L = int(roi_override.get("left", 0)); T = int(roi_override.get("top", 0))
                        W = int(roi_override.get("width", 0)); H = int(roi_override.get("height", 0))
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
        regions = []
        # If we have a last known position, search a small ROI around it first
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

        template_gray = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
        if template_gray is None:
            raise FileNotFoundError(f"Template image not found: {template_path}")
        tpl_h, tpl_w = template_gray.shape[:2]

        # Try each region with a fast pass first, then a broader fallback if needed
        fast_scales = [0.90, 0.95, 1.00, 1.05, 1.10]
        full_scales = [round(0.55 + 0.05 * i, 2) for i in range(23)]  # 0.55..1.65
        fast_scales_n = len(fast_scales)
        slow_scales_n = len(full_scales)
        fast_only = (os.environ.get("GW_VISION_FAST_ONLY", "0") == "1")
        best_overall = -1.0
        best_overall_region = None
        best_overall_meta = None
        logger = logging.getLogger(__name__)
        perf_enabled = (os.environ.get("GW_VISION_PERF", "0") == "1") or logger.isEnabledFor(logging.DEBUG)
        t_call0 = time.perf_counter()
        perf_regions = []
        for region in regions:
            t_grab0 = time.perf_counter()
            grab = np.array(self._safe_grab(region))  # BGRA
            t_grab1 = time.perf_counter()
            screenshot_gray = cv2.cvtColor(grab, cv2.COLOR_BGRA2GRAY)
            t_gray1 = time.perf_counter()
            std_val = float(screenshot_gray.std())
            # Skip likely-black frames (exclusive fullscreen)
            if std_val < 1.0:
                if perf_enabled:
                    perf_regions.append({
                        "region": dict(region),
                        "grab_ms": (t_grab1 - t_grab0) * 1000.0,
                        "gray_ms": (t_gray1 - t_grab1) * 1000.0,
                        "skipped_black": True,
                        "std": float(std_val),
                    })
                logger.debug("vision: skipped region %s due to near-black frame (std=%.3f)", str(region), float(std_val))
                continue
            # Fast pass: few scales, edges method only
            t_fast0 = time.perf_counter()
            best_score, best_loc, best_wh, meta = self._best_match_multi(screenshot_gray, template_gray, fast_scales, modes=["edges", "edges_center"])
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

            # Slow fallback: full scales and all methods (skip if fast-only mode is enabled)
            if not fast_only:
                t_slow0 = time.perf_counter()
                slow_score, slow_loc, slow_wh, slow_meta = self._best_match_multi(screenshot_gray, template_gray, full_scales)
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
                    scale = 640 / max(1, max(h, w))
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

        if 'perf_enabled' in locals() and perf_enabled:
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

    # -------------------------- Matching helpers (reduce CC) --------------------------
    @staticmethod
    def _edges(img: np.ndarray) -> np.ndarray:
        try:
            v = float(np.median(img))
            lo = int(max(0, 0.66 * v))
            hi = int(min(255, 1.33 * v))
            return cv2.Canny(img, lo, hi)
        except Exception:
            return cv2.Canny(img, 50, 150)

    def _screen_variants(self, gray: np.ndarray) -> dict:
        try:
            blur = cv2.GaussianBlur(gray, (3, 3), 0)
        except Exception:
            blur = gray
        try:
            eq = cv2.equalizeHist(gray)
        except Exception:
            eq = gray
        edges = self._edges(gray)
        return {"gray_blur": blur, "gray_eq": eq, "edges": edges}

    def _make_tile_mask(self, shape, left=0.08, right=0.08, top=0.22, bottom=0.18):
        """Binary mask that keeps the inner area of an item tile (ignores digits/shield)."""
        h, w = shape
        mask = np.zeros((h, w), np.uint8)
        x0 = int(w * left);  x1 = int(w * (1.0 - right))
        y0 = int(h * top);   y1 = int(h * (1.0 - bottom))
        if y1 > y0 and x1 > x0:
            mask[y0:y1, x0:x1] = 255
        return mask

    def _apply_mask(self, img, mask):
        try:
            return cv2.bitwise_and(img, img, mask=mask)
        except Exception:
            return img

    def _resize_tpl(self, tpl: np.ndarray, scale: float) -> np.ndarray:
        h, w = tpl.shape
        if abs(scale - 1.0) < 1e-6:
            return tpl
        nh, nw = max(8, int(h * scale)), max(8, int(w * scale))
        return cv2.resize(tpl, (nw, nh), interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC)

    def _tpl_variants(self, tpl: np.ndarray) -> dict:
        try:
            blur = cv2.GaussianBlur(tpl, (3, 3), 0)
        except Exception:
            blur = tpl
        try:
            eq = cv2.equalizeHist(tpl)
        except Exception:
            eq = tpl
        edges = self._edges(tpl)
        # new: mask out corners (digits, shield, borders)
        try:
            mask = self._make_tile_mask(tpl.shape)
        except Exception:
            mask = None
        if mask is not None:
            try:
                edges_center = self._apply_mask(edges, mask)
            except Exception:
                edges_center = edges
        else:
            edges_center = edges
        return {"gray_blur": blur, "gray_eq": eq, "edges": edges, "edges_center": edges_center}

    def _match_methods(self, modes: list[str], screen_v: dict, tpl_v: dict, scale: float) -> tuple[float, Optional[tuple[int, int]], Optional[dict]]:
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

    def _best_match_multi(self, screenshot_gray: np.ndarray, template_gray: np.ndarray, scales: list[float], modes: list[str] | None = None):
        """Return (score, loc, (w,h), meta) for best match across strategies and scales.

        modes: list of methods to try among {"gray_blur", "gray_eq", "edges"}. If None, tries all.
        """
        if not modes:
            modes = ["gray_blur", "gray_eq", "edges"]
        screen_v = self._screen_variants(screenshot_gray)

        best_score = -1.0
        best_loc = None
        best_wh = None
        best_meta = None

        for s in scales:
            try:
                tpl_scaled = self._resize_tpl(template_gray, s)
                if tpl_scaled.shape[0] < 8 or tpl_scaled.shape[1] < 8:
                    continue
                tpl_v = self._tpl_variants(tpl_scaled)
                sc, loc, meta = self._match_methods(modes, screen_v, tpl_v, s)
                if sc > best_score and loc is not None:
                    best_score = sc
                    best_loc = loc
                    best_wh = (tpl_scaled.shape[1], tpl_scaled.shape[0])
                    best_meta = meta
            except Exception:
                continue
        return best_score, best_loc, best_wh, (best_meta or {})

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

        Uses a multi-scale matcher (edges + gray variants) similar to find_template
        so it works under 4K/UI scaling. Returns a region dict or None if not found.
        """
        # Ensure thread-local MSS instance
        sct = self._get_sct()
        base_region = _ark_window_region() or sct.monitors[0]
        t0 = time.perf_counter()
        frame = np.array(self._safe_grab(base_region))  # BGRA
        t1 = time.perf_counter()
        if (os.environ.get("GW_VISION_PERF", "0") == "1") or logging.getLogger(__name__).isEnabledFor(logging.DEBUG):
            logging.getLogger(__name__).debug("vision: grab (calibrate) %.1fms region=%s", (t1 - t0) * 1000.0, str(base_region))

        bgr = frame[:, :, :3]
        screenshot_gray = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
        tpl_gray = cv2.imread(search_template_path, cv2.IMREAD_GRAYSCALE)
        if tpl_gray is None:
            raise FileNotFoundError(search_template_path)

        # Full scale set for robust detection - but optimize for speed since we already found search bar
        # Use fewer scales focused around the likely UI scale
        if hasattr(self, 'ui_scale') and self.ui_scale and abs(self.ui_scale - 1.0) < 0.5:
            # If UI scale is close to 1.0, use a focused set around that scale
            base_scale = self.ui_scale
            fast_scales = [round(base_scale + 0.05 * i, 2) for i in range(-2, 3)]  # ±0.1 around detected scale
            logging.getLogger(__name__).debug("vision: calibrate using fast scales around %.2f: %s", base_scale, fast_scales)
        else:
            # Fallback to broader range but still reduced from 23 to 11 scales
            fast_scales = [round(0.7 + 0.1 * i, 2) for i in range(11)]  # 0.7..1.7 in 0.1 steps
            logging.getLogger(__name__).debug("vision: calibrate using fallback scales: %s", fast_scales)

        cal_start = time.perf_counter()
        score, loc, wh, _meta = self._best_match_multi(screenshot_gray, tpl_gray, fast_scales)
        cal_time = (time.perf_counter() - cal_start) * 1000.0
        logging.getLogger(__name__).info("vision: calibrate_roi matching took %.1fms with %d scales", cal_time, len(fast_scales))
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

        # 2) derive ROI within the same frame, then convert to absolute coords
        l_rel, t_rel, r_rel, b_rel = self._derive_inventory_roi_from_search(bgr, rect_rel)
        left_abs = int(base_region["left"]) + int(l_rel)
        top_abs = int(base_region["top"]) + int(t_rel)
        right_abs = int(base_region["left"]) + int(r_rel)
        bottom_abs = int(base_region["top"]) + int(b_rel)
        roi = {"left": left_abs, "top": top_abs, "width": max(0, right_abs - left_abs), "height": max(0, bottom_abs - top_abs)}
        # Sanity guard: avoid setting fullscreen as inventory ROI
        try:
            if roi.get("width", 0) <= 0 or roi.get("height", 0) <= 0:
                return None
        except Exception:
            return None
        self.inventory_roi = roi
        return dict(self.inventory_roi)

    def grab_inventory_bgr(self):
        """Grab and return (BGR, region) for the inventory ROI when available, else Ark/window."""
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
                        L = int(roi.get("left", 0)); T = int(roi.get("top", 0))
                        W = int(roi.get("width", 0)); H = int(roi.get("height", 0))
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
        if (os.environ.get("GW_VISION_PERF", "0") == "1") or logging.getLogger(__name__).isEnabledFor(logging.DEBUG):
            logging.getLogger(__name__).debug("vision: grab (inventory) %.1fms region=%s", (t1 - t0) * 1000.0, str(region))
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
        edges_tpl = self._edges(tpl)
        mask = self._make_tile_mask(edges_tpl.shape)
        edges_tpl = self._apply_mask(edges_tpl, mask)
        gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
        edges_roi = self._edges(gray)
        scr = np.ascontiguousarray(edges_roi)
        tp = np.ascontiguousarray(edges_tpl)
        # fast, single-scale match
        res = cv2.matchTemplate(scr, tp, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        return (float(score) >= 0.86), (int(loc[0]), int(loc[1])), float(score)

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
        L = int(inv["left"]); T = int(inv["top"]); W = int(inv["width"]); H = int(inv["height"])
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
            # Degenerate band, fallback directly
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


# ----------------------- Windows helpers for Ark window -----------------------
if os.name == "nt":
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    def _foreground_executable_name_lower() -> str:
        try:
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return ""
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
            if not hproc:
                return ""
            try:
                buf_len = wintypes.DWORD(260)
                while True:
                    buf = ctypes.create_unicode_buffer(buf_len.value)
                    ok = kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(buf_len))
                    if ok:
                        return os.path.basename(buf.value or "").lower()
                    needed = buf_len.value
                    if needed <= len(buf):
                        break
                    buf_len = wintypes.DWORD(needed)
                return ""
            finally:
                kernel32.CloseHandle(hproc)
        except Exception:
            return ""

    def _ark_window_region() -> Optional[dict]:
        try:
            if _foreground_executable_name_lower() != "arkascended.exe":
                return None
            hwnd = user32.GetForegroundWindow()
            rc = RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rc)):
                return None
            left, top = int(rc.left), int(rc.top)
            width, height = int(rc.right - rc.left), int(rc.bottom - rc.top)
            if width <= 0 or height <= 0:
                return None
            return {"left": left, "top": top, "width": width, "height": height}
        except Exception:
            return None
else:
    def _ark_window_region() -> Optional[dict]:
        return None
