"""ROI capture service.

Encapsulates the two-press F6 ROI capture flow:
- First press: mark pending ROI capture in the overlay
- Second press: finalize ROI from two corners, clamp to current monitor bounds
- Convert to relative (for persistence) and absolute (for session)
- Persist relative ROI to config, update overlay and log informational messages
- Optionally save a small snapshot of the ROI for user confirmation

This keeps orchestration modules smaller and focused.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple, Protocol, runtime_checkable

# Optional dependencies
try:
    import mss  # type: ignore
except Exception:  # pragma: no cover
    mss = None  # type: ignore

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None  # type: ignore

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore

from ..win32 import utils as w32


@runtime_checkable
class OverlayLike(Protocol):
    def set_status(self, text: str) -> None: ...
    def set_roi_status(self, ok: bool, roi_text: Optional[str] = None) -> None: ...


@runtime_checkable
class ConfigLike(Protocol):
    config: dict
    def save(self) -> None: ...


def roi_first_press(overlay: Optional[OverlayLike]) -> None:
    """Update the overlay to indicate the first ROI corner was stored."""
    if isinstance(overlay, OverlayLike):
        try:
            overlay.set_status("ROI: first corner saved. Move to bottom-right and press F6 again.")
            overlay.set_roi_status(False)
        except Exception:
            pass


def roi_finalize(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    config_manager: object,
    overlay: Optional[OverlayLike] = None,
) -> Optional[Tuple[str, str, Optional[str]]]:
    """Finalize ROI from two corners and persist.

    Returns:
        (abs_roi_str, rel_roi_str, snapshot_path) or None on invalid (too small) ROI.
    """
    # Normalize to left/top/width/height
    left = int(min(x1, x2))
    top = int(min(y1, y2))
    width = int(abs(x2 - x1))
    height = int(abs(y2 - y1))

    if width < 8 or height < 8:
        if isinstance(overlay, OverlayLike):
            try:
                overlay.set_status("ROI too small — press F6 twice again.")
            except Exception:
                pass
        return None

    # Clamp to monitor bounds
    mb = w32.current_monitor_bounds()
    left = max(mb["left"], min(left, mb["left"] + mb["width"] - width))
    top = max(mb["top"], min(top, mb["top"] + mb["height"] - height))

    abs_roi_str = f"{left},{top},{width},{height}"
    rel_roi_str = w32.absolute_to_relative_roi(abs_roi_str, mb)

    # Persist relative ROI
    try:
        if isinstance(config_manager, ConfigLike):
            config_manager.config["DEFAULT"]["vision_roi"] = rel_roi_str
            try:
                config_manager.save()
            except Exception:
                pass
        else:
            cfg = getattr(config_manager, "config", None)
            if cfg is not None:
                cfg["DEFAULT"]["vision_roi"] = rel_roi_str
                save_fn = getattr(config_manager, "save", None)
                if callable(save_fn):
                    try:
                        save_fn()
                    except Exception:
                        pass
        logging.getLogger(__name__).info("F6: saved relative ROI: %s (absolute: %s)", rel_roi_str, abs_roi_str)
    except Exception:
        pass

    # Save snapshot for confirmation (optional, best effort)
    snapshot_path: Optional[str] = None
    try:
        if mss is not None and np is not None and cv2 is not None:
            with mss.mss() as sct:  # type: ignore[attr-defined]
                region = {"left": left, "top": top, "width": width, "height": height}
                grabbed = sct.grab(region)
                bgr = np.array(grabbed)[:, :, :3]
            base_dir = Path(getattr(config_manager, "config_path")).parent
            out_dir = base_dir / "templates"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / "roi.png"
            try:
                cv2.imwrite(str(out_path), bgr)
                snapshot_path = str(out_path)
            except Exception:
                snapshot_path = None
    except Exception:
        snapshot_path = None

    # Overlay updates
    if isinstance(overlay, OverlayLike):
        try:
            if snapshot_path:
                overlay.set_status(
                    f"ROI set to {width}x{height} at ({left},{top}) [Relative: {rel_roi_str[:20]}...]. "
                    f"Saved snapshot: {snapshot_path}. F6 twice to change."
                )
            else:
                overlay.set_status(
                    f"ROI set to {width}x{height} at ({left},{top}) [Relative]. (Snapshot save failed.) F6 twice to change."
                )
            overlay.set_roi_status(True, abs_roi_str)
        except Exception:
            pass

    return abs_roi_str, rel_roi_str, snapshot_path
