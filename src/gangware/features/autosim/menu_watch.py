from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np  # type: ignore

from ...vision.menu_detector import MenuDetector
from ...io import win as w32
from ...io.controls import InputController
from ...core.config import ConfigManager
from pathlib import Path
import cv2  # type: ignore


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

        # Input + config for quick fail popup handling
        self._input = InputController()
        self._config = ConfigManager()

        # Preload Connection_Failed template (optional, if present)
        try:
            base = Path(__file__).resolve().parents[4]
            self._cf_template_path = base / "assets" / "menus" / "connection_failed.jpg"
            self._cf_template: Optional[np.ndarray]
            if self._cf_template_path.exists():
                img = cv2.imread(str(self._cf_template_path), cv2.IMREAD_COLOR)
                self._cf_template = img if img is not None else None
            else:
                self._cf_template = None
        except Exception:
            self._cf_template = None

        # Hysteresis + cooldown for popup detection
        self._cf_hits = 0
        self._cf_cooldown_until = 0.0
        # Tight ROI (fractions of ARK window rect) for modal zone
        self._cf_roi = (0.20, 0.20, 0.80, 0.82)  # single default (kept for compatibility)
        # Multi-ROI support: list of fractional ROIs, default to [self._cf_roi]
        self._cf_rois = [self._cf_roi]
        rois_env = os.getenv("GW_CF_ROIS", "").strip()
        if rois_env:
            # Parse formats like: "0.2,0.2,0.8,0.82;0.10,0.18,0.90,0.86" (also supports '|')
            parts = [p for chunk in rois_env.split(";") for p in chunk.split("|")]
            parsed = []
            for p in parts:
                vals = [v for v in p.replace(" ", "").split(",") if v]
                if len(vals) != 4:
                    continue
                try:
                    x1f, y1f, x2f, y2f = map(float, vals)
                    # Basic validation and clamping
                    x1f = max(0.0, min(1.0, x1f))
                    y1f = max(0.0, min(1.0, y1f))
                    x2f = max(0.0, min(1.0, x2f))
                    y2f = max(0.0, min(1.0, y2f))
                    if x2f > x1f and y2f > y1f:
                        parsed.append((x1f, y1f, x2f, y2f))
                except Exception:
                    continue
            if parsed:
                self._cf_rois = parsed
        # Dual thresholds: immediate strong hit, or two-frame softer hits
        self._cf_thresh_strong = 0.82
        self._cf_thresh_soft = 0.68
        # Debug score logging
        self._cf_dbg_last_log = 0.0
        self._cf_debug = bool(os.getenv("GW_CF_DEBUG"))
        # Last detected rectangle (absolute) for precise click fallback
        self._cf_last_rect = None

        # Tier-3: template-less modal popup heuristic thresholds
        self._modal_thresh_strong = 0.78
        self._modal_thresh_soft = 0.64
        self._modal_debug = bool(os.getenv("GW_MODAL_DEBUG"))

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

                        # Fast, gated popup handling during the post-Join window (any menu)
                        now = time.time()
                        # Global suppression (e.g., after Enter pressed by automation or watcher)
                        try:
                            suppress_until = float(self.state.get("autosim_cf_suppress_until", 0.0))
                        except Exception:
                            suppress_until = 0.0

                        if now >= self._cf_cooldown_until and now >= suppress_until:
                            # Respect post-Join gating window if present
                            try:
                                join_until = self.state.get("autosim_join_window_until", 0.0)
                            except Exception:
                                join_until = 0.0
                            if join_until and now > join_until:
                                # Window expired; do not scan aggressively
                                pass
                            else:
                                # Inside the post-Join window: perform detection (template + template-less)
                                cf_hit, cf_score, cf_rect = (False, 0.0, None)
                                if self._cf_template is not None:
                                    cf_hit, cf_score, cf_rect = self._detect_connection_failed_in_frame(frame_bgr)
                                mp_hit, mp_score, mp_rect = self._detect_modal_popup_in_frame(frame_bgr)

                                # Optional per-frame score debug (throttled)
                                if (self._cf_debug or self._modal_debug) and (now - self._cf_dbg_last_log) >= 0.15:
                                    self._logger.info(
                                        "AutoSim: scores CF=%.3f(h=%s) MODAL=%.3f(h=%s)",
                                        cf_score, "1" if cf_hit else "0", mp_score, "1" if mp_hit else "0",
                                    )
                                    self._cf_dbg_last_log = now

                                # Choose best signal
                                best_is_modal = mp_score >= cf_score
                                best_hit = (mp_hit if best_is_modal else cf_hit)
                                best_score = (mp_score if best_is_modal else cf_score)
                                best_rect = (mp_rect if best_is_modal else cf_rect)

                                if best_hit:
                                    # remember last rect for precise click fallback
                                    try:
                                        self._cf_last_rect = best_rect
                                    except Exception:
                                        self._cf_last_rect = None
                                    self._cf_hits = 0  # strong hit triggers immediately
                                    if best_is_modal:
                                        self._logger.info(
                                            "AutoSim: Modal popup detected (watcher, score=%.3f) → dismiss",
                                            best_score,
                                        )
                                    else:
                                        self._logger.info(
                                            "AutoSim: Connection_Failed detected (watcher, score=%.3f) → dismiss",
                                            best_score,
                                        )
                                    self._handle_connection_failed_quick()
                                    self._cf_hits = 0
                                    self._cf_cooldown_until = now + 2.0  # small cooldown to avoid spam
                                    # Also advertise global suppression so automation won't double-handle
                                    try:
                                        self.state.set("autosim_cf_suppress_until", now + 2.5)
                                    except Exception:
                                        pass
                                else:
                                    # soft accumulation logic using best score
                                    soft_thresh_any = min(self._cf_thresh_soft, self._modal_thresh_soft)
                                    if best_score >= soft_thresh_any:
                                        self._cf_hits += 1
                                    else:
                                        self._cf_hits = 0
                                    if self._cf_hits >= 2:
                                        try:
                                            # store best-effort rect on soft path as well
                                            if best_is_modal:
                                                _, _, rect2 = self._detect_modal_popup_in_frame(frame_bgr)
                                            else:
                                                _, _, rect2 = self._detect_connection_failed_in_frame(frame_bgr)
                                            self._cf_last_rect = rect2
                                        except Exception:
                                            self._cf_last_rect = None
                                        self._logger.info(
                                            "AutoSim: %s detected (watcher, soft last=%.3f) → dismiss",
                                            "Modal popup" if best_is_modal else "Connection_Failed",
                                            best_score,
                                        )
                                        self._handle_connection_failed_quick()
                                        self._cf_hits = 0
                                        self._cf_cooldown_until = now + 2.0
                                        try:
                                            self.state.set("autosim_cf_suppress_until", now + 2.5)
                                        except Exception:
                                            pass

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
                                        # If resume is armed and we just landed on a safe menu, signal resume
                                        try:
                                            arm_until = float(self.state.get("autosim_resume_arm_until", 0.0) or 0.0)
                                        except Exception:
                                            arm_until = 0.0
                                        if (
                                            cur_menu in ("SELECT_GAME", "MAIN_MENU")
                                            and arm_until
                                            and time.time() < arm_until
                                        ):
                                            try:
                                                self.state.set("autosim_resume_from", cur_menu)
                                                self.state.set("autosim_resume_arm_until", 0.0)
                                            except Exception:
                                                pass
                                            self._logger.info(
                                                "AutoSim: Resume armed, landed on %s → signaling resume",
                                                cur_menu,
                                            )
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

                        # Dynamic cadence: during join window, speed up to ~80ms
                        sleep_interval = self.interval
                        try:
                            join_until = self.state.get("autosim_join_window_until", 0.0)
                        except Exception:
                            join_until = 0.0
                        if join_until and time.time() < join_until:
                            sleep_interval = min(self.interval, 0.08)
                        time.sleep(sleep_interval)
                    except Exception as e:
                        self._logger.warning("AutoSim detection cycle failed: %s", e)
                        time.sleep(0.15)
        except Exception as e:
            self._logger.error("AutoSim thread crashed: %s", e)
        finally:
            self._logger.debug("AutoSim detection thread exiting")

    def _detect_connection_failed_in_frame(
        self,
        frame_bgr: np.ndarray,
    ) -> tuple[bool, float, Optional[tuple[int, int, int, int]]]:
        """Detect the Connection_Failed popup inside a tight ROI of the frame.

        Returns True on a confident match.
        """
        try:
            if self._cf_template is None:
                return (False, 0.0, None)

            h, w = frame_bgr.shape[:2]
            tpl_g = cv2.cvtColor(self._cf_template, cv2.COLOR_BGR2GRAY)

            best_val = -1.0
            best_rect = None
            for x1f, y1f, x2f, y2f in self._cf_rois:
                x1 = max(0, min(w, int(w * x1f)))
                y1 = max(0, min(h, int(h * y1f)))
                x2 = max(0, min(w, int(w * x2f)))
                y2 = max(0, min(h, int(h * y2f)))
                if x2 <= x1 or y2 <= y1:
                    continue

                roi = frame_bgr[y1:y2, x1:x2]
                roi_g = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

                th, tw = tpl_g.shape[:2]
                rh, rw = roi_g.shape[:2]
                if th >= rh or tw >= rw:
                    continue

                res = cv2.matchTemplate(roi_g, tpl_g, cv2.TM_CCOEFF_NORMED)
                _min_val, max_val, _min_loc, max_loc = cv2.minMaxLoc(res)
                if max_val > best_val:
                    tlx = int(x1 + max_loc[0])
                    tly = int(y1 + max_loc[1])
                    brx = int(tlx + tw)
                    bry = int(tly + th)
                    best_rect = (tlx, tly, brx, bry)
                    best_val = float(max_val)

            strong = best_val >= self._cf_thresh_strong if best_val >= 0 else False
            return (strong, max(0.0, best_val), best_rect)
        except Exception:
            return (False, 0.0, None)

    def _detect_modal_popup_in_frame(
        self,
        frame_bgr: np.ndarray,
    ) -> tuple[bool, float, Optional[tuple[int, int, int, int]]]:
        """Template-less heuristic to detect a centered modal popup within ROI.

        Uses contour/rectangularity and centrality. Returns (hit, score, rect).
        """
        try:
            h, w = frame_bgr.shape[:2]
            best_score = 0.0
            best_rect = None

            for x1f, y1f, x2f, y2f in self._cf_rois:
                x1 = max(0, min(w, int(w * x1f)))
                y1 = max(0, min(h, int(h * y1f)))
                x2 = max(0, min(w, int(w * x2f)))
                y2 = max(0, min(h, int(h * y2f)))
                if x2 <= x1 or y2 <= y1:
                    continue

                roi = frame_bgr[y1:y2, x1:x2]
                gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (5, 5), 0)
                edges = cv2.Canny(gray, 60, 150)
                edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
                edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

                contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if not contours:
                    continue

                rh, rw = roi.shape[:2]
                roi_area = float(rh * rw)
                cx_roi = rw / 2.0
                cy_roi = rh / 2.0

                for cnt in contours:
                    x, y, ww, hh = cv2.boundingRect(cnt)
                    area = float(ww * hh)
                    if area <= 1:
                        continue
                    frac = area / roi_area
                    if frac < 0.02 or frac > 0.40:
                        continue
                    ar = ww / float(hh)
                    if ar < 0.5 or ar > 2.6:
                        continue
                    cnt_area = float(cv2.contourArea(cnt))
                    rect_fill = cnt_area / area if area > 0 else 0.0

                    bx = x + ww / 2.0
                    by = y + hh / 2.0
                    dx = abs(bx - cx_roi) / (rw / 2.0)
                    dy = abs(by - cy_roi) / (rh / 2.0)
                    centrality = 1.0 - min(1.0, (dx + dy) / 2.0)

                    score = 0.55 * rect_fill + 0.20 * centrality + 0.25 * min(1.0, frac / 0.15)
                    if score > best_score:
                        best_score = score
                        best_rect = (x1 + x, y1 + y, x1 + x + ww, y1 + y + hh)

            strong = best_score >= self._modal_thresh_strong
            return (strong, float(best_score), best_rect)
        except Exception:
            return (False, 0.0, None)

    def _handle_connection_failed_quick(self) -> None:
        """Immediately close the popup and click Back to return from server browser.

        Keeps actions minimal to avoid stalling the watcher loop.
        """
        try:
            # Ensure Ark is foreground, then press Enter twice for reliability
            try:
                from ...core.win32.utils import ensure_ark_foreground
                ensure_ark_foreground(timeout=0.6)
            except Exception:
                pass
            self._input.press_key("enter")
            time.sleep(0.08)
            self._input.press_key("enter")
            time.sleep(0.10)

            # Fallback: if we have a last match rect, click center and lower-center once
            rect = getattr(self, "_cf_last_rect", None)
            if rect:
                try:
                    x1, y1, x2, y2 = rect
                    cx = (x1 + x2) // 2
                    cy = (y1 + y2) // 2
                    ly = int(y1 + 0.78 * (y2 - y1))  # lower area where OK often sits
                    self._input.move_mouse(cx, cy)
                    time.sleep(0.02)
                    self._input.click()
                    time.sleep(0.06)
                    self._input.move_mouse(cx, ly)
                    time.sleep(0.02)
                    self._input.click()
                except Exception:
                    pass

            # Menu-gated, bounded Back navigation (no Esc). Avoid spamming clicks.
            raw_coord = self._config.get("coord_back", None)
            coord_str = (raw_coord or "").strip()
            back_clicked = 0
            consecutive_sb = 0  # how many consecutive reads say SERVER_BROWSER
            deadline = time.time() + 3.0  # bounded verification window (allow UI settle)

            # Arm a cross-loop resume so if SELECT_GAME/MAIN_MENU is detected slightly later, we still resume
            try:
                self.state.set("autosim_resume_arm_until", time.time() + 4.0)
            except Exception:
                pass

            # Small grace period to allow the menu state to update after Enter/clicks
            time.sleep(0.10)

            while time.time() < deadline:
                st = None
                try:
                    st = self.state.get("autosim_menu")
                except Exception:
                    st = None

                name = getattr(st, "name", None)

                # Early exit as soon as we land on a safe resume menu
                if name in ("SELECT_GAME", "MAIN_MENU"):
                    try:
                        self.state.set("autosim_resume_from", name)
                    except Exception:
                        pass
                    self._logger.info("AutoSim: Resume after popup at %s", name)
                    break

                # Track consecutive confirmations of SERVER_BROWSER
                if name == "SERVER_BROWSER":
                    consecutive_sb += 1
                else:
                    consecutive_sb = 0

                # Perform at most two Back clicks, only after confirmation
                if coord_str and back_clicked < 1 and consecutive_sb >= 2:
                    try:
                        x, y = map(int, coord_str.split(","))
                        self._input.move_mouse(x, y)
                        time.sleep(0.02)
                        self._input.click()
                        self._logger.info("AutoSim: Clicked Back (1) from SERVER_BROWSER")
                        back_clicked += 1
                        consecutive_sb = 0
                    except Exception:
                        pass
                elif coord_str and back_clicked < 2 and consecutive_sb >= 3:
                    try:
                        x, y = map(int, coord_str.split(","))
                        self._input.move_mouse(x, y)
                        time.sleep(0.02)
                        self._input.click()
                        self._logger.info("AutoSim: Clicked Back (2) from SERVER_BROWSER")
                        back_clicked += 1
                        consecutive_sb = 0
                    except Exception:
                        pass

                time.sleep(0.12)

            # Overlay status (optional)
            try:
                if self._overlay and hasattr(self._overlay, "set_status_safe"):
                    self._overlay.set_status_safe("Autosim: closed popup, going back")
            except Exception:
                pass
        except Exception:
            # Ignore any input errors to keep watcher alive
            pass
