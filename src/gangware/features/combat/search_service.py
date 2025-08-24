"""Search and type automation service.

This module provides comprehensive search and type functionality for item matching
and inventory interaction within the ARK game interface.
"""

import logging
import os
import time
from pathlib import Path
from typing import Callable, Optional, Dict, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..combat.armor_matcher import ArmorMatcher
else:
    try:
        from ..combat.armor_matcher import ArmorMatcher
    except ImportError:
        ArmorMatcher = None  # type: ignore


class SearchService:
    """Service for automated search and type functionality."""

    def __init__(self, config_manager, overlay=None):
        """Initialize search service.

        Args:
            config_manager: Configuration manager instance
            overlay: Optional overlay for status updates
        """
        self.config_manager = config_manager
        self.overlay = overlay
        self._armor_matcher = None
        self._cached_search_coords = None  # Cache search bar coordinates for reuse

    def create_search_and_type_task(
        self, text: str, close_inventory: bool = True, open_inventory: bool = True
    ) -> Callable[[object, object], None]:
        """Create task for searching and typing text in inventory.

        This method creates a comprehensive search and type task that:
        1. Opens inventory using configured hotkey (if requested)
        2. Locates the search bar template
        3. Clicks and clears the search field
        4. Types the specified text
        5. Performs armor matching and equipment

        Args:
            text: Text to search for and type
            close_inventory: Whether to close inventory after task completion
            open_inventory: Whether to open inventory at start (set False for subsequent items)

        Returns:
            Callable task function for execution
        """
        def _job(vision_controller, input_controller):
            import time as _t
            import random as _rand
            corr = f"f2-{int(_t.time())}-{_rand.randint(1000,9999)}"
            logger = logging.getLogger(__name__)

            try:
                # 1) Open inventory using configured token (keyboard or mouse) - only if requested
                if open_inventory:
                    inv_token = self._get_token('inventory_key', 'key_i')
                    t_phase = _t.perf_counter()

                    try:
                        if self.overlay:
                            self.overlay.set_status_safe(f"Opening inventory with {self._token_display(inv_token)}...")
                        # Use press_token to support mouse buttons like XBUTTON2
                        if hasattr(input_controller, 'press_token'):
                            input_controller.press_token(inv_token)
                        else:
                            # Fallback: press key token directly if available
                            name = inv_token.split('_', 1)[1] if '_' in inv_token else inv_token
                            if inv_token.startswith('key_'):
                                input_controller.press_key(name)
                    except Exception:
                        pass

                    # Give the game UI time to open and stabilize
                    try:
                        time.sleep(0.5)  # Increased from 0.25 to 0.5 seconds
                    except Exception:
                        pass

                    try:
                        logger.info("macro=F2 phase=open_inventory corr=%s duration_ms=%.1f",
                                  corr, (_t.perf_counter() - t_phase) * 1000.0)
                    except Exception:
                        pass
                else:
                    # Skip inventory opening for subsequent items
                    logger.info("macro=F2 phase=skip_open_inventory corr=%s (inventory already open)", corr)

                # 2) Locate the saved template path
                tmpl = self.config_manager.get('search_bar_template')
                if not tmpl:
                    self._log('Search bar template not set. Use F7 with Inv Search to capture coordinates.')
                    return

                # F6 ROI constraints are bypassed for search-bar detection to ensure visibility.
                # This ROI will be applied later as an inventory sub-region for item matching.
                _abs_roi_env = os.environ.get('GW_VISION_ROI', '').strip()

                # Apply deferred ROI from config if not already in environment
                if not _abs_roi_env:
                    try:
                        rel_roi = self.config_manager.get('vision_roi', '').strip()
                        if rel_roi and ',' in rel_roi:
                            # Import the conversion function
                            from ...core.win32 import utils as w32
                            monitor_bounds = w32.current_monitor_bounds()
                            abs_roi = w32.relative_to_absolute_roi(rel_roi, monitor_bounds)
                            if abs_roi:
                                os.environ['GW_VISION_ROI'] = abs_roi
                                _abs_roi_env = abs_roi
                                logger.info("Applied deferred ROI from config: %s -> %s", rel_roi, abs_roi)
                    except Exception as e:
                        logger.warning("Failed to apply deferred ROI: %s", e)

                # Check if we should use cached search bar coordinates (for subsequent items)
                coords = None
                tmpl = None  # Initialize template path
                if not open_inventory and self._cached_search_coords:
                    # Reuse cached coordinates for subsequent items
                    coords = self._cached_search_coords
                    logger.info("macro=F2 phase=reuse_search_coords corr=%s coords=%s", corr, str(coords))
                else:
                    # Check for saved search bar coordinates first (from F7 Inv Search capture)
                    saved_coords_str = self.config_manager.get('search_bar_coords')
                    if saved_coords_str and ',' in saved_coords_str:
                        try:
                            x, y = map(int, saved_coords_str.split(','))
                            coords = (x, y)
                            self._cached_search_coords = coords
                            logger.info("macro=F2 phase=use_saved_coords corr=%s coords=(%d,%d)", corr, x, y)
                            if self.overlay:
                                self.overlay.set_status_safe(f"Using saved search bar coordinates: ({x}, {y})")
                        except Exception as e:
                            logger.warning("Failed to parse saved search bar coordinates '%s': %s", saved_coords_str, e)
                            coords = None

                    # If no saved coordinates, fall back to template search
                    if coords is None:
                        # 2) Locate the saved template path
                        tmpl = self.config_manager.get('search_bar_template')
                        if not tmpl:
                            self._log('Search bar template not set. Use F7 with Inv Search to capture coordinates.')
                            return

                        # Find search bar using template matching
                        t_phase = _t.perf_counter()
                        for attempt in range(5):
                            # Gradually relax confidence from 0.70 down to 0.50
                            conf = max(0.50, 0.70 - 0.03 * attempt)
                            try:
                                if self.overlay:
                                    self.overlay.set_status_safe(
                                        f"Finding search bar… attempt {attempt+1}/8 (conf>={conf:.2f})"
                                    )
                            except Exception:
                                pass

                            try:
                                coords = self._find_search_bar(vision_controller, tmpl, conf, _abs_roi_env)
                            except Exception as e:
                                logger.exception("macro=F2 phase=find_bar corr=%s attempt=%d error=%s",
                                               corr, attempt + 1, str(e))
                                coords = None

                            if coords:
                                logger.info(
                                    "macro=F2 phase=find_bar corr=%s attempt=%d result=match coords=%s conf>=%.2f",
                                    corr, attempt + 1, str(coords), conf
                                )
                                self._log_monitor_detection(coords)
                                # Cache coordinates for subsequent items
                                self._cached_search_coords = coords
                                break

                            # On the 5th attempt (last), try pressing inventory again as final attempt
                            if attempt == 4:
                                try:
                                    if self.overlay:
                                        self.overlay.set_status_safe("Retrying inventory open (final attempt)...")
                                    if hasattr(input_controller, 'press_token'):
                                        input_controller.press_token(inv_token)
                                    else:
                                        name = inv_token.split('_', 1)[1] if '_' in inv_token else inv_token
                                        if inv_token.startswith('key_'):
                                            input_controller.press_key(name)
                                    time.sleep(0.5)  # Give more time after reopening
                                except Exception:
                                    pass

                            try:
                                time.sleep(0.04)
                            except Exception:
                                pass

                        try:
                            logger.info("macro=F2 phase=find_bar corr=%s duration_ms=%.1f found=%s",
                                      corr, (_t.perf_counter() - t_phase) * 1000.0, bool(coords))
                        except Exception:
                            pass

                if not coords:
                    self._handle_search_miss(vision_controller)
                    return

                # 3) Click, clear field safely, type text (avoid Ctrl+A to prevent stray 'A')
                try:
                    if self.overlay:
                        self.overlay.set_status_safe("Clicking search box and typing...")
                    self._perform_search_input(input_controller, coords, text, corr, logger, _t)

                    # 4) ROI calibration and item matching
                    self._perform_item_matching(vision_controller, input_controller, text,
                                              _abs_roi_env, tmpl or "", corr, logger, _t)

                except Exception:
                    pass

            except Exception:
                pass
            finally:
                # Close inventory at the end of the search task (only if requested)
                if close_inventory:
                    try:
                        # Prefer a dedicated close key (defaults to ESC) for reliable closing
                        close_token = self._get_token('inventory_close_key', 'key_esc')
                        if hasattr(input_controller, 'press_token'):
                            input_controller.press_token(close_token)
                        else:
                            name = close_token.split('_', 1)[1] if '_' in close_token else close_token
                            if close_token.startswith('key_'):
                                input_controller.press_key(name)
                        logger.info("macro=F2 phase=close_inventory corr=%s token=%s", corr, close_token)
                        # Brief settle to allow UI to close
                        try:
                            _t.sleep(0.25)
                        except Exception:
                            pass
                        # Clear cached search coordinates when inventory is closed
                        self._cached_search_coords = None
                        # Reset overlay status to operational when armor swapping sequence completes
                        if self.overlay:
                            self.overlay.set_status_safe("STATUS: OPERATIONAL")
                    except Exception:
                        pass

        try:
            setattr(_job, '_gw_task_id', 'search_and_type')
        except Exception:
            pass

        return _job

    def _get_token(self, key: str, default: str) -> str:
        """Get configuration token with fallback."""
        result = self.config_manager.get(key, default)
        return str(result)

    def _token_display(self, token: str) -> str:
        """Get display format for token."""
        if token.startswith('key_'):
            return token[4:].upper()
        elif token.startswith('mouse_'):
            return token[6:].upper()
        return token.upper()

    def _log(self, message: str) -> None:
        """Log message with overlay update."""
        if self.overlay:
            self.overlay.set_status_safe(message)

    def _find_search_bar(self, vision_controller, tmpl: str, conf: float,
                        _abs_roi_env: str) -> Optional[Tuple[int, int]]:
        """Find search bar template with ROI constraints."""
        # Disable ROI constraints for full-window template search
        _prev_abs = None
        if _abs_roi_env:
            try:
                _prev_abs = os.environ.pop('GW_VISION_ROI', None)
            except Exception:
                _prev_abs = None

        # Constrain search to a band above the inventory area
        band = self._calculate_search_band(_abs_roi_env, vision_controller)

        prev_manual_roi = getattr(vision_controller, 'search_roi', None)
        coords = None

        try:
            if band is not None and hasattr(vision_controller, 'set_search_roi'):
                vision_controller.set_search_roi(band)

            # Force fast-only search to reduce latency for search-bar detection
            _prev_fast = os.environ.get('GW_VISION_FAST_ONLY')
            try:
                os.environ['GW_VISION_FAST_ONLY'] = '1'
                result = vision_controller.find_template(str(tmpl), confidence=conf)
                coords = tuple(result) if result else None
            finally:
                try:
                    if _prev_fast is None:
                        os.environ.pop('GW_VISION_FAST_ONLY', None)
                    else:
                        os.environ['GW_VISION_FAST_ONLY'] = _prev_fast
                except Exception:
                    pass

        finally:
            try:
                if hasattr(vision_controller, 'clear_search_roi'):
                    vision_controller.clear_search_roi()
                if prev_manual_roi is not None and hasattr(vision_controller, 'set_search_roi'):
                    vision_controller.set_search_roi(prev_manual_roi)
            except Exception:
                pass
            if _prev_abs is not None:
                os.environ['GW_VISION_ROI'] = _prev_abs

        return coords

    def _calculate_search_band(self, _abs_roi_env: str, vision_controller) -> Optional[Dict[str, int]]:
        """Calculate search band area above inventory."""
        band = None
        try:
            inv_hint = None
            if _abs_roi_env:
                parts = [int(p.strip()) for p in _abs_roi_env.split(',')]
                if len(parts) == 4:
                    inv_hint = {'left': parts[0], 'top': parts[1],
                              'width': parts[2], 'height': parts[3]}

            if inv_hint is None:
                inv0 = getattr(vision_controller, 'inventory_roi', None)
                if isinstance(inv0, dict) and inv0.get('width', 0) > 0 and inv0.get('height', 0) > 0:
                    inv_hint = inv0

            if inv_hint is not None:
                L = int(inv_hint.get('left', 0))
                T = int(inv_hint.get('top', 0))
                W = int(inv_hint.get('width', 0))
                H = int(inv_hint.get('height', 0))
                band_h = max(100, min(260, int(H * 0.40)))
                band_top = max(0, T - band_h - int(H * 0.05))
                band_left = max(0, L - int(W * 0.05))
                band_w = int(W + int(W * 0.10))

                # Clamp to virtual screen
                try:
                    import mss
                    with mss.mss() as sct:
                        vb = sct.monitors[0]
                        band_left = max(vb['left'], min(band_left, vb['left'] + vb['width'] - band_w))
                        band_top = max(vb['top'], min(band_top, vb['top'] + vb['height'] - band_h))
                except Exception:
                    pass

                band = {'left': int(band_left), 'top': int(band_top),
                       'width': int(band_w), 'height': int(band_h)}
        except Exception:
            band = None

        return band

    def _log_monitor_detection(self, coords: tuple) -> None:
        """Log which monitor the detection occurred on."""
        try:
            import mss
            with mss.mss() as sct:
                monitors = sct.monitors
                x, y = coords
                for i, mon in enumerate(monitors):
                    if i == 0:  # Skip virtual screen
                        continue
                    if (mon['left'] <= x < mon['left'] + mon['width'] and
                        mon['top'] <= y < mon['top'] + mon['height']):
                        logging.getLogger(__name__).info(
                            "vision: search bar found on monitor %d: %s", i, str(mon))
                        break
        except Exception:
            pass

    def _handle_search_miss(self, vision_controller) -> None:
        """Handle case where search bar template is not found."""
        # Report best observed score to help tune capture
        dbg = None
        try:
            if hasattr(vision_controller, 'get_last_debug'):
                dbg = vision_controller.get_last_debug()
        except Exception:
            dbg = None

        if dbg and isinstance(dbg, dict) and 'best_score' in dbg:
            bs = float(dbg.get('best_score') or 0.0)
            meta = dbg.get('meta')
            region = dbg.get('region')
            logging.getLogger(__name__).info(
                "search: miss after 8 attempts. best_score=%.3f meta=%s region=%s",
                bs, str(meta), str(region)
            )
            self._log(f'Search bar not found. Best score={bs:.2f} (need >= 0.50–0.70). '
                     'Try re-capturing closer to the field center.')
        else:
            logging.getLogger(__name__).info("search: miss after 8 attempts. no debug meta available")
            self._log('Search bar not found on screen.')

    def _perform_search_input(self, input_controller, coords: tuple, text: str,
                            corr: str, logger, _t) -> None:
        """Perform mouse movement, clicking, and text input."""
        # Move cursor and allow a brief frame to render
        t_phase = _t.perf_counter()
        input_controller.move_mouse(*coords)
        try:
            _t.sleep(0.02)
        except Exception:
            pass

        # Click to focus the field
        input_controller.click_button('left', presses=1, interval=0.0)
        try:
            _t.sleep(0.03)
        except Exception:
            pass

        try:
            logger.info("macro=F2 phase=focus_field corr=%s duration_ms=%.1f",
                       corr, (_t.perf_counter() - t_phase) * 1000.0)
        except Exception:
            pass

        # Clear any existing input using a more robust approach
        t_phase = _t.perf_counter()
        # Use Ctrl+A to select all text, then Delete to clear
        input_controller.hotkey('ctrl', 'a')
        try:
            _t.sleep(0.03)  # allow selection highlight to register
        except Exception:
            pass
        input_controller.press_key('delete')
        try:
            _t.sleep(0.02)
        except Exception:
            pass

        try:
            logger.info("macro=F2 phase=clear_field corr=%s duration_ms=%.1f",
                       corr, (_t.perf_counter() - t_phase) * 1000.0)
        except Exception:
            pass

        # Paste the desired term (fast and reliable), fallback to precise typing if needed
        t_phase = _t.perf_counter()
        try:
            if hasattr(input_controller, 'paste_text'):
                input_controller.paste_text(text, pre_delay=0.02, settle=0.01)
            else:
                input_controller.type_text_precise(text, interval=0.02, pre_delay=0.05)
        except Exception:
            try:
                input_controller.type_text_precise(text, interval=0.02, pre_delay=0.05)
            except Exception:
                pass

        try:
            _t.sleep(0.015)
        except Exception:
            pass

        # Press Enter to apply filter
        input_controller.press_key('enter')
        try:
            logger.info("macro=F2 phase=type_and_apply corr=%s duration_ms=%.1f",
                       corr, (_t.perf_counter() - t_phase) * 1000.0)
        except Exception:
            pass

        # Give the game a brief moment to apply the filter before scanning
        try:
            # Give the game a brief moment to apply the filter before scanning
            # Slightly increased to improve reliability on slower frames
            _t.sleep(0.10)
        except Exception:
            pass

    def _perform_item_matching(self, vision_controller, input_controller, text: str,
                             _abs_roi_env: str, tmpl: str, corr: str, logger, _t) -> None:
        """Perform ROI calibration and item matching."""
        try:
            start_roi = _t.perf_counter()

            # ROI calibration logic
            inv_roi = self._setup_inventory_roi(vision_controller, _abs_roi_env, tmpl, logger)
            self._apply_subroi_intersection(_abs_roi_env, inv_roi, logger)

            roi_bgr, roi_region = vision_controller.grab_inventory_bgr()
            dur_roi = (_t.perf_counter() - start_roi) * 1000.0
            logger.info("macro=F2 phase=roi_grab corr=%s duration_ms=%.1f roi=%dx%d",
                       corr, dur_roi, int(roi_region.get('width', 0)), int(roi_region.get('height', 0)))

            # Armor matcher (lazy init)
            if self._armor_matcher is None and ArmorMatcher is not None:
                base_dir = self.config_manager.config_path.parent
                self._armor_matcher = ArmorMatcher(assets_dir=Path('assets'),
                                                 app_templates_dir=base_dir / 'templates')

            # Perform matching and equipment
            self._match_and_equip_item(roi_bgr, roi_region, text, input_controller,
                                     corr, logger, _t, vision_controller)

        except Exception:
            pass

    def _setup_inventory_roi(self, vision_controller, _abs_roi_env: str, tmpl: str, logger) -> Optional[Dict]:
        """Setup inventory ROI using F6 ROI or calibration."""
        inv_roi = None

        # If F6 ROI exists, use it directly for speed instead of slow calibration
        if _abs_roi_env:
            try:
                parts = [int(p.strip()) for p in _abs_roi_env.split(',')]
                if len(parts) == 4:
                    inv_roi = {
                        'left': int(parts[0]), 'top': int(parts[1]),
                        'width': int(parts[2]), 'height': int(parts[3])
                    }
                    # Set the F6 ROI as the inventory ROI on vision controller
                    vision_controller.inventory_roi = inv_roi
                    logger.info("F6 ROI: using F6 ROI directly for speed (skipping calibration)")
            except Exception:
                pass

        # Only do slow calibration if no F6 ROI available
        if inv_roi is None:
            cal_start = time.perf_counter()
            try:
                # Use a slightly lower confidence for calibration to improve robustness at 4K
                inv_roi = vision_controller.calibrate_inventory_roi_from_search(str(tmpl), min_conf=0.65)
            except Exception:
                inv_roi = None
            cal_time = (time.perf_counter() - cal_start) * 1000.0
            logger.info("timing: ROI calibration = %.1f ms", cal_time)

        # Fallback: if calibration failed but F6 ROI exists, use it directly as inventory ROI
        try:
            if inv_roi is None and _abs_roi_env:
                parts2 = [int(p.strip()) for p in _abs_roi_env.split(',')]
                if len(parts2) == 4:
                    vision_controller.inventory_roi = {
                        'left': int(parts2[0]), 'top': int(parts2[1]),
                        'width': int(parts2[2]), 'height': int(parts2[3])
                    }
                    logger.info("F6 ROI: using F6 as inventory ROI (calibration failed)")
        except Exception:
            pass

        return inv_roi

    def _apply_subroi_intersection(self, _abs_roi_env: str, inv_roi: Optional[Dict], logger) -> None:
        """Apply F6 ROI intersection as sub-ROI if applicable."""
        try:
            if _abs_roi_env and isinstance(inv_roi, dict):
                parts = [int(p.strip()) for p in _abs_roi_env.split(',')]
                if len(parts) == 4:
                    inv_left = int(inv_roi.get('left', 0))
                    inv_top = int(inv_roi.get('top', 0))
                    inv_w = int(inv_roi.get('width', 0))
                    inv_h = int(inv_roi.get('height', 0))
                    abs_left, abs_top, abs_w, abs_h = parts
                    abs_right, abs_bottom = abs_left + abs_w, abs_top + abs_h
                    inv_right, inv_bottom = inv_left + inv_w, inv_top + inv_h
                    inter_left, inter_top = max(inv_left, abs_left), max(inv_top, abs_top)
                    inter_right, inter_bottom = min(inv_right, abs_right), min(inv_bottom, abs_bottom)

                    # Calculate intersection for ROI optimization
                    logger.info("F6 ROI intersection: F6=(%d,%d,%d,%d) inv=(%d,%d,%d,%d) result=(%d,%d,%d,%d)",
                               abs_left, abs_top, abs_w, abs_h,
                               inv_left, inv_top, inv_w, inv_h,
                               inter_left, inter_top, inter_right-inter_left, inter_bottom-inter_top)

                    self._log_roi_monitors(abs_left, abs_top, abs_w, abs_h, inv_left, inv_top, inv_w, inv_h, logger)

                    if inter_right > inter_left and inter_bottom > inter_top and inv_w > 0 and inv_h > 0:
                        rl = (inter_left - inv_left) / float(inv_w)
                        rt = (inter_top - inv_top) / float(inv_h)
                        rw = (inter_right - inter_left) / float(inv_w)
                        rh = (inter_bottom - inter_top) / float(inv_h)
                        os.environ['GW_INV_SUBROI'] = f"{rl:.4f},{rt:.4f},{rw:.4f},{rh:.4f}"
                        logger.info("F6 ROI: using intersection as sub-ROI: rel=(%.3f,%.3f,%.3f,%.3f)",
                                   rl, rt, rw, rh)
                    else:
                        # No overlap: clear sub-ROI to avoid hiding items
                        logger.info("F6 ROI: no overlap with inventory ROI, clearing sub-ROI")
                        if 'GW_INV_SUBROI' in os.environ:
                            os.environ.pop('GW_INV_SUBROI', None)
        except Exception:
            pass

    def _log_roi_monitors(self, abs_left: int, abs_top: int, abs_w: int, abs_h: int,
                         inv_left: int, inv_top: int, inv_w: int, inv_h: int, logger) -> None:
        """Log which monitors ROIs are on."""
        try:
            import mss
            with mss.mss() as sct:
                monitors = sct.monitors
                f6_mon = inv_mon = "unknown"
                for i, mon in enumerate(monitors):
                    if i == 0:  # Skip virtual screen
                        continue
                    # Check F6 ROI center
                    f6_cx, f6_cy = abs_left + abs_w//2, abs_top + abs_h//2
                    if (mon['left'] <= f6_cx < mon['left'] + mon['width'] and
                        mon['top'] <= f6_cy < mon['top'] + mon['height']):
                        f6_mon = f"monitor_{i}"
                    # Check inventory ROI center
                    inv_cx, inv_cy = inv_left + inv_w//2, inv_top + inv_h//2
                    if (mon['left'] <= inv_cx < mon['left'] + mon['width'] and
                        mon['top'] <= inv_cy < mon['top'] + mon['height']):
                        inv_mon = f"monitor_{i}"
                logger.info("F6 ROI monitors: F6_ROI=%s, INV_ROI=%s", f6_mon, inv_mon)
        except Exception:
            pass

    def _match_and_equip_item(self, roi_bgr, roi_region: Dict, text: str, input_controller,
                            corr: str, logger, _t, vision_controller) -> None:
        """Perform item matching and equipment."""
        name_norm = str(text).strip().lower().replace(' ', '_')
        # Continuous search within a time window before forcing move to next piece
        window_sec = 0.7  # Reduced from 1.0 for faster swaps
        try:
            window_sec = float(os.getenv('GW_ITEM_MATCH_WINDOW', '0.7') or 0.7)
        except Exception:
            window_sec = 1.0

        threshold = 0.17 if any(piece in name_norm for piece in ['chestpiece', 'gauntlets']) else 0.25
        start_match = _t.perf_counter()
        match = None
        attempts = 0
        while (_t.perf_counter() - start_match) < window_sec:
            if self._armor_matcher is None:
                break
            attempts += 1
            t_try = _t.perf_counter()
            try:
                match = self._armor_matcher.best_for_name(
                    roi_bgr, name_norm, threshold=threshold, early_exit=True
                )
            except Exception:
                match = None
            dur_try = (_t.perf_counter() - t_try) * 1000.0
            best_sc = None
            try:
                best_sc = self._armor_matcher.get_last_best(name_norm)
            except Exception:
                best_sc = None
            logger.info(
                (
                    "macro=F2 phase=match_item_try corr=%s name=%s attempt=%d "
                    "duration_ms=%.1f found=%s best_score=%s"
                ),
                corr, name_norm, attempts, dur_try, bool(match),
                f"{float(best_sc):.3f}" if best_sc is not None else "n/a"
            )
            if match:
                break
            # Small pause and refresh ROI to catch items that load a frame later
            try:
                _t.sleep(0.05)
            except Exception:
                pass
            try:
                roi_bgr, roi_region = vision_controller.grab_inventory_bgr()
            except Exception:
                pass

        total_match_ms = (_t.perf_counter() - start_match) * 1000.0
        logger.info(
            "macro=F2 phase=match_item_window corr=%s name=%s attempts=%d total_ms=%.1f found=%s",
            corr, name_norm, attempts, total_match_ms, bool(match)
        )

        if match:
            self._equip_matched_item(match, roi_bgr, roi_region, input_controller,
                                   corr, logger, _t, vision_controller)
        else:
            self._log_match_failure(name_norm, corr, logger)
            # No fixed delay here; let the outer sequence advance to the next piece

    def _equip_matched_item(self, match, roi_bgr, roi_region: Dict, input_controller,
                          corr: str, logger, _t, vision_controller) -> None:
        """Equip the matched item."""
        x, y, _, _, w, h = match

        # Capture a small patch before interaction to detect change after equip
        _pre_patch = self._capture_item_patch(roi_bgr, x, y, w, h)

        abs_x = int(roi_region['left']) + int(x) + int(w) // 2
        abs_y = int(roi_region['top']) + int(y) + int(h) // 2

        # Time the mouse movement and clicking
        start_mouse = _t.perf_counter()
        input_controller.move_mouse(abs_x, abs_y)
        mouse_move_time = (_t.perf_counter() - start_mouse) * 1000.0

        try:
            _t.sleep(0.015)  # reduced from 0.025 for faster interaction
        except Exception:
            pass

        start_click = _t.perf_counter()
        input_controller.click_button('left', presses=1, interval=0.0)
        click_time = (_t.perf_counter() - start_click) * 1000.0

        try:
            _t.sleep(0.030)  # reduced from 0.045 for faster equipment
        except Exception:
            pass

        start_equip = _t.perf_counter()
        # Ensure equip registers: double E press with minimal interval
        input_controller.press_key('e', presses=1, interval=0.0)
        try:
            _t.sleep(0.060)  # reduced from 0.090 for faster E-press timing
        except Exception:
            pass
        input_controller.press_key('e', presses=1, interval=0.0)
        # Small settle after second E before verifying
        try:
            _t.sleep(0.020)  # reduced from 0.030 for faster verification
        except Exception:
            pass

        # Intelligent wait: confirm local patch changes (item moved/equipped) before proceeding
        self._verify_item_change(vision_controller, _pre_patch, x, y, w, h, input_controller)

        equip_time = (_t.perf_counter() - start_equip) * 1000.0

        total_interaction = mouse_move_time + 2.0 + click_time + 1.0 + equip_time
        logger.info("macro=F2 phase=click_and_equip corr=%s mouse_ms=%.1f click_ms=%.1f equip_ms=%.1f total_ms=%.1f",
                   corr, mouse_move_time, click_time, equip_time, total_interaction)

        # Move mouse back to search box area to prepare for next search
        try:
            # Prefer returning directly to the cached search bar coordinates (avoids extra visible hop)
            coords_cached = getattr(self, '_cached_search_coords', None)
            if coords_cached is not None:
                sx, sy = coords_cached  # absolute screen coords
                input_controller.move_mouse(int(sx), int(sy))
                logger.info(
                    "macro=F2 phase=return_to_search corr=%s using=cached coords=(%d,%d)",
                    corr, int(sx), int(sy)
                )
            else:
                # Fallback: use a neutral position above the inventory region
                search_x = roi_region['left'] + roi_region['width'] // 2
                search_y = roi_region['top'] - 50
                input_controller.move_mouse(search_x, search_y)
                logger.info(
                    "macro=F2 phase=return_to_search corr=%s using=fallback moved_to=(%d,%d)",
                    corr, search_x, search_y
                )
        except Exception:
            pass

    def _capture_item_patch(self, roi_bgr, x: int, y: int, w: int, h: int):
        """Capture item patch for change detection."""
        try:
            yy0 = max(0, int(y))
            xx0 = max(0, int(x))
            yy1 = min(int(y + h), roi_bgr.shape[0])
            xx1 = min(int(x + w), roi_bgr.shape[1])
            if yy1 > yy0 and xx1 > xx0:
                return roi_bgr[yy0:yy1, xx0:xx1].copy()
        except Exception:
            pass
        return None

    def _verify_item_change(self, vision_controller, _pre_patch, x: int, y: int, w: int, h: int,
                          input_controller) -> None:
        """Verify that item has changed/moved after equipment."""
        try:
            changed = False
            for _chk in range(6):  # up to ~120ms
                try:
                    time.sleep(0.02)
                except Exception:
                    pass
                roi_after, _ = vision_controller.grab_inventory_bgr()
                # Recompute patch bounds (accounting for possible minor shift)
                yy0 = max(0, int(y))
                xx0 = max(0, int(x))
                yy1 = min(int(y + h), roi_after.shape[0])
                xx1 = min(int(x + w), roi_after.shape[1])
                if yy1 <= yy0 or xx1 <= xx0:
                    changed = True
                    break
                _post_patch = roi_after[yy0:yy1, xx0:xx1]
                if _pre_patch is None or _post_patch.size == 0:
                    changed = True
                    break
                try:
                    import cv2 as _cv
                    import numpy as _np
                    diff = _cv.absdiff(_post_patch, _pre_patch)
                    score = float(_np.mean(diff))
                    if score >= 3.0:
                        changed = True
                        break
                except Exception:
                    changed = True
                    break

            # If no change detected, one more click+E to force action
            if not changed:
                input_controller.click_button('left', presses=1, interval=0.0)
                try:
                    time.sleep(0.006)
                except Exception:
                    pass
                input_controller.press_key('e', presses=1, interval=0.0)
        except Exception:
            pass

    def _log_match_failure(self, name_norm: str, corr: str, logger) -> None:
        """Log item matching failure with debug info."""
        # Include best observed score for visibility
        best_sc = None
        try:
            if self._armor_matcher and hasattr(self._armor_matcher, 'get_last_best'):
                best_sc = self._armor_matcher.get_last_best(name_norm)
        except Exception:
            best_sc = None

        if best_sc is not None:
            logger.info("macro=F2 phase=match_item corr=%s name=%s result=no_match best_score=%.3f",
                       corr, name_norm, float(best_sc))
        else:
            logger.info("macro=F2 phase=match_item corr=%s name=%s result=no_match", corr, name_norm)
