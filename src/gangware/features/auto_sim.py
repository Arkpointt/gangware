"""
Auto Sim Orchestrator

A modular, template-driven automator to join an Ark Ascended server by server code.

Design goals:
- No fixed pixels. All interactions use template matching + existing VisionController.
- Runs in its own thread; start/stop via overlay signal                # step 1: ensure we're at main menu
                found_menu = False
                if self.templates.exists("main_menu"):
                    found_menu = self._wait_for_tpl("main_menu", self.cfg.min_conf_main, timeout_s=2.0)
                if not found_menu:
                    self._log_warn("main_menu_anchor_missing_or_unseen")
                    # For testing: Use calibrated coordinates first, then template fallback
                    if not self._click_calibrated("press_start"):
                        self._click_tpl("press_start", self.cfg.min_conf_main, timeout_s=1.2)
                backoff = self.cfg.backoff_initial
                idle_frames = 0ent loop with idle watchdog and bounded backoff.
- Commented and modular to avoid impacting existing systems.

Templates
---------
Users should place template PNGs under:
  %APPDATA%/Gangware/templates/auto_sim/
with the following names (all optional except noted):
- to_main.png           : Anchor visible on the main menu (required)
- main_play.png         : "Play" (or equivalent) button on main menu (required)
- select_type.png       : Button/icon to choose game type / server browser (required)
- select_image.png      : Image tile to proceed to server list (optional; only if needed)
- search_box.png        : Search input field in the server browser (required)
- server_row.png        : A snippet of the row area after filtering (optional; improves accuracy)
- join_button.png       : "Join" button/icon in the server list UI (required)
- server_full.png       : Indicator or modal when server is full (optional)
- join_failed.png       : Generic failure indicator (optional)
- ok_button.png         : OK/Close to dismiss failure modal (optional)
- back_button.png       : Back control to return one layer (optional)

Notes:
- You can capture these with any screenshot tool or reuse the app's F8 capture on specific UI elements.
- Keep crops tight (just the distinctive part of the control) to improve matching.

"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Tuple
import logging
import random as _rand
import ctypes
import mss
import numpy as np
import cv2


@dataclass
class SimConfig:
    min_conf_main: float = 0.35          # Lowered from 0.60 for faster recognition
    min_conf_field: float = 0.35         # Lowered from 0.60 for faster recognition
    min_conf_buttons: float = 0.35       # Lowered from 0.62 for faster recognition
    click_settle: float = 0.01           # Reduced from 0.035 for speed
    type_guard_first: float = 0.01       # Reduced from 0.035 for speed
    type_guard_space: float = 0.01       # Reduced from 0.020 for speed
    post_enter_delay: float = 0.02       # Reduced from 0.06 for speed
    find_timeout_s: float = 0.5          # Reduced from 3.0 for speed
    join_fail_wait_s: float = 10.0       # Reduced from 25.0 for speed
    join_success_assume_s: float = 15.0  # Reduced from 45.0 for speed
    idle_frames_threshold: int = 30
    backoff_initial: float = 0.05        # Reduced from 0.15 for speed
    backoff_max: float = 0.5             # Reduced from 1.5 for speed
    # Require seeing the left-side star icon in the server row before accepting any server match
    require_star_for_server: bool = True
    # Expected star position (normalized to Ark window) and narrow ROI margins for faster/safer detection
    star_expected_x_norm: float = 0.085677
    star_expected_y_norm: float = 0.303241
    # Tight ROI around expected star — roughly a ~2" box equivalent (half-side ~1") on common DPIs
    # On 4K (3840x2160), 1" ~96px => ~0.025W, ~0.044H. Tune here if needed.
    star_roi_margin_x_norm: float = 0.025   # +/- ~2.5% of width around expected x
    star_roi_margin_y_norm: float = 0.045   # +/- ~4.5% of height around expected y
    # Star-only mode: treat any valid star hit as "server available" and click based on star offset.
    # This bypasses header gating and row-template confirmation for a simpler, faster path.
    star_only_mode: bool = True
    # Normalized offset from star center to the desired click point on the row (relative to Ark window width/height)
    # Default derived from current calibrated norms: click_server.x (0.531510) - star.x (~0.085677) ~= 0.445833
    star_to_click_dx_norm: float = 0.445833
    # Vertical offset from star to row click; typically near zero. Downward bias is applied later in click stage.
    star_to_click_dy_norm: float = 0.000000


class TemplateLibrary:
    """Resolve template files from multiple roots with name synonyms.

    Search order (first hit wins):
    1) User templates under %APPDATA%/Gangware/templates/auto_sim
    2) Bundled assets under <project>/assets/auto sim
    """

    def __init__(self, user_dir: Path):
        self.user_dir = Path(user_dir)
        self.user_dir.mkdir(parents=True, exist_ok=True)
        # Try to resolve project assets dir robustly
        try:
            project_root = Path(__file__).resolve().parents[3]
            asset_dir = project_root / "assets" / "auto sim"
        except Exception:
            asset_dir = Path.cwd() / "assets" / "auto sim"
        self.asset_dir = asset_dir
        self.cache: Dict[str, Path] = {}
        # Build relaxed filename index for user and assets directories
        self._index_user = self._scan_dir(self.user_dir)
        self._index_asset = self._scan_dir(self.asset_dir)
        # Canonical -> candidate filename list (without extension)
        self.synonyms: Dict[str, Tuple[str, ...]] = {
            # Anchors
            "main_menu": ("main_menu", "Main_Menu"),
            "menu_selection": ("menu_selection", "Menu_Selection"),
            # Buttons / controls
            "press_start": ("press_start",),
            "join_game": ("join_game",),
            "select_type": ("select_type",),
            "select_image": ("select_image",),
            "search_box": ("search_box", "search"),
            "server_row": ("server_row",),
            "server_join": ("server_join",),
            # Legacy mappings retained for compatibility
            "to_main": ("to_main", "press_start"),
            "main_play": ("main_play", "press_start"),
            "join_button": ("join_button", "server_join", "join_game"),
            # Outcomes / dialogs
            "server_full": ("server_full",),
            "join_failed": ("join_failed", "connection_failed", "joining_failed"),
            "no_session": ("no_session",),
            "ok_button": ("ok_button",),
            "back_button": ("back_button", "back"),
            # Server clicking
            "click_server": ("click_server",),
            "click_server2": ("click_server2",),
            "click_server3": ("click_server3",),
            "click_server4": ("click_server4",),
            "click_server5": ("click_server5",),
            # Row signature icons
            # Include star_server_click explicitly (tight crop of the star icon) for robustness across backgrounds
            "server_star": ("server_star", "star_server_click", "star", "row_star", "favorite_star"),
            "server_star2": ("server_star2", "star2", "row_star2"),
            "row_star": ("row_star", "star_server_click"),
            "star_icon": ("star_server_click", "star_icon", "star"),
        }

    @staticmethod
    def _norm(stem: str) -> str:
        s = (stem or "").strip().lower()
        s = s.replace("-", "_").replace(" ", "_")
        out = []
        prev_us = False
        for ch in s:
            if ch.isalnum():
                out.append(ch)
                prev_us = False
            else:
                if not prev_us:
                    out.append("_")
                    prev_us = True
        norm = "".join(out).strip("_")
        while "__" in norm:
            norm = norm.replace("__", "_")
        return norm

    def _scan_dir(self, root: Path) -> Dict[str, Path]:
        idx: Dict[str, Path] = {}
        try:
            if root and root.exists():
                for p in root.iterdir():
                    if p.is_file() and p.suffix.lower() == ".png":
                        stem = p.stem
                        idx[self._norm(stem)] = p
                        # also index raw stem lower for extra tolerance
                        idx.setdefault(stem.lower(), p)
        except Exception:
            pass
        return idx

    def _resolve_stem(self, stem: str) -> Optional[Path]:
        # Try direct name.png first
        up = self.user_dir / f"{stem}.png"
        if up.exists():
            return up
        ap = self.asset_dir / f"{stem}.png"
        if ap.exists():
            return ap
        # Try normalized lookup
        key = self._norm(stem)
        if key in self._index_user:
            return self._index_user[key]
        if key in self._index_asset:
            return self._index_asset[key]
        # Try contains matching as last resort
        for k, v in self._index_user.items():
            if key and key in k:
                return v
        for k, v in self._index_asset.items():
            if key and key in k:
                return v
        return None

    def path(self, name: str) -> Optional[str]:
        # Cache on canonical name
        p = self.cache.get(name)
        if p is not None:
            return str(p)
        cands = self.synonyms.get(name, (name,))
        for cand in cands:
            hit = self._resolve_stem(cand)
            if hit is not None:
                self.cache[name] = hit
                return str(hit)
        return None

    def exists(self, name: str) -> bool:
        return self.path(name) is not None

    def ensure_required(self, names: Tuple[str, ...]) -> Tuple[bool, str]:
        missing = [n for n in names if not self.path(n)]
        if missing:
            desc = f"Missing templates: {', '.join(missing)} in {self.user_dir} or {self.asset_dir}"
            return False, desc
        return True, ""


class AutoSimRunner:
    """Template-driven Ark server auto-joiner."""

    def __init__(self, config_manager, vision_controller, input_controller, overlay=None, logger: Optional[logging.Logger] = None):
        self.cfg = SimConfig()
        self.config_manager = config_manager
        self.vision = vision_controller
        self.input = input_controller
        self.overlay = overlay
        self.logger = logger or logging.getLogger("gangware.features.auto_sim")
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        # Resolve template directories
        base_dir = self.config_manager.config_path.parent
        self.templates = TemplateLibrary(base_dir / "templates" / "auto_sim")
        self._running = threading.Event()

    # --------------- Public API ---------------
    def start(self, server_code: str) -> None:
        """Start the sim loop with the provided server code."""
        code = (server_code or "").strip()
        if not code:
            self._status("Sim: enter a server code to start.")
            return
        # Correlation/run id for support logs
        try:
            self._run_id = f"SIM-{int(time.time())}-{_rand.randint(1000,9999)}"
        except Exception:
            self._run_id = f"SIM-{int(time.time())}"
        # Preflight: list resolved templates for quick visibility
        req = ("press_start", "join_game", "search_box", "server_join")
        opt = ("main_menu", "menu_selection")
        resolved = {name: (self.templates.path(name) or "<missing>") for name in (*req, *opt)}
        lines = [f"  {k}: {v}" for k, v in resolved.items()]
        self._status(
            "Sim: starting for %s\nTemplates:\n%s\nIf any are <missing>, add them under %%APPDATA%%/Gangware/templates/auto_sim or assets/auto sim." %
            (code, "\n".join(lines))
        )
        self._log_info("start", code=code, resolved={k: (v != "<missing>") for k, v in resolved.items()})
        if any(resolved[k] == "<missing>" for k in req):
            self._log_warn("missing_templates", missing=[k for k in req if resolved[k] == "<missing>"])
            # Do not start if core templates are missing
            return
        if self._running.is_set():
            self._status("Sim: already running — restarting with new code…")
            self._log_info("restart_running", code=code)
            self.stop(join=True)
        self._stop.clear()
        t = threading.Thread(target=self._run, args=(code,), daemon=True)
        self._thread = t
        self._running.set()
        t.start()

    def stop(self, join: bool = False) -> None:
        """Request the sim to stop and optionally join the thread."""
        self._stop.set()
        if join and self._thread and self._thread.is_alive():
            try:
                self._thread.join(timeout=2.0)
            except Exception:
                pass
        self._running.clear()
        self._status("Sim: stopped.")

    def _detect_current_state(self) -> str:
        """Detect current UI state to allow resuming from any point"""
        try:
            self._log_info("state_detection_step", step="checking_templates")

            # Check in order of specificity - most unique templates first

            # Check for main menu (press_start visible) - FIRST priority
            if self.templates.exists("press_start"):
                path = self.templates.path("press_start")
                if path:
                    self._log_info("state_detection_step", step="checking_press_start")
                    coords = self.vision.find_template(path, confidence=0.30)  # Even lower confidence to catch main menu reliably
                    if coords:
                        self._log_info("state_detected", state="main_menu")
                        return "main_menu"

            # Check for join game screen (join_game button visible)
            if self.templates.exists("join_game"):
                path = self.templates.path("join_game")
                if path:
                    self._log_info("state_detection_step", step="checking_join_game")
                    coords = self.vision.find_template(path, confidence=0.40)  # Lower confidence
                    if coords:
                        self._log_info("state_detected", state="join_screen")
                        return "join_screen"

            # Check for server browser (search box visible) - LAST priority with very high confidence
            if self.templates.exists("search_box"):
                path = self.templates.path("search_box")
                if path:
                    self._log_info("state_detection_step", step="checking_search_box")
                    coords = self.vision.find_template(path, confidence=0.40)  # Lower confidence
                    if coords:
                        self._log_info("state_detected", state="server_browser")
                        return "server_browser"

            # Default: unknown state, start from beginning
            self._log_info("state_detected", state="unknown")
            return "unknown"

        except Exception as e:
            self._log_warn("state_detection_failed", error=str(e))
            return "unknown"    # --------------- Core loop ---------------
    def _run(self, server_code: str):
        self._log_info("_run_started", server_code=server_code)
        req_ok, msg = self.templates.ensure_required((
            "press_start", "join_game", "search_box", "server_join",
        ))
        if not req_ok:
            self._status(msg)
            self._log_warn("ensure_required_failed", msg=msg)
            self._running.clear()
            return

        self._log_info("templates_validated", message="All required templates found")

        # main loop until success or external stop
        # backoff = self.cfg.backoff_initial  # For potential future use
        # idle_frames = 0  # For potential future use
        restarting_after_no_session = False

        # Adaptive state detection - determine where we are in the UI flow
        self._log_info("starting_state_detection")
        try:
            current_state = self._detect_current_state()
            self._log_info("adaptive_start", detected_state=current_state)
        except Exception as e:
            self._log_error("state_detection_error", error=str(e))
            current_state = "unknown"
            self._log_info("adaptive_start", detected_state=current_state)

        # Hide overlay and wait 2 seconds before starting the loop
        self._log_info("hiding_overlay_and_waiting")
        self._status("Sim: Starting in 2 seconds...")
        try:
            if self.overlay and hasattr(self.overlay, 'set_visible'):
                self.overlay.set_visible(False)
                self._log_info("overlay_hidden")
        except Exception as e:
            self._log_warn("overlay_hide_failed", error=str(e))

        # Wait 2 seconds
        self._sleep(2.0)
        self._log_info("startup_delay_complete")

        try:
            self._log_info("entering_main_loop")
            while not self._stop.is_set():
                self._log_info("main_loop_iteration", current_state=current_state)

                # Initialize server detection variables for each loop iteration
                detected_server_coords = None
                detected_server_template = None

                # Adaptive start: skip steps based on detected state
                skip_to_server_browser = (current_state == "server_browser")
                skip_to_join_game = (current_state == "join_screen")

                self._log_info("skip_flags", skip_to_server_browser=skip_to_server_browser, skip_to_join_game=skip_to_join_game)

                if current_state == "in_game":
                    self._log_info("already_in_game")
                    self._status("Sim: already in game - stopping")
                    break

                # Clear state after first iteration
                if current_state:
                    self._log_info("clearing_initial_state", was=current_state)
                    current_state = None

                # step 1: press start (skip if we're already past this)
                if not skip_to_server_browser and not skip_to_join_game:
                    # Try to detect main menu first, but proceed regardless
                    found_menu = False
                    if self.templates.exists("main_menu"):
                        found_menu = self._wait_for_tpl("main_menu", self.cfg.min_conf_main, timeout_s=0.5)
                        if found_menu:
                            self._log_info("main_menu_detected")

                    # Always attempt to click press_start (whether main_menu was found or not)
                    if restarting_after_no_session:
                        self._log_info("restart_skip_press_start", message="Skipping press_start after Back; will click join_game directly")
                        self._sleep(0.5)  # small settle time
                    else:
                        # Click press_start - try calibrated first, then template fallback
                        self._log_info("clicking_press_start", main_menu_found=found_menu)
                        if not self._click_calibrated("press_start"):
                            self._click_tpl("press_start", self.cfg.min_conf_main, timeout_s=0.5)

                    # Variables for potential future use
                    # backoff = self.cfg.backoff_initial
                    # idle_frames = 0

                # step 2: click Join Game (skip if we're already in server browser)
                if not skip_to_server_browser:
                    # If restarting after no_session, use calibrated Ark-window coordinates and only clear flag on success
                    if restarting_after_no_session:
                        self._log_info("restart_immediate_join", message="Immediate join_game click after back button")
                        # Minimal settle time after back button - UI should be ready
                        self._sleep(0.5)

                        # Try calibrated coordinates first for speed (most reliable after back button)
                        clicked = self._click_calibrated("join_game")

                        if not clicked:
                            # Fast template fallback with very short timeout
                            clicked = self._click_tpl("join_game", 0.30, timeout_s=0.5)

                        # If still not clicked, force immediate normalized click
                        if not clicked:
                            try:
                                rect = self._get_ark_rect_by_proc() or self._get_virtual_screen_rect()
                                if rect:
                                    L, T, R, B = rect
                                    W = max(1, R - L)
                                    H = max(1, B - T)
                                    nx, ny = (0.286458, 0.534722)  # Use correct calibrated coordinates
                                    fx = L + int(nx * W)
                                    fy = T + int(ny * H)
                                    self._log_info("restart_force_immediate_click", norm_x=nx, norm_y=ny, x=fx, y=fy)
                                    self.input.move_mouse(fx, fy)
                                    self._sleep(0.02)
                                    self.input.click_button('left', presses=1, interval=0.0)
                                    self._sleep(self.cfg.click_settle)
                                    clicked = True
                            except Exception:
                                pass

                        if clicked:
                            restarting_after_no_session = False
                            self._log_info("restart_join_clicked", message="Successfully clicked join_game after restart")
                        else:
                            self._log_warn("restart_join_failed", message="Failed to click join_game after restart")
                    else:
                        # Normal flow: Try calibrated coordinates first, then template fallback
                        self._log_info("normal_join_game_click")
                        if not self._click_calibrated("join_game"):
                            # Simple template fallback - just try to click join_game directly
                            self._click_tpl("join_game", max(self.cfg.min_conf_main, 0.35), timeout_s=0.5)

                    # Wait for transition after clicking join_game
                    self._log_info("waiting_for_transition", duration_s=0.5)
                    self._sleep(0.5)

                # step 3: focus search, type code, apply (300ms target)
                if not self._focus_search_and_type(server_code):
                    # couldn't find search; go back and retry
                    self._log_warn("search_not_found")
                    self._press_esc()
                    continue

                # step 4: wait for search results to load and check for servers
                self._sleep(0.5)  # Wait for search results to populate (reduced from 1.0s)
                self._log_info("search_results_wait_complete", message="0.5 second wait completed, checking for server availability")

                # Check if we can find any content in the server list area (this indicates servers are available)
                server_content_available = False

                # OPTIMIZATION 1: Use content variance detection for speed and reliability
                start_time = time.perf_counter()

                # OPTIMIZATION 5: Set ROI to server list area only (huge speed boost)
                # Server list is typically in the center-right area of the screen
                # This reduces search area by ~80%, making detection 5x faster
                try:
                    # Get window bounds and set server list ROI
                    window_dict = self._get_ark_window_region()
                    if window_dict:
                        # Extract coordinates from dictionary
                        left = int(window_dict['left'])
                        top = int(window_dict['top'])
                        width = int(window_dict['width'])
                        height = int(window_dict['height'])
                        right = left + width
                        bottom = top + height

                        # Server list is roughly in right 60% of window, center 70% vertically
                        roi_left = left + int(width * 0.4)   # Start at 40% from left
                        roi_top = top + int(height * 0.15)    # Start at 15% from top
                        roi_right = right - int(width * 0.05) # End at 95% from left
                        roi_bottom = bottom - int(height * 0.15) # End at 85% from bottom

                        server_roi = (roi_left, roi_top, roi_right, roi_bottom)
                        # Apply server list ROI to vision (override any manual ROI), store previous to restore later
                        prev_server_roi = getattr(self.vision, 'search_roi', None)
                        try:
                            if hasattr(self.vision, 'set_search_roi'):
                                self.vision.set_search_roi({
                                    "left": roi_left,
                                    "top": roi_top,
                                    "width": max(1, roi_right - roi_left),
                                    "height": max(1, roi_bottom - roi_top),
                                })
                            self._log_info("server_roi_applied", left=roi_left, top=roi_top, width=max(1, roi_right - roi_left), height=max(1, roi_bottom - roi_top))

                            # Further refine ROI to the server rows band (exclude header like 'DAY').
                            # Use normalized expected server Y (~0.301) and keep a safe band below it.
                            try:
                                expected_server_y_norm = 0.301389
                                band_top_norm = max(0.0, expected_server_y_norm - 0.03)   # ~0.271 -> ~586px on 2160p
                                # Keep a generous band height to include first rows
                                band_bottom_norm = min(1.0, expected_server_y_norm + 0.25) # ~0.551 -> ~1190px on 2160p

                                row_top = max(roi_top, top + int(height * band_top_norm))
                                row_bottom = min(roi_bottom, top + int(height * band_bottom_norm))

                                # Only apply if we still have a positive height
                                if row_bottom > row_top + 10:
                                    if hasattr(self.vision, 'set_search_roi'):
                                        self.vision.set_search_roi({
                                            "left": roi_left,
                                            "top": row_top,
                                            "width": max(1, roi_right - roi_left),
                                            "height": max(1, row_bottom - row_top),
                                        })
                                    self._log_info("server_row_band_applied",
                                        left=roi_left,
                                        top=row_top,
                                        width=max(1, roi_right - roi_left),
                                        height=max(1, row_bottom - row_top)
                                    )
                                # Detect header divider line and exclude any detection above it
                                header_bottom_val = None
                                try:
                                    header_bottom_val = self._detect_header_bottom({"left": left, "top": top, "width": width, "height": height}, (roi_left, roi_top, roi_right, roi_bottom))
                                except Exception:
                                    header_bottom_val = None

                                if header_bottom_val is not None:
                                    # Adjust the ROI to start strictly below header_bottom
                                    new_top = max(row_top if 'row_top' in locals() else roi_top, int(header_bottom_val))
                                    if new_top < (row_bottom if 'row_bottom' in locals() else roi_bottom) - 5:
                                        if hasattr(self.vision, 'set_search_roi'):
                                            self.vision.set_search_roi({
                                                "left": roi_left,
                                                "top": new_top,
                                                "width": max(1, roi_right - roi_left),
                                                "height": max(1, (row_bottom if 'row_bottom' in locals() else roi_bottom) - new_top),
                                            })
                                        self._log_info("header_exclusion_applied", header_bottom=int(header_bottom_val), new_top=int(new_top))
                            except Exception:
                                # If any error, continue with the broader server ROI
                                pass
                        except Exception:
                            pass

                        # Primary detection: prefer left star icon cluster (row signature) if templates are provided
                        server_content_available = False  # Default to no servers
                        star_found_and_accepted = False
                        # Prepare detection containers early so star pass can feed click stage
                        detected_server_coords = None
                        detected_server_template = None

                        # Attempt star-icon detection first (more distinctive than header text)
                        # Prefer the tight star-only crop if available
                        star_templates = [t for t in ("star_icon", "server_star", "row_star", "server_star2") if self.templates.exists(t)]
                        if star_templates:
                            self._log_info("checking_star_templates", templates=star_templates)
                            # Narrow ROI around expected star position to avoid false candidates elsewhere.
                            # Use the Ark window bounds for this ROI rather than the broader server list ROI.
                            exp_x = left + int(self.cfg.star_expected_x_norm * width)
                            exp_y = top + int(self.cfg.star_expected_y_norm * height)
                            mx = int(self.cfg.star_roi_margin_x_norm * width)
                            my = int(self.cfg.star_roi_margin_y_norm * height)
                            star_left = max(left, exp_x - mx)
                            star_right = min(left + width, exp_x + mx)
                            star_top = max(top, exp_y - my)
                            star_bottom = min(top + height, exp_y + my)
                            # Ensure a small minimum ROI size to avoid degenerate boxes (at least 16x16)
                            if star_right - star_left < 16:
                                pad = (16 - (star_right - star_left)) // 2
                                star_left = max(left, star_left - pad)
                                star_right = min(left + width, star_right + pad)
                            if star_bottom - star_top < 16:
                                pad = (16 - (star_bottom - star_top)) // 2
                                star_top = max(top, star_top - pad)
                                star_bottom = min(top + height, star_bottom + pad)
                            # Log expected geometry upfront for easier diagnosis
                            self._log_info(
                                "star_expected",
                                window_left=int(left), window_top=int(top), window_w=int(width), window_h=int(height),
                                exp_x=int(exp_x), exp_y=int(exp_y), margin_x=int(mx), margin_y=int(my)
                            )
                            if star_right > star_left and star_bottom > star_top:
                                prev_roi_for_star = getattr(self.vision, 'search_roi', None)
                                try:
                                    if hasattr(self.vision, 'set_search_roi'):
                                        self.vision.set_search_roi({
                                            "left": star_left,
                                            "top": star_top,
                                            "width": max(1, star_right - star_left),
                                            "height": max(1, star_bottom - star_top),
                                        })
                                    self._log_info("star_roi_applied", left=star_left, top=star_top, width=max(1, star_right - star_left), height=max(1, star_bottom - star_top))
                                except Exception:
                                    prev_roi_for_star = None
                            else:
                                prev_roi_for_star = None

                            # Stricter confidence for small icon; keep floor higher to avoid globe/highlight false positives
                            # Raised thresholds to be safer when resolution or scaling changes
                            star_conf_levels = (0.70, 0.66, 0.62, 0.58)
                            # Compute header bottom once for gating
                            header_bottom_for_star = None
                            try:
                                header_bottom_for_star = self._detect_header_bottom({"left": left, "top": top, "width": width, "height": height}, (roi_left, roi_top, roi_right, roi_bottom))
                            except Exception:
                                header_bottom_for_star = None

                            # Counters for diagnostics
                            star_attempts = 0
                            star_hits = 0
                            star_accepts = 0
                            for sname in star_templates:
                                if star_found_and_accepted:
                                    break
                                spath = self.templates.path(sname)
                                if not spath:
                                    continue
                                for sc in star_conf_levels:
                                    star_attempts += 1
                                    coords = self._find(spath, conf=float(sc), timeout_s=0.30)
                                    if not coords:
                                        continue
                                    star_hits += 1
                                    sx, sy = map(int, coords)
                                    # Header gating - prefer detected divider; fallback to row-band top if divider isn't detected (blur/scale)
                                    header_ok = (header_bottom_for_star is not None and sy > int(header_bottom_for_star))
                                    # Fallback band-top based gate (mirrors the earlier server_row_band range ~27%+ of height)
                                    band_top_norm = 0.271  # keep in sync with server_row_band_applied
                                    band_top_abs = max(roi_top, top + int(height * band_top_norm))
                                    band_ok = (header_bottom_for_star is None and sy > int(band_top_abs))
                                    header_or_band_ok = bool(header_ok or band_ok)
                                    # Proximity constraint: must be close to expected position
                                    prox_ok = (abs(sx - exp_x) <= mx and abs(sy - exp_y) <= my)
                                    # Left-edge constraint: use absolute expected band ± small tolerance
                                    left_band_min = left + int(0.06 * width)  # 6%
                                    left_band_max = left + int(0.13 * width) # 13%
                                    left_ok = (left_band_min <= sx <= left_band_max)
                                    self._log_info("star_candidate",
                                                  template=sname, coords=(sx, sy), conf=float(sc),
                                                  header_bottom=int(header_bottom_for_star) if header_bottom_for_star is not None else None,
                                                  header_ok=bool(header_ok), band_top=int(band_top_abs), band_ok=bool(band_ok), geom_ok=bool(header_or_band_ok), prox_ok=bool(prox_ok), left_band=f"{left_band_min}-{left_band_max}", left_ok=bool(left_ok))
                                    # In star-only mode we still require the geometric gates (header or band-top fallback)
                                    if getattr(self.cfg, 'star_only_mode', False) and not (header_or_band_ok and prox_ok and left_ok):
                                        reason = "header_and_band_failed" if not header_or_band_ok else ("proximity_failed" if not prox_ok else "left_band_failed")
                                        self._log_warn("star_coords_rejected", template=sname, coords=(sx, sy), reason=f"star_only_gate_{reason}")
                                        continue
                                    if header_or_band_ok and prox_ok and left_ok:
                                        # Quick row confirmation to avoid false positives: check for a row snippet near the star
                                        row_confirmed = False
                                        try:
                                            # Define a small ROI to the right of the star, same row band
                                            confirm_left = max(roi_left, sx + int(0.01 * width))
                                            confirm_right = min(roi_right, sx + int(0.22 * width))
                                            confirm_top = max(roi_top, sy - int(0.05 * height))
                                            confirm_bottom = min(roi_bottom, sy + int(0.06 * height))
                                            if confirm_right > confirm_left and confirm_bottom > confirm_top and hasattr(self.vision, 'set_search_roi'):
                                                prev_roi_confirm = getattr(self.vision, 'search_roi', None)
                                                try:
                                                    self.vision.set_search_roi({
                                                        "left": confirm_left,
                                                        "top": confirm_top,
                                                        "width": max(1, confirm_right - confirm_left),
                                                        "height": max(1, confirm_bottom - confirm_top),
                                                    })
                                                    # Try available row templates quickly
                                                    for row_name in ("click_server", "click_server2", "click_server3", "click_server4", "click_server5"):
                                                        if row_confirmed:
                                                            break
                                                        if not self.templates.exists(row_name):
                                                            continue
                                                        rpath = self.templates.path(row_name)
                                                        if rpath and self._find(rpath, conf=0.48, timeout_s=0.15):
                                                            row_confirmed = True
                                                            break
                                                finally:
                                                    try:
                                                        if prev_roi_confirm is not None:
                                                            self.vision.set_search_roi(prev_roi_confirm)
                                                    except Exception:
                                                        pass
                                        except Exception:
                                            row_confirmed = False

                                        self._log_info("star_row_confirmation", passed=bool(row_confirmed))
                                        # Secondary verification: if row isn't confirmed or templates are missing,
                                        # require a second star template to agree within a tiny ROI
                                        second_ok = False
                                        if not row_confirmed:
                                            alt_stars = [t for t in star_templates if t != sname and self.templates.exists(t)]
                                            if alt_stars:
                                                # Slightly wider pad for blur/scale; a bit taller than wide
                                                verify_pad_x = max(12, int(0.018 * width))
                                                verify_pad_y = max(12, int(0.024 * height))
                                                v_left = max(left, sx - verify_pad_x)
                                                v_right = min(left + width, sx + verify_pad_x)
                                                v_top = max(top, sy - verify_pad_y)
                                                v_bottom = min(top + height, sy + verify_pad_y)
                                                prev_roi_verify = getattr(self.vision, 'search_roi', None)
                                                try:
                                                    if hasattr(self.vision, 'set_search_roi') and v_right > v_left and v_bottom > v_top:
                                                        self.vision.set_search_roi({
                                                            "left": v_left,
                                                            "top": v_top,
                                                            "width": max(1, v_right - v_left),
                                                            "height": max(1, v_bottom - v_top),
                                                        })
                                                    for alt in alt_stars:
                                                        apath = self.templates.path(alt)
                                                        if not apath:
                                                            continue
                                                        # Slightly lower threshold to tolerate blur
                                                        vcoords = self._find(apath, conf=0.64, timeout_s=0.14)
                                                        if vcoords:
                                                            ax, ay = map(int, vcoords)
                                                            if abs(ax - sx) <= verify_pad_x and abs(ay - sy) <= verify_pad_y:
                                                                second_ok = True
                                                                break
                                                finally:
                                                    try:
                                                        if prev_roi_verify is not None and hasattr(self.vision, 'set_search_roi'):
                                                            self.vision.set_search_roi(prev_roi_verify)
                                                    except Exception:
                                                        pass
                                        self._log_info("star_secondary_verify", needed=not row_confirmed, second_ok=bool(second_ok))

                                        accept_this = False
                                        # Strong primary acceptance if geometric gates pass (helps blurred 1080p)
                                        strong_primary = (float(sc) >= 0.66)
                                        # In star-only mode, require either row_confirmed (if row templates exist) or second_ok
                                        if getattr(self.cfg, 'star_only_mode', False):
                                            any_row_tpl = any(self.templates.exists(rn) for rn in ("click_server", "click_server2", "click_server3", "click_server4", "click_server5"))
                                            if any_row_tpl:
                                                # Accept if row confirmed OR secondary star agreed OR strong primary match
                                                accept_this = bool(row_confirmed or second_ok or strong_primary)
                                            else:
                                                # Without row templates, accept strong primary or second_ok
                                                accept_this = bool(second_ok or strong_primary)
                                        else:
                                            # Non star-only: require row_confirmed
                                            accept_this = bool(row_confirmed)

                                        if not accept_this:
                                            reject_reason = "row_not_confirmed_near_star" if not row_confirmed else "secondary_star_verify_failed"
                                            self._log_warn("star_coords_rejected", template=sname, coords=(sx, sy), reason=reject_reason)
                                            continue

                                        # Compute the final click:
                                        if getattr(self.cfg, 'star_only_mode', False):
                                            # Derive click from star using normalized offset
                                            click_x = sx + int(self.cfg.star_to_click_dx_norm * width)
                                            click_y = sy + int(self.cfg.star_to_click_dy_norm * height)
                                            click_x = max(roi_left, min(roi_right - 1, int(click_x)))
                                            click_y = max(roi_top, min(roi_bottom - 1, int(click_y)))
                                            detected_server_coords = (int(click_x), int(click_y))
                                            detected_server_template = sname
                                            server_content_available = True
                                            star_found_and_accepted = True
                                            star_accepts += 1
                                            self._log_info("server_coords_detected",
                                                           template=sname,
                                                           coordinates=detected_server_coords,
                                                           validation="star_only_verified")
                                            break
                                        else:
                                            detected_server_coords = (sx, sy)
                                            detected_server_template = sname
                                            server_content_available = True
                                            star_found_and_accepted = True
                                            star_accepts += 1
                                            self._log_info("server_coords_detected",
                                                           template=sname,
                                                           coordinates=detected_server_coords,
                                                           validation="passed_star_geom_proximity_left")
                                            break
                                    else:
                                        reason = "geom_failed" if not header_or_band_ok else ("proximity_failed" if not prox_ok else "left_band_failed")
                                        self._log_warn("star_coords_rejected", template=sname, coords=(sx, sy), reason=reason)

                            # If we didn't accept any, provide a brief summary for debugging
                            if not star_found_and_accepted:
                                self._log_info(
                                    "star_scan_summary",
                                    attempts=int(star_attempts),
                                    hits=int(star_hits),
                                    accepts=int(star_accepts),
                                    note="Zero accepts; consider increasing margin or lowering confidence if star is visibly present"
                                )

                            # Restore the previous ROI after star detection pass
                            try:
                                if 'prev_roi_for_star' in locals() and isinstance(prev_roi_for_star, dict) and hasattr(self.vision, 'set_search_roi'):
                                    self.vision.set_search_roi(prev_roi_for_star)
                                    self._log_info("star_roi_restored")
                                elif 'prev_roi_for_star' in locals() and prev_roi_for_star is None and hasattr(self.vision, 'set_search_roi'):
                                    # Restore to rows ROI already applied earlier (do nothing) or clear if needed
                                    pass
                            except Exception:
                                pass
                        else:
                            self._log_warn("star_templates_missing", message="No star templates available; star-gated detection may fail if required")

                        # If star not found and not in star-only mode, check row button templates next
                        if not server_content_available and not getattr(self.cfg, 'star_only_mode', False):
                            self._log_info("checking_server_templates_for_absence", message="Looking for click_server templates to determine server availability")

                        # Progressive confidence levels for different visual conditions
                        # Lower values handle HDR, scaling, color variations, different resolutions
                        # Try stricter confidence first to ensure strong, band-shaped matches (masked template)
                        confidence_levels = [0.50, 0.45, 0.40]  # can tune if too strict

                        # Consolidated template checks using the helper - store detected coordinates
                        template_order = ["click_server", "click_server2", "click_server3", "click_server4", "click_server5"]
                        frame_bounds = (left, top, right, bottom)
                        # Do not reset detected_server_coords/template here; star pass may have set them already

                        for name in template_order:
                            if server_content_available:
                                break
                            if getattr(self.cfg, 'star_only_mode', False):
                                # In star-only mode we don't use row templates
                                break
                            if not self.templates.exists(name):
                                continue
                            # If star is required and we have not validated one, do not accept click_server detections
                            if self.cfg.require_star_for_server and not star_found_and_accepted:
                                self._log_warn("skipping_row_detection_without_star", template=name, reason="require_star_for_server is True and star not found/accepted")
                                continue
                            coords = self._check_server_template_enhanced(name, tuple(confidence_levels), frame_bounds)
                            if coords:
                                # Validate detected coordinates are within expected server list area
                                x, y = coords

                                # Server list area bounds (from ROI calculations above)
                                roi_left = left + int(width * 0.4)    # 40% from left
                                roi_top = top + int(height * 0.15)    # 15% from top
                                roi_right = right - int(width * 0.05) # 95% from left
                                roi_bottom = bottom - int(height * 0.15) # 85% from bottom

                                # Header geometry constraint: any detection must be strictly below header_bottom
                                header_bottom_val2 = None
                                try:
                                    header_bottom_val2 = self._detect_header_bottom({"left": left, "top": top, "width": width, "height": height}, (roi_left, roi_top, roi_right, roi_bottom))
                                except Exception:
                                    header_bottom_val2 = None

                                header_ok = True
                                if header_bottom_val2 is not None:
                                    header_ok = (y > int(header_bottom_val2))
                                    self._log_info("header_constraint_check", template=name, detected_y=int(y), header_bottom=int(header_bottom_val2), pass_check=bool(header_ok))

                                # Use hardcoded calibrated coordinates as reference for valid server area
                                # Hardcoded server coords: (0.531510, 0.301389) translates to roughly (2040, 651)
                                # Allow reasonable margin around these known-good coordinates
                                expected_server_x = left + int(width * 0.531510)  # ~2040 for 3840 width
                                expected_server_y = top + int(height * 0.301389)  # ~651 for 2160 height

                                # Define valid area with generous margins around expected server location
                                margin_x = int(width * 0.15)   # ±15% width margin
                                margin_y = int(height * 0.10)  # ±10% height margin

                                server_min_x = max(roi_left, expected_server_x - margin_x)
                                server_max_x = min(roi_right, expected_server_x + margin_x)
                                server_min_y = max(roi_top, expected_server_y - margin_y)
                                server_max_y = min(roi_bottom, expected_server_y + margin_y)

                                coords_valid = (server_min_x <= x <= server_max_x and server_min_y <= y <= server_max_y)
                                if not header_ok:
                                    coords_valid = False

                                self._log_info("coordinate_validation",
                                    template=name,
                                    detected_coords=coords,
                                    server_area_bounds=f"x:{server_min_x}-{server_max_x}, y:{server_min_y}-{server_max_y}",
                                    validation_result="valid" if coords_valid else "invalid"
                                )

                                if coords_valid:
                                    server_content_available = True
                                    detected_server_coords = coords
                                    detected_server_template = name
                                    self._log_info("server_coords_detected",
                                        template=name,
                                        coordinates=coords,
                                        validation="passed_coordinate_check_and_header_exclusion"
                                    )
                                    break
                                else:
                                    self._log_warn("server_coords_rejected",
                                        template=name,
                                        coordinates=coords,
                                        reason="coords_out_of_bounds_or_above_header",
                                        expected_bounds=f"x:{server_min_x}-{server_max_x}, y:{server_min_y}-{server_max_y}",
                                        message="Enhanced detection found something but coordinates don't match expected server location"
                                    )
                                    # Continue to next template

                        # Final determination
                        if not server_content_available:
                            if self.cfg.require_star_for_server and not star_found_and_accepted:
                                self._log_info("no_server_templates_detected", message="Star not found; skipping row detection because require_star_for_server=True")
                            else:
                                self._log_info("no_server_templates_detected", message="No click_server[1..5] templates found - no servers available")

                        detection_time = (time.perf_counter() - start_time) * 1000

                        self._log_info("server_availability_check",
                            roi=server_roi,
                            content_detected=server_content_available,
                            detection_time_ms=f"{detection_time:.1f}",
                            method="template_based"
                        )
                        # Restore previous ROI after server availability check
                        try:
                            if hasattr(self.vision, 'set_search_roi'):
                                if isinstance(prev_server_roi, dict):
                                    self.vision.set_search_roi(prev_server_roi)
                                elif hasattr(self.vision, 'clear_search_roi'):
                                    self.vision.clear_search_roi()
                            self._log_info("server_roi_cleared")
                        except Exception:
                            pass

                except Exception as e:
                    self._log_info("content_detection_failed", error=str(e))
                    # Always restore ROI on failure
                    try:
                        if 'prev_server_roi' in locals() and hasattr(self.vision, 'set_search_roi'):
                            if isinstance(prev_server_roi, dict):
                                self.vision.set_search_roi(prev_server_roi)
                            elif hasattr(self.vision, 'clear_search_roi'):
                                self.vision.clear_search_roi()
                        self._log_info("server_roi_cleared_after_error")
                    except Exception:
                        pass
                    # If template detection fails, default to NO servers (safer assumption)
                    # This prevents false positives when templates are missing or corrupted
                    server_content_available = False
                    self._log_info("template_error_fallback", message="Template detection failed, assuming no servers available for safety")

                # If no server content found, treat as "no session" and restart cycle
                if not server_content_available:
                    self._log_info("no_servers_detected", message="No content found in server list area - server not available, restarting cycle")
                    no_session_found = True
                    self._status("Sim: server not available — waiting 10s then restarting search...")

                    # Wait 10 seconds then restart the cycle (increased from 5s)
                    self._sleep(10.0)

                    # Go back and restart: back button → join game → search again
                    self._log_info("restarting_search_cycle", message="Going back to restart search")

                    # Click back button to return to main menu
                    if not self._click_calibrated("back"):
                        self._press_esc()  # Fallback if back button fails
                    self._sleep(0.5)  # Fast UI transition

                    # Set flag to use template matching on restart
                    restarting_after_no_session = True

                    # Restart from the beginning of the cycle
                    continue
                else:
                    self._log_info("servers_available", message="Content found in server list area, proceeding to server click")
                    no_session_found = False

                if not no_session_found:
                    self._log_info("proceeding_to_server_click", message="Server templates available, clicking server")

                # step 5: click on server in search results
                server_clicked = False

                # Try using detected coordinates first (most accurate) - but only if they passed validation
                if detected_server_coords and detected_server_template:
                    self._log_info("using_detected_server_coords", template=detected_server_template, coords=detected_server_coords)
                    if self._click_at_detected_coords(detected_server_coords, detected_server_template):
                        server_clicked = True
                    else:
                        self._log_warn("detected_coords_click_failed",
                            template=detected_server_template,
                            coords=detected_server_coords,
                            message="Click at detected coordinates failed - falling back to calibrated coordinates"
                        )

                # Fallback to calibrated coordinates if detection-based clicking failed or no valid detection
                if not server_clicked:
                    if detected_server_coords:
                        self._log_info("falling_back_to_calibrated_coords", message="Detection-based clicking failed, trying calibrated coordinates")
                    else:
                        self._log_info("using_calibrated_coords", message="No valid server coordinates detected, using calibrated coordinates")

                    # Try click_server first (we know it exists from previous check)
                    if self._click_calibrated("click_server"):
                        self._log_info("server_clicked", method="calibrated", template="click_server")
                        server_clicked = True
                    # Try click_server2 as alternative (we know it exists from previous check)
                    elif self._click_calibrated("click_server2"):
                        self._log_info("server_clicked", method="calibrated", template="click_server2")
                        server_clicked = True
                    elif self._click_calibrated("click_server3"):
                        self._log_info("server_clicked", method="calibrated", template="click_server3")
                        server_clicked = True
                    elif self._click_calibrated("click_server4"):
                        self._log_info("server_clicked", method="calibrated", template="click_server4")
                        server_clicked = True
                    elif self._click_calibrated("click_server5"):
                        self._log_info("server_clicked", method="calibrated", template="click_server5")
                        server_clicked = True

                if not server_clicked:
                    # Fallback: use keyboard down arrow to select first result
                    try:
                        self.input.press_key('down', presses=1, interval=0.0)
                        self._sleep(0.05)
                        self._log_info("server_selected", method="keyboard_fallback")
                    except Exception:
                        self._log_warn("server_selection_failed", message="All server selection methods failed")
                        # If server selection completely failed, restart cycle
                        continue

                # step 7: click server join button (300ms target)
                self._sleep(0.3)
                if not self._click_calibrated("server_join"):
                    if not self._click_tpl("server_join", self.cfg.min_conf_buttons, timeout_s=0.5):
                        self._status("Sim: server_join not found — retrying…")
                        self._log_warn("server_join_not_found")
                        continue

                # step 6: wait for join outcome - check for failure signals
                join_result = self._wait_for_join_failure_signals()
                if join_result == "success":
                    self._status("Sim: join appears successful — stopping loop.")
                    self._log_info("join_success")
                    break
                elif join_result == "failure":
                    # Handle failure: Fast ESC → back button → restart from join_game
                    self._log_info("handling_join_failure_fast", message="Fast failure recovery with immediate ESC and back")
                    self._press_esc()
                    self._sleep(0.5)  # Updated to 0.5s
                    if not self._click_calibrated("back"):
                        self._press_esc()  # Fallback if back button fails
                        self._sleep(0.2)
                    self._sleep(0.5)  # Brief pause before restarting
                    continue  # Restart from join_game step
                else:
                    # Timeout case: also use fast ESC + back instead of slow _dismiss_failure_and_back
                    self._status("Sim: join timeout — backing out and retrying…")
                    self._log_warn("join_timeout_fast_recovery")
                    self._press_esc()
                    self._sleep(0.5)
                    if not self._click_calibrated("back"):
                        self._press_esc()  # Fallback if back button fails
                        self._sleep(0.2)
                    self._sleep(0.5)  # Brief pause before restarting
                    continue  # Restart from join_game step
        finally:
            self._running.clear()

    # --------------- High-level steps ---------------
    def _ensure_main_menu(self) -> bool:
        to_main = self.templates.path("main_menu")
        if not to_main:
            return False
        coords = self._find(to_main, self.cfg.min_conf_main, timeout_s=0.5)
        return bool(coords)

    def _focus_search_and_type(self, server_code: str) -> bool:
        t0 = time.perf_counter()
        # Try calibrated coordinates first for more accuracy
        if not self._click_calibrated("search_box"):
            # Template fallback
            if not self._click_tpl("search_box", self.cfg.min_conf_field, timeout_s=self.cfg.find_timeout_s):
                self._log_warn("search_click_failed")
                return False
        # Clear field and type guarded
        try:
            self.input.hotkey('ctrl', 'a')
            self._sleep(0.03)
            self.input.press_key('delete')
            self._sleep(0.02)
            self._log_info("field_cleared")
        except Exception:
            self._log_warn("field_clear_error")
        try:
            if hasattr(self.input, 'type_text_guarded_fast'):
                self.input.type_text_guarded_fast(server_code, pre_delay=0.02, first_delay=self.cfg.type_guard_first, post_space_delay=self.cfg.type_guard_space, burst_interval=0.0)
            else:
                self.input.type_text(server_code, interval=0.02, pre_delay=0.05)
            self._sleep(0.015)
            self.input.press_key('enter')
            self._sleep(self.cfg.post_enter_delay)
            dur_ms = (time.perf_counter() - t0) * 1000.0
            self._log_info("typed_and_applied", code=server_code, duration_ms=round(dur_ms, 1))
        except Exception as e:
            self._log_error("type_apply_error", err=str(e))
            return False
        return True

    def _wait_for_join_failure_signals(self) -> str:
        """Wait for join outcome - specifically looking for failure signals.
        Returns: 'success', 'failure', or 'timeout'
        """
        t0 = time.perf_counter()
        failure_templates = ["joining_failed", "connection_failed", "unknown_error", "join_failed"]

        while not self._stop.is_set():
            # Check for successful_join first (highest priority)
            if self.templates.exists("successful_join"):
                path = self.templates.path("successful_join")
                if path and self._find(path, 0.60, timeout_s=0.0):  # Higher confidence for success detection
                    # Verify we're not still on server browser by checking for browser-specific elements
                    browser_elements = ["search_box", "server_join", "join_game"]
                    still_on_browser = False
                    for browser_elem in browser_elements:
                        if self.templates.exists(browser_elem):
                            browser_path = self.templates.path(browser_elem)
                            if browser_path and self._find(browser_path, 0.35, timeout_s=0.0):
                                still_on_browser = True
                                self._log_warn("false_positive_success", detected="successful_join", but_still_see=browser_elem)
                                break

                    if not still_on_browser:
                        self._log_info("join_success_detected", signal="successful_join")
                        return "success"

            # Check for specific failure signals with lower confidence for faster detection
            for failure_name in failure_templates:
                if self.templates.exists(failure_name):
                    path = self.templates.path(failure_name)
                    # Use lower confidence (0.30) for faster failure detection, especially for joining_failed
                    confidence = 0.25 if failure_name == "joining_failed" else 0.30
                    if path and self._find(path, confidence, timeout_s=0.0):
                        self._log_warn("join_failure_signal_fast", signal=failure_name, confidence=confidence)
                        return "failure"

            # Also check for generic OK/error dialogs that might indicate failure
            for dialog_name in ["ok_button", "error_dialog", "server_full"]:
                if self.templates.exists(dialog_name):
                    path = self.templates.path(dialog_name)
                    if path and self._find(path, 0.30, timeout_s=0.0):
                        self._log_warn("join_failure_dialog", signal=dialog_name)
                        return "failure"

            # Check if we've been waiting too long
            elapsed = time.perf_counter() - t0
            if elapsed >= 15.0:  # 15 second timeout
                # Assume success if no failure signals detected
                self._log_info("join_timeout_assume_success")
                return "success"

            self._sleep(0.15)  # Check every 150ms for faster response

        return "timeout"

    def _wait_for_join_outcome(self) -> bool:
        """Return True if join likely succeeded, False if a failure was observed."""
        t0 = time.perf_counter()
        seen_search_again = False
        while not self._stop.is_set():
            # failure templates have priority
            for name in ("server_full", "join_failed", "ok_button"):
                p = self.templates.path(name)
                if not p:
                    continue
                if self._find(p, 0.35, timeout_s=0.0):
                    # click OK if present, treated as failure path
                    if name == 'ok_button':
                        self._click_at_found(p)
                        self._sleep(0.15)
                    self._log_warn("join_failure_signal", signal=name)
                    return False
            # if search box visible again quickly, treat as still on browser
            sb = self.templates.path("search_box")
            if sb and self._find(sb, 0.70, timeout_s=0.0):
                seen_search_again = True
            # success heuristic: after long time without failures and not in browser
            elapsed = time.perf_counter() - t0
            if elapsed >= self.cfg.join_success_assume_s:
                if not seen_search_again:
                    return True
                # Still seeing search after a long time => likely timed out; fail
                self._log_warn("join_timeout")
                return False
            self._sleep(0.15)
        return False

    def _dismiss_failure_and_back(self):
        # Try Esc first (universal)
        self._press_esc()
        self._sleep(0.25)
        # Click known OK/back templates if available
        for name in ("ok_button", "back_button"):
            p = self.templates.path(name)
            if p and self._find(p, 0.35, timeout_s=0.4):
                self._click_at_found(p)
                self._sleep(0.2)
                self._log_info("dismissed_dialog", which=name)
        # Ensure we're back to a state where search is visible or main menu reachable
        sb = self.templates.path("search_box")
        to_main = self.templates.path("to_main")
        if sb and self._find(sb, 0.35, timeout_s=1.0):
            return
        if to_main and self._find(to_main, 0.35, timeout_s=1.0):
            return
        # Otherwise, press Esc one more time to unwind
        self._log_warn("extra_escape")
        self._press_esc()

    # --------------- Vision helpers ---------------
    def _find(self, path: str, conf: float, timeout_s: float) -> Optional[Tuple[int, int]]:
        t0 = time.perf_counter()
        # Save current ROI constraints to restore later
        prev_abs = os.environ.pop('GW_VISION_ROI', None) if 'GW_VISION_ROI' in os.environ else None
        prev_manual = getattr(self.vision, 'search_roi', None)
        try:
            # Set search ROI to Ark window bounds, but respect an existing manual ROI if present
            ark_region = self._get_ark_window_region()
            if prev_manual is None:
                if ark_region:
                    # Use Ark window bounds as the search constraint
                    try:
                        if hasattr(self.vision, 'set_search_roi'):
                            self.vision.set_search_roi(ark_region)
                        self._log_debug("constrained_search", ark_bounds=ark_region)
                    except Exception:
                        pass
                else:
                    # Fallback: clear ROI constraints if Ark window not found (but log this)
                    try:
                        if hasattr(self.vision, 'clear_search_roi'):
                            self.vision.clear_search_roi()
                        self._log_warn("ark_window_not_found", fallback="full_virtual_screen")
                    except Exception:
                        pass
            else:
                try:
                    self._log_debug("respect_manual_roi", roi=prev_manual)
                except Exception:
                    pass

            while not self._stop.is_set():
                try:
                    coords = self.vision.find_template(path, confidence=conf)
                except Exception:
                    coords = None
                if coords:
                    # Ensure found coordinates are within Ark window bounds
                    if ark_region and coords:
                        coords = self._clamp_to_ark_window(coords, ark_region)
                    return coords
                if timeout_s and (time.perf_counter() - t0) >= timeout_s:
                    return None
                self._sleep(0.06)
        finally:
            # Restore prior ROI constraints
            try:
                if prev_manual is not None and hasattr(self.vision, 'set_search_roi'):
                    self.vision.set_search_roi(prev_manual)
            except Exception:
                pass
            if prev_abs is not None:
                try:
                    os.environ['GW_VISION_ROI'] = prev_abs
                except Exception:
                    pass
        return None

    def _click_at_found(self, path: str, conf: float = 0.70, timeout_s: float = 0.8, label: Optional[str] = None) -> bool:
        t0 = time.perf_counter()
        coords = self._find(path, conf, timeout_s)
        if not coords:
            self._log_warn("click_not_found", target=(label or Path(path).stem))
            return False
        try:
            # Clamp to virtual screen bounds to avoid off-screen clicks on multi-monitor setups
            cx, cy, clamped = self._clamp_coords(int(coords[0]), int(coords[1]))
            if clamped:
                self._log_warn("clamped_coords", target=(label or Path(path).stem), from_x=int(coords[0]), from_y=int(coords[1]), to_x=cx, to_y=cy)
            self.input.move_mouse(cx, cy)
            self._sleep(0.02)
            self.input.click_button('left', presses=1, interval=0.0)
            self._sleep(self.cfg.click_settle)
            dur_ms = (time.perf_counter() - t0) * 1000.0
            self._log_info("clicked", target=(label or Path(path).stem), x=int(cx), y=int(cy), duration_ms=round(dur_ms, 1))
            return True
        except Exception as e:
            self._log_error("click_error", target=(label or Path(path).stem), err=str(e))
            return False

    def _click_tpl(self, name: str, conf: float, timeout_s: Optional[float] = None) -> bool:
        path = self.templates.path(name)
        if not path:
            return False
        return self._click_at_found(path, conf=conf, timeout_s=timeout_s if timeout_s is not None else self.cfg.find_timeout_s, label=name)

    def _wait_for_tpl(self, name: str, conf: float, timeout_s: float) -> bool:
        path = self.templates.path(name)
        if not path:
            return False
        t0 = time.perf_counter()
        ok = bool(self._find(path, conf, timeout_s))
        duration = round((time.perf_counter() - t0) * 1000.0, 1)
        self._log_info("wait_for_tpl", tpl=name, found=ok, duration_ms=duration, required_conf=conf)
        return ok

    def _click_tpl_if_present(self, name: str, conf: float) -> bool:
        if not self.templates.exists(name):
            return False
        return self._click_tpl(name, conf, timeout_s=0.5)

    def _detect_header_bottom(self, window_region: Dict[str, int], roi_rect: Tuple[int, int, int, int]) -> Optional[int]:
        """Detect the Y coordinate just below the header by locating the first strong horizontal divider.

        Returns the absolute Y (screen space) of the divider + padding, or None if not found.
        """
        try:
            # Extract only what's needed
            H = int(window_region["height"]) if isinstance(window_region, dict) else int(window_region[3] - window_region[1])

            roi_left, roi_top, roi_right, roi_bottom = map(int, roi_rect)
            # Focus a band near the top of the server list area
            band_top = roi_top
            band_bottom = min(roi_bottom, roi_top + max(20, int(0.12 * H)))  # ~12% of window height
            band_left = roi_left
            band_right = roi_right
            if band_bottom <= band_top or band_right <= band_left:
                return None

            # Grab the band and run edge + Hough to find long horizontal lines
            with mss.mss() as sct:
                frame = np.array(sct.grab({
                    "left": band_left,
                    "top": band_top,
                    "width": max(1, band_right - band_left),
                    "height": max(1, band_bottom - band_top),
                }))
            gray = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
            # Light blur, then Canny
            try:
                gray = cv2.GaussianBlur(gray, (3, 3), 0)
            except Exception:
                pass
            edges = cv2.Canny(gray, 40, 120)
            # Probabilistic Hough to get segments
            h, w = edges.shape[:2]
            min_len = max(60, int(0.25 * w))  # long line
            lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80, minLineLength=min_len, maxLineGap=6)
            if lines is None:
                return None
            # Find the first strong horizontal near the top
            candidate_y = None
            for seg in lines[:, 0, :]:
                x1, y1, x2, y2 = map(int, seg)
                # Horizontal tolerance
                if abs(y2 - y1) <= 2 and abs(x2 - x1) >= min_len:
                    y_abs = band_top + min(y1, y2)
                    if candidate_y is None or y_abs < candidate_y:
                        candidate_y = y_abs
            if candidate_y is None:
                return None
            # Padding below the divider to avoid clicking into the header row
            pad = max(6, int(0.008 * H))  # ~0.8% of height
            header_bottom = int(candidate_y + pad)
            self._log_info("header_divider_detected", divider_y=int(candidate_y), header_bottom=int(header_bottom), band_top=int(band_top))
            return header_bottom
        except Exception as e:
            try:
                self._log_warn("header_divider_detection_failed", error=str(e))
            except Exception:
                pass
            return None

    def _check_server_template_enhanced(self, template_name: str, confidence_levels: Tuple[float, ...], frame_bounds: Tuple[int, int, int, int]) -> Optional[Tuple[int, int]]:
        """Try enhanced detection for a single server template name with ROI recheck and fallback.

        Returns coordinates (x, y) if found, None otherwise.
        """
        try:
            if not self.templates.exists(template_name):
                return None
            self._log_info(f"checking_{template_name}_template_enhanced")
            tpl_path = self.templates.path(template_name)
            if not tpl_path:
                self._log_info(f"{template_name}_path_not_resolved", message=f"Could not resolve {template_name} template path")
                return None
            self._log_info(f"{template_name}_path_resolved", path=str(tpl_path))

            left, top, right, bottom = frame_bounds
            for confidence in confidence_levels:
                try:
                    result = self.vision.find_server_template_enhanced(str(tpl_path), confidence=confidence)
                    if result:
                        # Skip verify ROI step - the enhanced detection already found it with good confidence
                        # The verify step was causing false negatives due to overly restrictive ROI
                        self._log_info(f"{template_name}_found_enhanced",
                            message=f"Found {template_name} template with enhanced detection - servers available",
                            confidence_used=confidence,
                            match_details=result,
                            verified=False,  # No secondary verification needed
                            method="enhanced"
                        )
                        return result  # Return the actual coordinates
                    else:
                        self._log_info(f"{template_name}_attempt_enhanced", confidence=confidence, found=False)
                except Exception as e:
                    self._log_info(f"{template_name}_enhanced_error", error=str(e), confidence=confidence)
                    # Fallback to standard detection for this confidence level
                    try:
                        result = self.vision.find_template(str(tpl_path), confidence=confidence)
                        if result:
                            self._log_info(f"{template_name}_found_fallback",
                                message=f"Found {template_name} template with fallback detection",
                                confidence_used=confidence,
                                match_details=result,
                                method="fallback"
                            )
                            return result  # Return the actual coordinates
                    except Exception as fallback_e:
                        self._log_info(f"{template_name}_fallback_error", error=str(fallback_e))

            self._log_info(f"{template_name}_not_found", message=f"{template_name} template not found at any confidence level")
            return None
        except Exception as e:
            self._log_info("template_check_error", template=template_name, error=str(e))
            return None

    def _click_at_detected_coords(self, coords: Tuple[int, int], template_name: str) -> bool:
        """Click at detected coordinates with proper clamping and logging."""
        try:
            x, y = coords

            # If this is a server-row click, bias the click slightly downward to avoid header/label hits
            y_offset = 0
            try:
                if str(template_name).startswith("click_server") or template_name in {"click_server", "click_server2", "click_server3", "click_server4", "click_server5"}:
                    rect = self._get_ark_rect_by_proc() or self._get_virtual_screen_rect()
                    if rect:
                        _, top, _, bottom = rect
                        H = max(1, bottom - top)
                        # About 1.2% of window height; ~26px on 2160p
                        y_offset = int(0.012 * H)
                    else:
                        # Conservative fallback offset
                        y_offset = 22
            except Exception:
                pass

            adj_x = int(x)
            adj_y = int(y) + int(y_offset)

            # Clamp to virtual screen bounds to avoid off-screen clicks
            cx, cy, clamped = self._clamp_coords(adj_x, adj_y)
            if clamped:
                self._log_warn("detected_coords_clamped", template=template_name, from_x=int(x), from_y=int(y), offset_y=int(y_offset), to_x=cx, to_y=cy)

            if y_offset:
                self._log_info("detected_click_adjustment", template=template_name, original_x=int(x), original_y=int(y), offset_y=int(y_offset), adjusted_x=int(cx), adjusted_y=int(cy))

            self._log_info("clicking_detected_coords", template=template_name, x=cx, y=cy)
            self.input.move_mouse(cx, cy)
            self._sleep(0.02)
            self.input.click_button('left', presses=1, interval=0.0)
            self._sleep(self.cfg.click_settle)
            self._log_info("server_clicked", method="detected_coords", template=template_name, x=cx, y=cy)
            return True
        except Exception as e:
            self._log_error("detected_coords_click_error", template=template_name, error=str(e))
            return False

    # --------------- Calibrated fallback ---------------
    def _parse_norm(self, key: str) -> Optional[Tuple[float, float]]:
        try:
            raw = self.config_manager.get(f"sim_{key}_norm")
            if not raw:
                # Hardcoded fallback coordinates for calibrated buttons
                if key == "join_game":
                    return (0.247396, 0.531481)  # Calibrated join_game coordinates (universal fallback)
                elif key == "search_box":
                    return (0.832031, 0.179630)  # Search field coordinates - updated
                elif key == "server_join":
                    return (0.892448, 0.877315)  # Server join button coordinates - updated
                elif key == "click_server":
                    return (0.531510, 0.301389)  # Click on server in search results
                elif key == "click_server2":
                    return (0.531510, 0.301389)  # Same as click_server; one server expected
                elif key in ("click_server3", "click_server4", "click_server5"):
                    return (0.531510, 0.301389)  # Same as click_server; additional variants
                elif key == "press_start":
                    return (0.500781, 0.804167)  # Press start button coordinates - updated
                elif key == "back":
                    return (0.087760, 0.812963)  # Back button coordinates
                return None
            parts = [p.strip() for p in str(raw).split(',')]
            if len(parts) != 2:
                return None
            nx = float(parts[0])
            ny = float(parts[1])
            if not (0.0 <= nx <= 1.0 and 0.0 <= ny <= 1.0):
                return None
            return nx, ny
        except Exception:
            # Fallback coordinates if config parsing fails
            if key == "join_game":
                return (0.247396, 0.531481)  # Calibrated join_game coordinates (universal fallback)
            elif key == "search_box":
                return (0.832031, 0.179630)  # Search field coordinates - updated
            elif key == "server_join":
                return (0.892448, 0.877315)  # Server join button coordinates - updated
            elif key == "click_server":
                return (0.531510, 0.301389)  # Click on server in search results
            elif key == "click_server2":
                return (0.531510, 0.301389)  # Same as click_server; one server expected
            elif key in ("click_server3", "click_server4", "click_server5"):
                return (0.531510, 0.301389)  # Same as click_server; additional variants
            elif key == "press_start":
                return (0.500781, 0.804167)  # Press start button coordinates - updated
            elif key == "back":
                return (0.087760, 0.812963)  # Back button coordinates
            return None

    def _get_virtual_screen_rect(self) -> Optional[Tuple[int, int, int, int]]:
        try:
            import mss
            with mss.mss() as sct:
                vb = sct.monitors[0]
                L = int(vb['left'])
                T = int(vb['top'])
                R = L + int(vb['width'])
                B = T + int(vb['height'])
                return L, T, R, B
        except Exception:
            return None

    def _get_ark_rect_by_proc(self) -> Optional[Tuple[int, int, int, int]]:
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            class RECT(ctypes.Structure):
                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
            target_exe = "arkascended.exe"
            found = ctypes.wintypes.HWND()
            @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
            def _enum_proc(hwnd, lparam):
                try:
                    if not user32.IsWindowVisible(hwnd):
                        return True
                    pid = ctypes.wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    hproc = kernel32.OpenProcess(0x1000, False, pid.value)
                    if not hproc:
                        return True
                    try:
                        buf_len = ctypes.wintypes.DWORD(260)
                        while True:
                            buf = ctypes.create_unicode_buffer(buf_len.value)
                            ok = kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(buf_len))
                            if ok:
                                exe = os.path.basename(buf.value or "").lower()
                                if exe == target_exe:
                                    found.value = hwnd
                                    return False
                                break
                            needed = buf_len.value
                            if needed <= len(buf):
                                break
                            buf_len = ctypes.wintypes.DWORD(needed)
                    finally:
                        kernel32.CloseHandle(hproc)
                except Exception:
                    return True
                return True
            user32.EnumWindows(_enum_proc, 0)
            if not found.value:
                return None
            rc = RECT()
            if not user32.GetWindowRect(found, ctypes.byref(rc)):
                return None
            return int(rc.left), int(rc.top), int(rc.right), int(rc.bottom)
        except Exception:
            return None

    def _click_calibrated(self, name: str) -> bool:
        norm = self._parse_norm(name)
        if not norm:
            self._log_warn("calibrated_no_norm", target=name)
            return False
        rect = self._get_ark_rect_by_proc() or self._get_virtual_screen_rect()
        if not rect:
            self._log_warn("calibrated_no_rect", target=name)
            return False
        L, T, R, B = rect
        W = max(1, R - L)
        H = max(1, B - T)
        nx, ny = norm
        x = L + int(nx * W)
        y = T + int(ny * H)

        # Debug logging
        self._log_info(
            "calibrated_debug",
            target=name,
            norm_x=nx,
            norm_y=ny,
            window_rect=f"({L},{T},{R},{B})",
            window_size=f"{W}x{H}",
            calculated_x=x,
            calculated_y=y,
        )

        cx, cy, clamped = self._clamp_coords(x, y)
        if clamped:
            self._log_warn("calibrated_clamped", target=name, from_x=x, from_y=y, to_x=cx, to_y=cy)
        try:
            self._log_info("calibrated_mouse_move", target=name, moving_to_x=int(cx), moving_to_y=int(cy))
            self.input.move_mouse(cx, cy)
            self._sleep(0.02)  # Standard delay for all clicks
            self._log_info("calibrated_mouse_click", target=name, clicking_at_x=int(cx), clicking_at_y=int(cy))
            self.input.click_button('left', presses=1, interval=0.0)
            self._sleep(self.cfg.click_settle)
            self._log_info("sim_cal_fallback_click", target=name, x=int(cx), y=int(cy))
            return True
        except Exception as e:
            self._log_warn("calibrated_click_exception", target=name, error=str(e))
            return False

    # --------------- Utilities ---------------
    def _press_esc(self, times: int = 1):
        try:
            self.input.press_key('esc', presses=max(1, int(times)), interval=0.10)
        except Exception:
            pass

    def _virtual_bounds(self) -> Optional[Tuple[int, int, int, int]]:
        try:
            import mss
            with mss.mss() as sct:
                mon = sct.monitors[0]
                return int(mon['left']), int(mon['top']), int(mon['left'] + mon['width'] - 1), int(mon['top'] + mon['height'] - 1)
        except Exception:
            return None

    def _clamp_coords(self, x: int, y: int) -> Tuple[int, int, bool]:
        bounds = self._virtual_bounds()
        if not bounds:
            return x, y, False
        L, t, r, b = bounds
        cx = max(L, min(r, int(x)))
        cy = max(t, min(b, int(y)))
        return cx, cy, (cx != x or cy != y)

    def _get_ark_window_region(self) -> Optional[Dict[str, int]]:
        """Get the Ark Ascended window bounds using process detection.

        This searches for ANY Ark window, not just the foreground one.
        Handles DPI scaling to get true coordinates.
        Returns a region dict with 'left', 'top', 'width', 'height' keys,
        or None if Ark window cannot be found or accessed.
        """
        try:
            # Try the vision controller's method first (foreground window only)
            from ..controllers.vision import _ark_window_region
            foreground_region = _ark_window_region()
            if foreground_region:
                # Check if this looks like it might be DPI scaled
                width, height = foreground_region['width'], foreground_region['height']
                if width == 1920 and height == 1080:
                    # Try to detect if this should be 4K
                    scaled_region = self._handle_dpi_scaling(foreground_region)
                    if scaled_region:
                        if hasattr(self, '_log_debug'):
                            self._log_debug("ark_window_found", source="foreground_dpi_corrected", region=scaled_region)
                        return scaled_region

                if hasattr(self, '_log_debug'):
                    self._log_debug("ark_window_found", source="foreground", region=foreground_region)
                return foreground_region

        except ImportError:
            pass
        except Exception as e:
            if hasattr(self, '_log_debug'):
                self._log_debug("foreground_ark_detection_failed", error=str(e))

        # Fallback: Search for ANY Ark window (not just foreground)
        try:
            if not ctypes or not hasattr(ctypes, 'windll'):
                return None

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            # Structure to hold the found window handle
            found_hwnd = ctypes.c_void_p(0)

            def enum_windows_proc(hwnd, lParam):
                try:
                    # Get process ID for this window
                    pid = ctypes.c_ulong()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

                    # Open process to get executable name
                    hproc = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
                    if not hproc:
                        return True  # Continue enumeration

                    try:
                        buffer = ctypes.create_unicode_buffer(260)
                        size = ctypes.c_ulong(260)
                        if kernel32.QueryFullProcessImageNameW(hproc, 0, buffer, ctypes.byref(size)):
                            exe_path = buffer.value.lower()
                            if exe_path.endswith('arkascended.exe'):
                                # Check if this is a visible window
                                if user32.IsWindowVisible(hwnd):
                                    found_hwnd.value = hwnd
                                    return False  # Stop enumeration
                    finally:
                        kernel32.CloseHandle(hproc)

                except Exception:
                    pass
                return True  # Continue enumeration

            # Define the callback type
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            enum_proc = WNDENUMPROC(enum_windows_proc)

            # Enumerate all windows
            user32.EnumWindows(enum_proc, 0)

            if not found_hwnd.value:
                if hasattr(self, '_log_debug'):
                    self._log_debug("ark_window_not_found", searched="all_windows")
                return None

            # Get window rectangle
            class RECT(ctypes.Structure):
                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                           ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

            rect = RECT()
            if not user32.GetWindowRect(found_hwnd.value, ctypes.byref(rect)):
                return None

            left, top = int(rect.left), int(rect.top)
            width, height = int(rect.right - rect.left), int(rect.bottom - rect.top)

            if width <= 0 or height <= 0:
                return None

            region = {"left": left, "top": top, "width": width, "height": height}

            # Handle potential DPI scaling
            if width == 1920 and height == 1080:
                scaled_region = self._handle_dpi_scaling(region, found_hwnd.value)
                if scaled_region:
                    if hasattr(self, '_log_debug'):
                        self._log_debug("ark_window_found", source="enumeration_dpi_corrected", region=scaled_region)
                    return scaled_region

            if hasattr(self, '_log_debug'):
                self._log_debug("ark_window_found", source="enumeration", region=region)
            return region

        except Exception as e:
            if hasattr(self, '_log_debug'):
                self._log_debug("ark_window_detection_failed", error=str(e))
            return None

    def _handle_dpi_scaling(self, region: Dict[str, int], hwnd: Optional[int] = None) -> Optional[Dict[str, int]]:
        """Handle DPI scaling by detecting if window is actually larger than reported.

        Args:
            region: Original region dict
            hwnd: Window handle (optional)

        Returns:
            Corrected region dict or None if no correction needed
        """
        try:
            width, height = region['width'], region['height']

            # If we get 1920x1080, check if it should be 4K
            if width == 1920 and height == 1080:
                # Try to detect DPI scaling factor
                try:
                    user32 = ctypes.windll.user32

                    # Method 1: Try GetDpiForWindow if hwnd provided
                    if hwnd:
                        try:
                            dpi = user32.GetDpiForWindow(hwnd)
                            scale_factor = dpi / 96.0
                            if scale_factor >= 1.8:  # Close to 2x scaling
                                # Scale up to 4K
                                scaled_region = {
                                    "left": region["left"],
                                    "top": region["top"],
                                    "width": int(width * 2),
                                    "height": int(height * 2)
                                }
                                if hasattr(self, '_log_debug'):
                                    self._log_debug("dpi_scaling_detected",
                                                   original=region,
                                                   scaled=scaled_region,
                                                   dpi=dpi,
                                                   scale=scale_factor)
                                return scaled_region
                        except Exception:
                            pass

                    # Method 2: Check monitor resolution vs window size
                    # If we're on a 4K monitor but window reports 1080p, likely scaled
                    monitor_info = self._get_monitor_info_for_region(region)
                    if monitor_info:
                        mon_width = monitor_info.get('width', 0)
                        if mon_width >= 3840:  # 4K monitor
                            # Window reports 1080p on 4K monitor - likely scaled
                            scaled_region = {
                                "left": region["left"],
                                "top": region["top"],
                                "width": 3840,
                                "height": 2160
                            }
                            if hasattr(self, '_log_debug'):
                                self._log_debug("dpi_scaling_inferred",
                                               original=region,
                                               scaled=scaled_region,
                                               monitor=monitor_info)
                            return scaled_region

                except Exception as e:
                    if hasattr(self, '_log_debug'):
                        self._log_debug("dpi_detection_failed", error=str(e))

            return None

        except Exception as e:
            if hasattr(self, '_log_debug'):
                self._log_debug("dpi_scaling_failed", error=str(e))
            return None

    def _get_monitor_info_for_region(self, region: Dict[str, int]) -> Optional[Dict[str, int]]:
        """Get monitor information for a given region"""
        try:
            # Use the same monitor detection as the startup logs
            import mss
            with mss.mss() as sct:
                # Check which monitor this region is on
                center_x = region["left"] + region["width"] // 2
                for i, monitor in enumerate(sct.monitors[1:], 1):  # Skip virtual monitor
                    mon_left = monitor["left"]
                    mon_right = mon_left + monitor["width"]
                    if mon_left <= center_x <= mon_right:
                        return monitor
            return None
        except Exception:
            return None

    def _clamp_to_ark_window(self, coords: Tuple[int, int], ark_region: Dict[str, int]) -> Tuple[int, int]:
        """Ensure coordinates are within Ark window bounds.

        Args:
            coords: (x, y) coordinates to clamp
            ark_region: Ark window region with 'left', 'top', 'width', 'height'

        Returns:
            Clamped (x, y) coordinates within the Ark window
        """
        try:
            x, y = coords
            left = ark_region["left"]
            top = ark_region["top"]
            right = left + ark_region["width"]
            bottom = top + ark_region["height"]

            # Clamp coordinates to window bounds
            clamped_x = max(left, min(x, right - 1))
            clamped_y = max(top, min(y, bottom - 1))

            if (clamped_x, clamped_y) != (x, y):
                if hasattr(self, '_log_debug'):
                    self._log_debug("coords_clamped",
                                   original=(x, y),
                                   clamped=(clamped_x, clamped_y),
                                   ark_bounds=ark_region)

            return clamped_x, clamped_y

        except Exception as e:
            if hasattr(self, '_log_debug'):
                self._log_debug("clamp_coords_failed", error=str(e))
            return coords  # Return original coords if clamping fails

    def _sleep(self, s: float):
        try:
            if s > 0:
                time.sleep(s)
        except Exception:
            pass

    def _status(self, text: str):
        self.logger.info(text)
        if self.overlay and hasattr(self.overlay, 'set_status'):
            try:
                self.overlay.set_status(text)
            except Exception:
                pass

    # --------------- Logging helpers ---------------
    def _log(self, level: int, event: str, **fields):
        try:
            rid = getattr(self, "_run_id", None)
            base = f"auto-sim event={event}"
            if rid:
                base += f" id={rid}"
            details = " ".join(f"{k}={fields[k]}" for k in fields)
            self.logger.log(level, f"{base} {details}" if details else base)
        except Exception:
            pass

    def _log_info(self, event: str, **fields):
        self._log(logging.INFO, event, **fields)

    def _log_warn(self, event: str, **fields):
        self._log(logging.WARNING, event, **fields)

    def _log_error(self, event: str, **fields):
        self._log(logging.ERROR, event, **fields)

# --------------------------------------------------------------------------------------
# Backwards-compatibility alias
# Some tests and older code import AutoSimFeature from this module.
# Keep an alias so the public API remains stable.
AutoSimFeature = AutoSimRunner
