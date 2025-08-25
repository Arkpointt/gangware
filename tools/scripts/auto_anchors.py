from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Tuple

import cv2  # type: ignore
import numpy as np  # type: ignore

"""
Auto-anchor generator

Reads full-screen menu screenshots from assets/menus, auto-picks 2 anchors per
menu using edge-density scoring in stable UI bands, crops templates to
assets/anchors/<MENU>_N.png, writes fractional coordinates and settings for
each anchor into the per-user config.ini via ConfigManager, and saves annotated
previews to assets/anchors_preview/<menu>.png.

Menus processed in order: MAIN_MENU, SELECT_GAME, SERVER_BROWSER.

Usage (from repo root):
  - Ensure screenshots exist in assets/menus/ as PNGs. Suggested names:
      main_menu.png, select_game.png, server_browser.png
  - Run with your venv active:
      python tools/scripts/auto_anchors.py

This is HDR- and resolution-tolerant at runtime by storing fractional coords
and recommending edge-based matching for logo-like anchors.
"""


# Canonical working height (used for scoring/preview only in this tool)
BASE_HEIGHT = 1080


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _assets_dir() -> Path:
    return _repo_root() / "assets"


def _normalize_gray(bgr: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float]:
    """Return (gray_small, edge_small, scale_to_BASE_HEIGHT)."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    h, w = gray.shape[:2]
    s = BASE_HEIGHT / float(h)
    if abs(s - 1.0) > 1e-3:
        gray_small = cv2.resize(gray, (int(round(w * s)), BASE_HEIGHT), interpolation=cv2.INTER_AREA)
    else:
        gray_small = gray
    edge_small = cv2.Canny(cv2.GaussianBlur(gray_small, (3, 3), 0), 80, 160)
    return gray_small, edge_small, s


def _bands_for(menu_key: str) -> List[Tuple[float, float, float, float]]:
    """Return fractional bands (x,y,w,h) to search for anchors per menu.

    Heuristic, resolution-agnostic:
    - Focus on top bars, corners, and center area for logos/headers.
    """
    menu_key = menu_key.upper()
    if menu_key == "MAIN_MENU":
        return [
            (0.35, 0.30, 0.30, 0.30),  # center block for big logo/glyphs
            (0.75, 0.02, 0.22, 0.16),  # top-right (settings/branding)
            (0.03, 0.02, 0.22, 0.16),  # top-left (back/logo bits)
        ]
    if menu_key == "SELECT_GAME":
        return [
            (0.02, 0.02, 0.96, 0.18),  # top header area
            (0.02, 0.20, 0.30, 0.25),  # left column area
            (0.68, 0.20, 0.30, 0.25),  # right column area
        ]
    if menu_key == "SERVER_BROWSER":
        return [
            (0.02, 0.02, 0.96, 0.18),  # top filters/search/header bar
            (0.02, 0.20, 0.30, 0.20),  # left area near server list header
            (0.70, 0.20, 0.28, 0.20),  # right area near search/paging
        ]
    # Fallback: whole image
    return [(0.0, 0.0, 1.0, 1.0)]


def _sliding_windows(width: int, height: int, roi: Tuple[int, int, int, int]) -> List[Tuple[int, int, int, int]]:
    x0, y0, w, h = roi
    x1, y1 = x0 + w, y0 + h
    # window sizes at canonical scale
    sizes = [(96, 96), (128, 128)]
    stride = max(16, min(width, height) // 64)
    out: List[Tuple[int, int, int, int]] = []
    for (ww, hh) in sizes:
        for y in range(y0, max(y1 - hh + 1, y0 + 1), stride):
            for x in range(x0, max(x1 - ww + 1, x0 + 1), stride):
                out.append((x, y, ww, hh))
    return out


def _pick_top_k(
    gray: np.ndarray,
    edge: np.ndarray,
    bands: List[Tuple[float, float, float, float]],
    k: int = 2,
) -> List[Tuple[int, int, int, int]]:
    H, W = gray.shape[:2]
    candidates: List[Tuple[float, Tuple[int, int, int, int]]] = []
    for (fx, fy, fw, fh) in bands:
        roi = (int(fx * W), int(fy * H), int(fw * W), int(fh * H))
        for (x, y, w, h) in _sliding_windows(W, H, roi):
            patch_e = edge[y : y + h, x : x + w]
            if patch_e.size == 0:
                continue
            ed = float(np.mean(patch_e > 0))  # edge density
            if ed < 0.05:
                continue
            g = float(np.mean(gray[y : y + h, x : x + w])) / 255.0
            penalty = 0.05 * abs(g - 0.5)
            score = ed - penalty
            candidates.append((score, (x, y, w, h)))

    # Sort and non-maximum suppression to diversify positions
    candidates.sort(key=lambda t: t[0], reverse=True)
    picked: List[Tuple[int, int, int, int]] = []

    def iou(a, b) -> float:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        x0 = max(ax, bx)
        y0 = max(ay, by)
        x1 = min(ax + aw, bx + bw)
        y1 = min(ay + ah, by + bh)
        inter = max(0, x1 - x0) * max(0, y1 - y0)
        ua = aw * ah + bw * bh - inter
        return inter / ua if ua > 0 else 0.0

    for _, rect in candidates:
        if all(iou(rect, p) < 0.15 for p in picked):
            picked.append(rect)
        if len(picked) >= k:
            break
    return picked


def _write_ini_anchors(
    config_manager,
    menu_key: str,
    anchors: List[Tuple[str, Tuple[float, float, float, float]]],
    src_h: int,
) -> None:
    """Persist anchors into user config.ini using fractional coords.

    Keys written (DEFAULT section):
      anchors_<menu> = comma-separated names
      anchor_<Name> = fx,fy,fw,fh
      anchor_<Name>_mode = edge|raw (heuristic: first is edge, others raw)
      anchor_<Name>_thresh = float
      anchor_<Name>_scales = csv floats
      anchor_<Name>_src_h = int (screenshot height for reference)
    """
    menu_lower = menu_key.lower()
    names = ",".join([name for name, _ in anchors])
    config_manager.config["DEFAULT"][f"anchors_{menu_lower}"] = names
    for idx, (name, (fx, fy, fw, fh)) in enumerate(anchors):
        base = f"anchor_{name}"
        config_manager.config["DEFAULT"][base] = f"{fx:.6f},{fy:.6f},{fw:.6f},{fh:.6f}"
        # Heuristic defaults: first anchor in edge mode for logo-like robustness
        mode = "edge" if idx == 0 else "raw"
        thresh = 0.90 if mode == "edge" else 0.92
        scales = "1.00,0.92,1.08,1.15"
        config_manager.config["DEFAULT"][f"{base}_mode"] = mode
        config_manager.config["DEFAULT"][f"{base}_thresh"] = f"{thresh:.2f}"
        config_manager.config["DEFAULT"][f"{base}_scales"] = scales
        config_manager.config["DEFAULT"][f"{base}_src_h"] = str(int(src_h))
    config_manager.save()


def main() -> None:
    # Import ConfigManager from src while running as a tool
    root = _repo_root()
    sys.path.insert(0, str(root / "src"))
    try:
        from gangware.core.config import ConfigManager  # type: ignore
    except Exception as e:  # pragma: no cover
        print(f"Failed to import ConfigManager: {e}")
        sys.exit(1)

    assets = _assets_dir()
    menus_dir = assets / "menus"
    if not menus_dir.exists():
        print(f"No assets/menus directory found at {menus_dir}")
        sys.exit(1)

    # Resolve menu screenshots by stem name across png/jpg/jpeg
    def find_by_stem(stem: str) -> Path | None:
        exts = (".png", ".jpg", ".jpeg")
        # direct checks first
        for ext in exts:
            p = menus_dir / f"{stem}{ext}"
            if p.exists():
                return p
            # also try capitalized variants
            p2 = menus_dir / f"{stem.capitalize()}{ext}"
            if p2.exists():
                return p2
        # fallback: scan directory
        for cand in menus_dir.iterdir():
            if cand.suffix.lower() in exts and cand.stem.lower() == stem.lower():
                return cand
        return None

    shots: Dict[str, Path] = {}
    stems = {
        "MAIN_MENU": "main_menu",
        "SELECT_GAME": "select_game",
        "SERVER_BROWSER": "server_browser",
    }
    for key, stem in stems.items():
        p = find_by_stem(stem)
        if p is None:
            print(f"Warning: missing screenshot for {key} (expected {stem}.[png|jpg|jpeg])")
            continue
        shots[key] = p

    if not shots:
        print("No screenshots found in assets/menus.")
        sys.exit(1)

    anchors_dir = assets / "anchors"
    anchors_dir.mkdir(parents=True, exist_ok=True)
    preview_dir = assets / "anchors_preview"
    preview_dir.mkdir(parents=True, exist_ok=True)

    cfg = ConfigManager()  # writes to %APPDATA%/Gangware/config.ini

    for key in ["MAIN_MENU", "SELECT_GAME", "SERVER_BROWSER"]:
        shot = shots.get(key)
        if shot is None:
            continue
        bgr = cv2.imread(str(shot))
        if bgr is None:
            print(f"Skip unreadable: {shot}")
            continue

        gray_small, edge_small, s = _normalize_gray(bgr)
        bands = _bands_for(key)
        rects_small = _pick_top_k(gray_small, edge_small, bands, k=2)

        # Map rects back to original pixels for cropping and to fractions for ini
        h_small, w_small = gray_small.shape[:2]
        h0, w0 = bgr.shape[:2]
        inv = 1.0 / max(s, 1e-6)

        # Build names and crops
        anchors_for_ini: List[Tuple[str, Tuple[float, float, float, float]]] = []
        anno = bgr.copy()
        for i, (xs, ys, ws, hs) in enumerate(rects_small, start=1):
            x = int(round(xs * inv))
            y = int(round(ys * inv))
            w = int(round(ws * inv))
            h = int(round(hs * inv))

            # Clamp to image bounds
            x = max(0, min(x, w0 - 1))
            y = max(0, min(y, h0 - 1))
            w = max(4, min(w, w0 - x))
            h = max(4, min(h, h0 - y))

            # Fractions for config (resolution-agnostic)
            fx, fy = x / float(w0), y / float(h0)
            fw, fh = w / float(w0), h / float(h0)

            # File name per requirement
            base_name = {
                "MAIN_MENU": f"Main_Menu_{i}",
                "SELECT_GAME": f"Select_Game_{i}",
                "SERVER_BROWSER": f"Server_Browser_{i}",
            }[key]

            out_path = anchors_dir / f"{base_name}.png"
            crop = bgr[y : y + h, x : x + w]
            try:
                cv2.imwrite(str(out_path), crop)
            except Exception:
                pass

            # Annotate preview
            cv2.rectangle(anno, (x, y), (x + w, y + h), (0, 220, 255) if i == 1 else (0, 200, 0), 2)
            cv2.putText(
                anno,
                base_name,
                (x, max(0, y - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

            anchors_for_ini.append((base_name, (fx, fy, fw, fh)))

        # Save preview
        try:
            cv2.imwrite(str(preview_dir / f"{key.lower()}_preview.png"), anno)
        except Exception:
            pass

        # Persist into user config.ini
        _write_ini_anchors(cfg, key, anchors_for_ini, src_h=bgr.shape[0])

        print(f"{key}: saved {len(anchors_for_ini)} anchors -> {anchors_dir}")

    print("Done. Anchors written to assets/anchors and user config.ini (AppData\\Roaming\\Gangware\\config.ini).")


if __name__ == "__main__":
    main()
