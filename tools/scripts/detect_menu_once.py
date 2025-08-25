from __future__ import annotations

import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "src"))

from gangware.vision.menu_detector import MenuDetector  # noqa: E402
from gangware.io import win as w32  # noqa: E402


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    # Quick one-off capture using mss for reliability.
    # This fallback uses mss for reliability.
    sys.path.insert(0, str(root / "src"))
    try:
        import mss  # type: ignore
        import numpy as np  # type: ignore
    except Exception as e:  # pragma: no cover
        print(f"Missing deps for capture: {e}")
        sys.exit(1)

    with mss.mss() as sct:
        region = w32.get_ark_window_region() or sct.monitors[1]
        shot = sct.grab(region)
        frame = np.array(shot)
        frame_bgr = frame[:, :, :3][:, :, ::-1]  # BGRA->BGR

    det = MenuDetector()
    menu, anchor, score, ok = det.detect(frame_bgr)
    if ok and menu:
        print(f"Detected: {menu} via {anchor} (score={score:.3f})")
    else:
        print(
            "No confident match" + (
                f". Best guess: {anchor} in {menu} (score={score:.3f})" if menu and anchor else "."
            )
        )


if __name__ == "__main__":
    main()
