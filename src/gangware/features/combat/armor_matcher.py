"""
Armor matcher with hybrid (edges + HSV hue) tier-aware detection and caching.

Usage:
    matcher = ArmorMatcher(assets_dir=Path('assets'), app_templates_dir=APPDATA/templates)
    x, y, score, tier, w, h = matcher.best_for_name(roi_bgr, 'flak_helmet')
Then click at (x + w//2, y + h//2) in ROI coordinates.

Notes:
- Loads templates recursively from assets, honoring quality-priority order and
  per-user overrides (if you include app_templates_dir in your integration).
- Performs edges-only template matching for speed, with an HSV hue confirmation
  to disambiguate tiers (Ascendant teal vs Mastercraft yellow-green, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import logging
import sys

# Tier priority (highest to lowest)
TIER_ORDER: List[str] = [
    "tek",  # untiered tek templates
    "ascendant",
    "mastercraft",
    "journeyman",
    "apprentice",
    "ramshackle",
    "primitive",
]

# Restrict matching to these tiers and names
ALLOWED_TIERS: List[str] = [
    "tek",
    "ascendant",
    "mastercraft",
]
# Allowed flak pieces (support common synonyms)
ALLOWED_NAMES: List[str] = [
    "flak_helmet",
    "flak_chest",
    "flak_chestpiece",
    "flak_gauntlets",
    "flak_gloves",
    "flak_leggings",
    "flak_legs",
    "flak_boots",
    # Tek variants
    "tek_helmet",
    "tek_chestpiece",
    "tek_gauntlets",
    "tek_leggings",
    "tek_boots",
]

# Filename aliasing for common misspellings or legacy assets
# Note: These affect only file resolution; the public API names remain ALLOWED_NAMES above.
NAME_FILE_ALIASES: Dict[str, List[str]] = {
    # Support alternate synonyms for completeness (if filenames were saved that way)
    "flak_chestpiece": ["flak_chest"],
    "flak_gauntlets": ["flak_gloves"],
    "flak_legs": ["flak_leggings"],
}


@dataclass
class _Tpl:
    tier: str
    edges: np.ndarray
    size: Tuple[int, int]  # (w, h)
    path: str


def _median_hue_bgr(bgr: np.ndarray, sat_min: int = 60, val_min: int = 60) -> Optional[float]:
    """Return median Hue (0..179) using only colorful pixels; None if not enough."""
    try:
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        H, S, V = cv2.split(hsv)
        mask = (S >= sat_min) & (V >= val_min)
        vals = H[mask]
        if vals.size < 25:
            return None
        return float(np.median(vals.astype(np.float64)))
    except Exception:
        return None


def _hue_dist(h1: float, h2: float) -> float:
    """Circular distance in OpenCV hue space (0..179)."""
    d = abs(h1 - h2)
    return min(d, 180.0 - d)


class ArmorMatcher:
    def __init__(self, assets_dir: Path, app_templates_dir: Optional[Path] = None) -> None:
        self.assets_dir = self._resolve_assets_dir(Path(assets_dir))
        self.app_templates_dir = Path(app_templates_dir) if app_templates_dir else None
        # name -> tier -> list[_Tpl]
        self._bank: Dict[str, Dict[str, List[_Tpl]]] = {}
        # name -> tier -> ref hue
        self._tier_ref_hue: Dict[str, Dict[str, float]] = {}
        # cache resolved file paths per name for faster subsequent lookups
        self._path_cache: Dict[str, List[Path]] = {}
        # last best score per name for debugging
        self._last_best: Dict[str, float] = {}

    def _resolve_assets_dir(self, p: Path) -> Path:
        """Resolve the assets directory robustly for both dev and frozen executables."""
        try:
            if p.is_absolute():
                return p
            # When frozen, PyInstaller extracts data files under sys._MEIPASS
            if getattr(sys, 'frozen', False):
                base = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
            else:
                # Dev mode: prefer current working dir as project root
                base = Path.cwd()
            return (base / p).resolve()
        except Exception:
            return p

    # ---------------------------- public API ----------------------------
    def best_for_name(
        self,
        roi_bgr: np.ndarray,
        name_norm: str,
        threshold: float = 0.88,
        early_exit: bool = True,
    ) -> Optional[Tuple[int, int, float, str, int, int]]:
        """
        Returns (x, y, score, tier, w, h) for top-left of the best match in ROI coords.
        Prefers TIER_ORDER, validates with hue so tiers can't be confused.
        """
        name_norm = str(name_norm or "").strip().lower()
        if not name_norm:
            return None
        # Enforce allowed item whitelist
        if name_norm not in ALLOWED_NAMES:
            logging.getLogger(__name__).debug("armor_matcher: name not allowed: %s", name_norm)
            return None
        # Ensure templates are loaded (edges + ref hue)
        self._ensure_loaded(name_norm)
        if name_norm not in self._bank:
            return None
        # Prepare ROI edges once for speed
        try:
            gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
        except Exception:
            return None
        edges_roi = cv2.Canny(gray, 60, 120)

        # Track best per tier
        per_tier: Dict[str, Tuple[float, Tuple[int, int], Tuple[int, int]]] = {}

        tiers = [t for t in TIER_ORDER if t in self._bank.get(name_norm, {})]
        # Optimize scales for speed - focus on most likely ranges first
        # Try common UI scales first, then expand if needed
        fast_scales = [1.0, 0.8, 0.9, 1.1, 0.7, 1.2, 0.6, 1.3]  # Most likely scales first
        slow_scales = [round(0.35 + 0.05 * i, 2) for i in range(26) if round(0.35 + 0.05 * i, 2) not in fast_scales]

        best_overall = -1.0
        found_match = False

        # Debug timing
        import time
        t_start = time.perf_counter()
        fast_attempts = 0
        slow_attempts = 0

        # Fast pass: try most common scales first
        for tier in tiers:
            if found_match and early_exit:
                break
            for tpl in self._bank[name_norm][tier]:
                if found_match and early_exit:
                    break
                for s in fast_scales:
                    fast_attempts += 1
                    try:
                        if abs(s - 1.0) < 1e-6:
                            tpl_edges = tpl.edges
                            tw, th = tpl.size
                        else:
                            th0, tw0 = tpl.edges.shape[:2]
                            th, tw = max(8, int(round(th0 * s))), max(8, int(round(tw0 * s)))
                            if th > edges_roi.shape[0] or tw > edges_roi.shape[1]:
                                continue
                            tpl_edges = cv2.resize(
                                tpl.edges, (tw, th),
                                interpolation=cv2.INTER_AREA if s < 1.0 else cv2.INTER_CUBIC,
                            )
                        if edges_roi.shape[0] < th or edges_roi.shape[1] < tw:
                            continue
                        res = cv2.matchTemplate(edges_roi, tpl_edges, cv2.TM_CCOEFF_NORMED)
                        _, sc, _, loc = cv2.minMaxLoc(res)
                    except Exception:
                        continue
                    cur = per_tier.get(tier, (-1.0, (0, 0), (tw, th)))
                    if sc > cur[0]:
                        per_tier[tier] = (float(sc), (int(loc[0]), int(loc[1])), (tw, th))
                    if sc > best_overall:
                        best_overall = float(sc)

                    # Early exit on good match
                    if sc >= float(threshold):
                        tile = roi_bgr[loc[1] : loc[1] + th, loc[0] : loc[0] + tw]
                        predicted = self._classify_by_hue(name_norm, tile)
                        if predicted == tier:
                            t_end = time.perf_counter()
                            logging.getLogger(__name__).info("armor_matcher: FAST_EXIT score=%.3f attempts=%d time=%.1fms",
                                                             sc, fast_attempts, (t_end-t_start)*1000)
                            try:
                                self._last_best[name_norm] = float(sc)
                            except Exception:
                                pass
                            return loc[0], loc[1], sc, tier, tw, th
                        elif sc >= 0.3:  # Good structural match, continue with this tier
                            found_match = True
                            break

        t_fast = time.perf_counter()

        # Only do slow pass if fast pass didn't find anything good
        if best_overall < 0.15:  # Very poor matches so far
            for tier in tiers:
                for tpl in self._bank[name_norm][tier]:
                    for s in slow_scales:
                        slow_attempts += 1
                        try:
                            th0, tw0 = tpl.edges.shape[:2]
                            th, tw = max(8, int(round(th0 * s))), max(8, int(round(tw0 * s)))
                            if th > edges_roi.shape[0] or tw > edges_roi.shape[1]:
                                continue
                            tpl_edges = cv2.resize(
                                tpl.edges, (tw, th),
                                interpolation=cv2.INTER_AREA if s < 1.0 else cv2.INTER_CUBIC,
                            )
                            if edges_roi.shape[0] < th or edges_roi.shape[1] < tw:
                                continue
                            res = cv2.matchTemplate(edges_roi, tpl_edges, cv2.TM_CCOEFF_NORMED)
                            _, sc, _, loc = cv2.minMaxLoc(res)
                        except Exception:
                            continue
                        cur = per_tier.get(tier, (-1.0, (0, 0), (tw, th)))
                        if sc > cur[0]:
                            per_tier[tier] = (float(sc), (int(loc[0]), int(loc[1])), (tw, th))
                        if sc > best_overall:
                            best_overall = float(sc)

        t_end = time.perf_counter()
        logging.getLogger(__name__).info("armor_matcher: timing fast=%d/%d slow=%d fast_time=%.1fms total_time=%.1fms best=%.3f",
                                         fast_attempts, len(fast_scales)*len(tiers)*sum(len(self._bank[name_norm][t]) for t in tiers),
                                         slow_attempts, (t_fast-t_start)*1000, (t_end-t_start)*1000, best_overall)

        # Choose best across tiers; verify hue if possible
        best_tier: Optional[str] = None
        best_tuple: Tuple[float, Tuple[int, int], Tuple[int, int]] = (-1.0, (0, 0), (0, 0))
        for t, tpl_info in per_tier.items():
            if tpl_info[0] > best_tuple[0]:
                best_tier, best_tuple = t, tpl_info

        sc, (x, y), (w, h) = best_tuple
        # Record best score for diagnostics
        try:
            self._last_best[name_norm] = float(max(best_overall, sc))
        except Exception:
            pass
        if sc >= float(threshold) and best_tier is not None:
            tile = roi_bgr[y : y + h, x : x + w]
            predicted = self._classify_by_hue(name_norm, tile)
            # If hue suggests a different tier and that tier is close in score, prefer hue tier
            if predicted and predicted != best_tier and predicted in per_tier and per_tier[predicted][0] >= sc - 0.03:
                sc2, (x2, y2), (w2, h2) = per_tier[predicted]
                return x2, y2, sc2, predicted, w2, h2
            return x, y, sc, (predicted or best_tier), w, h
        return None

    def get_last_best(self, name_norm: str) -> Optional[float]:
        try:
            value = self._last_best.get(str(name_norm).strip().lower())
            return float(value) if value is not None else None
        except Exception:
            return None

    # ---------------------------- internals ----------------------------
    def _classify_by_hue(self, name_norm: str, tile_bgr: np.ndarray) -> Optional[str]:
        h = _median_hue_bgr(tile_bgr)
        bank = self._tier_ref_hue.get(name_norm) or {}
        if h is None or not bank:
            return None
        best_tier, best_d = None, 1e9
        for tier, ref in bank.items():
            d = _hue_dist(h, ref)
            if d < best_d:
                best_d, best_tier = d, tier
        return best_tier if best_d <= 20.0 else None

    def _ensure_loaded(self, name_norm: str) -> None:
        if name_norm in self._bank:
            return
        paths = self._resolve_paths(name_norm)
        if not paths:
            logging.getLogger(__name__).info("armor_matcher: no template paths found for %s", name_norm)
            return
        logging.getLogger(__name__).info("armor_matcher: loading templates for %s: %s", name_norm, [str(p) for p in paths])

        # Load templates grouped by tier and learn a ref hue per tier
        per_tier: Dict[str, List[_Tpl]] = {}
        tier_ref: Dict[str, float] = {}
        for p in paths:
            tier = self._infer_tier_from_name(p.name)
            if not tier:
                logging.getLogger(__name__).info("armor_matcher: no tier found in filename %s", p.name)
                continue
            if tier not in ALLOWED_TIERS:
                logging.getLogger(__name__).info("armor_matcher: tier %s not in allowed tiers for %s", tier, p.name)
                continue
            bgr = cv2.imread(str(p), cv2.IMREAD_COLOR)
            if bgr is None:
                logging.getLogger(__name__).info("armor_matcher: failed to load image %s", str(p))
                continue
            g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            # For better matching, extract just the center region where the item icon is,
            # excluding background and text overlays that vary between template and inventory
            h_full, w_full = g.shape[:2]
            # Use center 60% of image to focus on the actual item icon
            crop_margin = 0.2
            y_start = int(h_full * crop_margin)
            y_end = int(h_full * (1 - crop_margin))
            x_start = int(w_full * crop_margin)
            x_end = int(w_full * (1 - crop_margin))
            g_cropped = g[y_start:y_end, x_start:x_end]
            edges = cv2.Canny(g_cropped, 60, 120)
            h, w = edges.shape[:2]
            per_tier.setdefault(tier, []).append(_Tpl(tier=tier, edges=edges, size=(w, h), path=str(p)))
            logging.getLogger(__name__).info("armor_matcher: loaded %s tier=%s size=%dx%d (cropped from %dx%d)",
                                             p.name, tier, w, h, w_full, h_full)
            if tier not in tier_ref:
                # Sample hue from the cropped region to avoid background interference
                bgr_cropped = bgr[y_start:y_end, x_start:x_end]
                # Sample inner region of the cropped area to focus on the actual item
                ih, iw = bgr_cropped.shape[:2]
                y0, y1 = int(0.15 * ih), int(0.85 * ih)
                x0, x1 = int(0.15 * iw), int(0.85 * iw)
                ref = _median_hue_bgr(bgr_cropped[y0:y1, x0:x1])
                if ref is not None:
                    tier_ref[tier] = ref
                    logging.getLogger(__name__).info("armor_matcher: tier %s ref_hue=%.1f", tier, ref)
        if per_tier:
            self._bank[name_norm] = per_tier
            logging.getLogger(__name__).info("armor_matcher: loaded %d tiers for %s: %s",
                                             len(per_tier), name_norm, list(per_tier.keys()))
        if tier_ref:
            self._tier_ref_hue[name_norm] = tier_ref

    def _infer_tier_from_name(self, filename: str) -> Optional[str]:
        base = filename.lower().split(".")[0]
        for t in TIER_ORDER:
            if base.startswith(t + "_"):
                return t
        # fallback: if the filename equals the name_norm without tier (handled by caller)
        for t in TIER_ORDER:
            if base.endswith("_" + t):  # rarely used pattern
                return t
        # or if the name contains the tier somewhere
        for t in TIER_ORDER:
            if t in base:
                return t
        # no tier identifiable
        return None

    def _resolve_paths(self, name_norm: str) -> List[Path]:
        # Cache hit
        if name_norm in self._path_cache:
            return self._path_cache[name_norm]
        variants: List[str] = [name_norm]
        # Only consider allowed tiers to reduce IO and enforce constraints
        variants += [f"{t}_{name_norm}" for t in ALLOWED_TIERS]

        # Include filename aliases (for misspellings or alternate naming)
        try:
            aliases = NAME_FILE_ALIASES.get(name_norm, [])
            for a in aliases:
                variants.append(a)
                variants += [f"{t}_{a}" for t in ALLOWED_TIERS]
        except Exception:
            pass

        seen: set[str] = set()
        results: List[Path] = []

        # Per-user override folder first if provided
        if self.app_templates_dir:
            for v in variants:
                p = self.app_templates_dir / f"{v}.png"
                if p.exists():
                    sp = str(p.resolve())
                    if sp not in seen:
                        results.append(p)
                        seen.add(sp)

        # Direct assets path, then recursive
        for v in variants:
            p = self.assets_dir / f"{v}.png"
            if p.exists():
                sp = str(p.resolve())
                if sp not in seen:
                    results.append(p)
                    seen.add(sp)
        try:
            for v in variants:
                for p in self.assets_dir.rglob(f"{v}.png"):
                    sp = str(p.resolve())
                    if sp not in seen:
                        results.append(p)
                        seen.add(sp)
        except Exception:
            pass

        # Avoid caching empty results so adding files at runtime is detected on next call
        if results:
            self._path_cache[name_norm] = results
        return results
