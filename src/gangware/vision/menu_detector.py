"""vision.menu_detector
Detects which high-level menu the game is currently on using precomputed anchors.

Loads anchor definitions from ConfigManager (user INI) and template crops from
assets/anchors. Matching supports 'edge' and 'raw' modes and multiscale.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import cv2  # type: ignore
import numpy as np  # type: ignore

from gangware.core.config import ConfigManager


MENUS_ORDER: Tuple[str, ...] = ("MAIN_MENU", "SELECT_GAME", "SERVER_BROWSER")


def _repo_root() -> Path:
    # vision/ -> gangware/ -> src/ -> repo
    return Path(__file__).resolve().parents[3]


def _assets_anchors_dir() -> Path:
    return _repo_root() / "assets" / "anchors"


def _parse_floats_csv(val: str) -> List[float]:
    out: List[float] = []
    for part in (val or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(float(part))
        except Exception:
            pass
    return out


@dataclass
class Anchor:
    name: str
    fx: float
    fy: float
    fw: float
    fh: float
    mode: str  # 'edge' or 'raw'
    thresh: float
    scales: Sequence[float]
    template_path: Path


class MenuDetector:
    def __init__(self, cfg: Optional[ConfigManager] = None) -> None:
        self.cfg = cfg or ConfigManager()
        self.anchors_by_menu: Dict[str, List[Anchor]] = {}
        self._load_anchors()

    def _load_anchors(self) -> None:
        anchors_root = _assets_anchors_dir()
        for menu in MENUS_ORDER:
            key = f"anchors_{menu.lower()}"
            names_csv = self.cfg.get(key, "") or ""
            names = [n.strip() for n in names_csv.split(",") if n.strip()]
            anchors: List[Anchor] = []
            for name in names:
                base = f"anchor_{name}"
                frac = self.cfg.get(base, "") or ""
                try:
                    fx, fy, fw, fh = [float(x) for x in frac.split(",")]
                except Exception:
                    continue
                mode = (self.cfg.get(f"{base}_mode", "edge") or "edge").strip().lower()
                try:
                    thresh = float(self.cfg.get(f"{base}_thresh", "0.90") or "0.90")
                except Exception:
                    thresh = 0.90
                scales = _parse_floats_csv(self.cfg.get(f"{base}_scales", "1.00,0.92,1.08") or "")
                tpath = anchors_root / f"{name}.png"
                anchors.append(Anchor(name, fx, fy, fw, fh, mode, thresh, scales, tpath))
            self.anchors_by_menu[menu] = anchors

    @staticmethod
    def _gray(bgr: np.ndarray) -> np.ndarray:
        g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(g)

    @staticmethod
    def _edge(gray: np.ndarray) -> np.ndarray:
        return cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 80, 160)

    @staticmethod
    def _crop_frac(img: np.ndarray, fx: float, fy: float, fw: float, fh: float) -> np.ndarray:
        H, W = img.shape[:2]
        x = max(0, min(int(round(fx * W)), W - 1))
        y = max(0, min(int(round(fy * H)), H - 1))
        w = max(2, min(int(round(fw * W)), W - x))
        h = max(2, min(int(round(fh * H)), H - y))
        return img[y : y + h, x : x + w]

    def _match_anchor(self, frame_bgr: np.ndarray, a: Anchor) -> float:
        # Build ROI from fractions
        roi_bgr = self._crop_frac(frame_bgr, a.fx, a.fy, a.fw, a.fh)
        if roi_bgr.size == 0:
            return 0.0
        # Load template
        if not a.template_path.exists():
            return 0.0
        t_bgr = cv2.imread(str(a.template_path))
        if t_bgr is None or t_bgr.size == 0:
            return 0.0

        # Preprocess per mode
        if a.mode == "edge":
            roi_g = self._gray(roi_bgr)
            t_g = self._gray(t_bgr)
            roi_p = self._edge(roi_g)
            t_p = self._edge(t_g)
        else:
            roi_p = self._gray(roi_bgr)
            t_p = self._gray(t_bgr)

        best = 0.0
        th, tw = t_p.shape[:2]
        for s in (a.scales or [1.0]):
            sw = max(2, int(round(tw * s)))
            sh = max(2, int(round(th * s)))
            t_s = cv2.resize(t_p, (sw, sh), interpolation=cv2.INTER_AREA)
            if roi_p.shape[0] < t_s.shape[0] or roi_p.shape[1] < t_s.shape[1]:
                continue
            res = cv2.matchTemplate(roi_p, t_s, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, _, _ = cv2.minMaxLoc(res)
            if max_val > best:
                best = max_val
        return float(best)

    def detect(self, frame_bgr: np.ndarray) -> Tuple[Optional[str], Optional[str], float, bool]:
        """Return (menu_key, anchor_name, score, met_threshold).

        Tries anchors in MENUS_ORDER; returns immediately on first anchor meeting its threshold.
        If none meet thresholds, returns best-scoring candidate with met_threshold=False; menu/name
        may be None if no anchors are configured.
        """
        best_menu: Optional[str] = None
        best_name: Optional[str] = None
        best_score: float = 0.0
        for menu in MENUS_ORDER:
            anchors = self.anchors_by_menu.get(menu) or []
            for a in anchors:
                score = self._match_anchor(frame_bgr, a)
                if score >= a.thresh:
                    return menu, a.name, score, True
                if score > best_score:
                    best_menu, best_name, best_score = menu, a.name, score
        return best_menu, best_name, best_score, False
