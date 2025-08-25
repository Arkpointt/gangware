from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "src"))

from gangware.vision.menu_detector import MenuDetector  # noqa: E402
from gangware.io import win as w32  # noqa: E402


def run(duration_sec: float = 15.0, interval_sec: float = 0.25) -> None:
    try:
        import mss  # type: ignore
        import numpy as np  # type: ignore
    except Exception as e:  # pragma: no cover
        print(f"Missing deps: {e}")
        sys.exit(1)

    det = MenuDetector()
    t0 = time.monotonic()
    next_log = t0
    last_menu = None
    last_ok = None
    last_anchor = None
    last_score = 0.0

    printed_ark_missing = False

    with mss.mss() as sct:
        while True:
            now = time.monotonic()
            if now - t0 >= duration_sec:
                break

            region = w32.get_ark_window_region()
            if region is None:
                if not printed_ark_missing:
                    print("[warn] ARK window not detected; capturing primary monitor.")
                    printed_ark_missing = True
                region = sct.monitors[1]

            shot = sct.grab(region)
            frame = np.array(shot)
            frame_bgr = frame[:, :, :3][:, :, ::-1]

            menu, anchor, score, ok = det.detect(frame_bgr)

            # Print on change or when confidence crosses threshold, else once per 2s heartbeat
            changed = (menu != last_menu) or (ok != last_ok) or (anchor != last_anchor)
            improved = score >= last_score + 0.05
            heartbeat = now >= next_log

            if changed or improved or heartbeat:
                ts = now - t0
                if ok and menu:
                    print(f"[{ts:5.2f}s] OK {menu:<14} via {anchor:<18} score={score:.3f}")
                else:
                    best = f"{anchor} in {menu}" if menu and anchor else "unknown"
                    print(f"[{ts:5.2f}s] .. {best:<22} score={score:.3f}")
                last_menu, last_ok, last_anchor, last_score = menu, ok, anchor, score
                next_log = now + 2.0

            time.sleep(interval_sec)


def main() -> None:
    ap = argparse.ArgumentParser(description="Live menu detector")
    ap.add_argument("--duration", type=float, default=15.0, help="Duration seconds (default 15)")
    ap.add_argument("--interval", type=float, default=0.25, help="Sample interval seconds (default 0.25)")
    args = ap.parse_args()
    run(args.duration, args.interval)


if __name__ == "__main__":
    main()
