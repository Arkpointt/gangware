"""Calibration: template capture for the search bar (F8-based).

Encapsulates waiting for F8, capturing a small region around the cursor, clamping
it to the virtual screen, and saving under the user's templates directory.

This isolates OS-specific logic from controllers while preserving behavior.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional, Protocol, Any

from ...core.win32 import utils as w32

# Optional imports with proper typing
mss: Optional[Any]
np: Optional[Any]
cv2: Optional[Any]
try:
    import mss
    import numpy as np
    import cv2
except ImportError:  # pragma: no cover - optional in some environments
    mss = None
    np = None
    cv2 = None


class OverlayProtocol(Protocol):
    """Protocol for overlay objects with status methods."""
    def set_status(self, text: str) -> None: ...


user32 = w32.user32


def wait_and_capture_template(config_manager, overlay: Optional[OverlayProtocol] = None) -> Optional[Path]:
    """Block until F8 is pressed, then capture a 220x50 rectangle around the cursor.

    Returns the saved Path on success, or None on failure/cancel.
    """
    if user32 is None:
        if overlay and hasattr(overlay, "set_status"):
            overlay.set_status("Calibration is supported on Windows only.")
        return None

    # Wait for F8 press
    try:
        while True:
            is_down_f8 = bool(user32.GetAsyncKeyState(0x77) & 0x8000)
            if is_down_f8:
                break
            time.sleep(0.02)
        # Debounce: wait for release
        while bool(user32.GetAsyncKeyState(0x77) & 0x8000):
            time.sleep(0.02)
    except Exception:
        return None

    # Cursor position
    try:
        x, y = w32.cursor_pos()
    except Exception:
        return None

    # Capture rectangle around cursor
    w, h = 220, 50
    left = int(x - w // 2)
    top = int(y - h // 2)

    if mss is None or np is None or cv2 is None:
        return None

    try:
        with mss.mss() as sct:
            # Clamp to virtual bounds
            vb = sct.monitors[0]
            vleft = int(vb.get("left", 0))
            vtop = int(vb.get("top", 0))
            vright = vleft + int(vb.get("width", 0))
            vbottom = vtop + int(vb.get("height", 0))
            left = max(vleft, min(left, vright - w))
            top = max(vtop, min(top, vbottom - h))
            region = {"left": int(left), "top": int(top), "width": int(w), "height": int(h)}
            img = sct.grab(region)
            bgr = np.array(img)[:, :, :3]
    except Exception as e:
        logging.getLogger(__name__).exception("template: capture failed: %s", str(e))
        return None

    # Persist under templates/search_bar.png next to config.ini
    try:
        base_dir = Path(getattr(config_manager, "config_path")).parent
        out_dir = base_dir / "templates"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "search_bar.png"
        cv2.imwrite(str(out_path), bgr)
        return out_path
    except Exception as e:
        logging.getLogger(__name__).exception("template: save failed: %s", str(e))
        return None
