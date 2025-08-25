from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np  # type: ignore

from ...vision.menu_detector import MenuDetector
from ...io import win as w32


@dataclass
class MenuState:
    name: Optional[str]
    anchor: Optional[str]
    score: float
    ok: bool


class MenuWatcher:
    """Background watcher that detects the current ARK menu and updates a StateManager.

    Hysteresis: requires 2 consecutive frames above threshold to switch menus,
    and 3 consecutive frames below 0.60 to clear.
    """

    def __init__(self, state_manager, interval: float = 0.25, overlay=None) -> None:
        self.state = state_manager
        self.interval = interval
        self.det = MenuDetector()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._confirm = 0
        self._decay = 0
        self._overlay = overlay
        self._logger = logging.getLogger(__name__)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="autosim-menu-watch", daemon=True)
        self._thread.start()
        self._logger.info("AutoSim menu detection started (interval=%.2fs)", self.interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._logger.info("AutoSim menu detection stopped")

    def _run(self) -> None:
        try:
            import mss  # type: ignore
        except Exception as e:
            self._logger.error("AutoSim failed to import mss for screen capture: %s", e)
            return

        cur_menu: Optional[str] = None

        try:
            with mss.mss() as sct:
                while not self._stop.is_set():
                    try:
                        region = w32.get_ark_window_region() or sct.monitors[1]
                        shot = sct.grab(region)
                        frame = np.array(shot)
                        frame_bgr = frame[:, :, :3][:, :, ::-1]

                        menu, anchor, score, ok = self.det.detect(frame_bgr)

                        # Hysteresis logic
                        if ok and menu:
                            if cur_menu != menu:
                                self._confirm += 1
                                if self._confirm >= 2:
                                    cur_menu = menu
                                    self._confirm = 0
                                    self._decay = 0
                                    self.state.set("autosim_menu", MenuState(cur_menu, anchor, score, ok))
                                    # Log menu transition for user visibility
                                    self._logger.info("AutoSim detected menu: %s via %s (score=%.3f)",
                                                      cur_menu, anchor, score)
                                    # Overlay feedback (optional)
                                    try:
                                        if self._overlay and hasattr(self._overlay, "set_status_safe"):
                                            status_msg = f"Autosim: {cur_menu} via {anchor} ({score:.3f})"
                                            self._overlay.set_status_safe(status_msg)
                                    except Exception:
                                        pass
                            else:
                                # stable, just update score
                                self.state.set("autosim_menu", MenuState(cur_menu, anchor, score, ok))
                                self._decay = 0
                                # Debug log for score updates (helps with troubleshooting)
                                self._logger.debug("AutoSim stable: %s via %s (score=%.3f)",
                                                   cur_menu, anchor, score)
                        else:
                            self._confirm = 0
                            if score < 0.60:
                                self._decay += 1
                                if self._decay >= 3:
                                    if cur_menu is not None:  # Only log when transitioning from known to unknown
                                        self._logger.info("AutoSim lost menu detection (last=%s, score=%.3f)",
                                                          cur_menu, score)
                                    cur_menu = None
                                    self.state.set("autosim_menu", MenuState(None, None, score, False))
                                    try:
                                        if self._overlay and hasattr(self._overlay, "set_status_safe"):
                                            self._overlay.set_status_safe("Autosim: menu unknown")
                                    except Exception:
                                        pass
                                else:
                                    # Log intermediate detection failures for debugging
                                    self._logger.debug("AutoSim detection uncertain (decay=%d/3, score=%.3f)",
                                                       self._decay, score)

                        time.sleep(self.interval)
                    except Exception as e:
                        self._logger.warning("AutoSim detection cycle failed: %s", e)
                        time.sleep(self.interval)
        except Exception as e:
            self._logger.error("AutoSim thread crashed: %s", e)
        finally:
            self._logger.debug("AutoSim detection thread exiting")
