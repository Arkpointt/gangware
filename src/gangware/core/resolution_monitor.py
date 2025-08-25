"""Resolution and Window Mode Monitor for ARK: Survival Ascended.

Periodically detects desktop resolution, game window resolution, and window mode
(fullscreen, fullscreen windowed, or windowed) and updates the configuration.
"""
import logging
import threading
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)


class ResolutionMonitor(threading.Thread):
    """Monitor system and game resolution/window mode changes."""

    def __init__(self, config_manager: Any, overlay: Optional[Any] = None, interval: float = 10.0):
        super().__init__(daemon=True, name="ResolutionMonitor")
        self.config_manager = config_manager
        self.overlay = overlay
        self.interval = interval
        self._stop_event = threading.Event()

        # Initialize from config values if they exist
        self._last_desktop_resolution = self.config_manager.get("desktop_resolution", fallback="")
        self._last_game_resolution = self.config_manager.get("game_resolution", fallback="")
        self._last_window_mode = self.config_manager.get("window_mode", fallback="")

        # Supported window modes for ARK automation
        self._supported_modes = {"windowed", "fullscreen_windowed"}
        self._warned_about_mode = False

    def stop(self) -> None:
        """Stop the monitoring thread."""
        self._stop_event.set()

    def run(self) -> None:
        """Main monitoring loop."""
        logger.info("Resolution monitor started (interval=%.1fs)", self.interval)

        # Initial detection
        self._detect_and_update()

        while not self._stop_event.wait(self.interval):
            try:
                self._detect_and_update()
            except Exception as e:
                logger.warning("Resolution monitoring error: %s", e)

        logger.info("Resolution monitor stopped")

    def _detect_and_update(self) -> None:
        """Detect current resolution and window mode, update config if changed."""
        try:
            # Get current measurements
            desktop_res = self._get_desktop_resolution()
            game_res, window_mode = self._get_game_window_info()

            # Check for changes (only report if this is the first detection OR values actually changed)
            changed = False
            is_first_detection = (not self._last_desktop_resolution and
                                 not self._last_game_resolution and
                                 not self._last_window_mode)

            if desktop_res != self._last_desktop_resolution:
                self._last_desktop_resolution = desktop_res
                self.config_manager.config["DEFAULT"]["desktop_resolution"] = desktop_res
                changed = True
                if not is_first_detection:  # Only log if not the initial detection
                    logger.info("Desktop resolution changed: %s", desktop_res)

            if game_res != self._last_game_resolution:
                self._last_game_resolution = game_res
                self.config_manager.config["DEFAULT"]["game_resolution"] = game_res
                changed = True
                if not is_first_detection:  # Only log if not the initial detection
                    logger.info("Game resolution changed: %s", game_res)

            if window_mode != self._last_window_mode:
                self._last_window_mode = window_mode
                self.config_manager.config["DEFAULT"]["window_mode"] = window_mode
                changed = True
                if not is_first_detection:  # Only log if not the initial detection
                    logger.info("Window mode changed: %s", window_mode)

                # Reset warning flag when window mode changes
                self._warned_about_mode = False

            # Check for unsupported window modes and warn user
            self._check_window_mode_compatibility(window_mode)

            # Save config if anything changed
            if changed:
                try:
                    self.config_manager.save()
                    # Only show overlay message for actual changes, not initial detection
                    if self.overlay and not is_first_detection:
                        status_msg = (
                            f"Resolution updated: Desktop={desktop_res}, "
                            f"Game={game_res}, Mode={window_mode}"
                        )
                        self.overlay.set_status_safe(status_msg)
                except Exception as e:
                    logger.warning("Failed to save resolution config: %s", e)

        except Exception as e:
            logger.warning("Resolution detection failed: %s", e)

    def _get_desktop_resolution(self) -> str:
        """Get desktop resolution as 'widthxheight' or 'unknown' if detection fails."""
        try:
            from .win32 import utils as w32
            monitor = w32.current_monitor_bounds()

            # Check if we got valid monitor bounds
            width = monitor.get('width', 0)
            height = monitor.get('height', 0)

            if width > 0 and height > 0:
                return f"{width}x{height}"
            else:
                # Resolution detection failed
                if self.overlay:
                    self.overlay.set_status_safe("⚠️ Unable to detect display resolution")
                logger.warning("Failed to detect display resolution - invalid dimensions")
                return "unknown"
        except Exception as e:
            # Resolution detection failed
            if self.overlay:
                self.overlay.set_status_safe("⚠️ Unable to detect display resolution")
            logger.warning("Failed to detect display resolution: %s", e)
            return "unknown"

    def _get_game_window_info(self) -> Tuple[str, str]:
        """Get game window resolution and mode.

        Returns:
            Tuple of (resolution, window_mode)
            resolution: 'widthxheight' or 'unknown'
            window_mode: 'fullscreen', 'fullscreen_windowed', 'windowed', or 'not_running'
        """
        try:
            from .win32 import utils as w32

            # Try to get ARK window rect
            ark_rect = w32.ark_window_rect_by_proc()
            if not ark_rect:
                return "unknown", "not_running"

            left, top, right, bottom = ark_rect
            game_width = right - left
            game_height = bottom - top
            game_resolution = f"{game_width}x{game_height}"

            # Determine window mode
            window_mode = self._determine_window_mode(left, top, game_width, game_height)

            return game_resolution, window_mode

        except Exception as e:
            logger.debug("Game window detection failed: %s", e)
            return "unknown", "not_running"

    def _determine_window_mode(self, left: int, top: int, width: int, height: int) -> str:
        """Determine window mode based on window position and size."""
        try:
            from .win32 import utils as w32

            # Get desktop bounds
            desktop = w32.current_monitor_bounds()
            desktop_width = desktop.get('width', 0)
            desktop_height = desktop.get('height', 0)
            desktop_left = desktop.get('left', 0)
            desktop_top = desktop.get('top', 0)

            # If we couldn't detect desktop dimensions, we can't determine window mode
            if desktop_width == 0 or desktop_height == 0:
                return "unknown"

            # Check if window fills the entire monitor
            is_full_size = (width >= desktop_width and height >= desktop_height)
            is_at_origin = (left <= desktop_left and top <= desktop_top)

            if is_full_size and is_at_origin:
                # Could be fullscreen or fullscreen windowed
                # In true fullscreen, the window usually has no borders/decorations
                # and coordinates might be exactly (0,0) to (width, height)
                if left == desktop_left and top == desktop_top and width == desktop_width and height == desktop_height:
                    return "fullscreen_windowed"
                else:
                    return "fullscreen"
            else:
                # Window doesn't fill screen - definitely windowed
                return "windowed"

        except Exception:
            return "unknown"

    def _check_window_mode_compatibility(self, window_mode: str) -> None:
        """Check if current window mode is supported and warn user if not."""
        if window_mode in ["not_running", "unknown"]:
            # Don't warn for these states
            return

        if window_mode not in self._supported_modes and not self._warned_about_mode:
            warning_msg = (
                f"⚠️ Unsupported window mode: {window_mode}. "
                "For best results, use 'Windowed' or 'Fullscreen Windowed' mode in ARK settings."
            )

            logger.warning("Unsupported window mode detected: %s", window_mode)

            if self.overlay:
                self.overlay.set_status_safe(warning_msg)

            # Set flag to avoid repeated warnings
            self._warned_about_mode = True
        elif window_mode in self._supported_modes and self._warned_about_mode:
            # Window mode is now supported, clear warning flag and notify
            self._warned_about_mode = False
            if self.overlay:
                self.overlay.set_status_safe(f"✅ Window mode compatible: {window_mode}")

    def get_current_info(self) -> Dict[str, str]:
        """Get current resolution and window mode information."""
        desktop_res = self._get_desktop_resolution()
        game_res, window_mode = self._get_game_window_info()

        return {
            "desktop_resolution": desktop_res,
            "game_resolution": game_res,
            "window_mode": window_mode
        }

    def get_config_resolution(self) -> str:
        """Get the configured resolution from config.ini."""
        return self.config_manager.get("resolution", fallback="unknown")

    def get_detected_resolution(self) -> str:
        """Get the currently detected desktop resolution."""
        return self.config_manager.get("desktop_resolution", fallback="unknown")

    def is_window_mode_supported(self) -> bool:
        """Check if current window mode is supported for automation."""
        current_mode = self.config_manager.get("window_mode", fallback="unknown")
        return current_mode in self._supported_modes
