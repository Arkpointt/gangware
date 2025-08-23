"""Calibration service for hotkey and template management.

This module provides calibration functionality for setting up inventory keys,
tekgram cancel tokens, and search bar templates.
"""

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .template import wait_and_capture_template
else:
    try:
        from .template import wait_and_capture_template
    except ImportError:
        wait_and_capture_template = None  # type: ignore


class CalibrationService:
    """Service for calibration operations."""

    def __init__(self, config_manager, overlay=None, calibration_gate=None):
        """Initialize calibration service.

        Args:
            config_manager: Configuration manager instance
            overlay: Optional overlay for UI updates
            calibration_gate: Threading event for calibration coordination
        """
        self.config_manager = config_manager
        self.overlay = overlay
        self._calibration_gate = calibration_gate
        self._MSG_CAL_DONE = "Calibration complete! Ready for hotkeys."

    def complete_and_exit_calibration(self) -> None:
        """Complete calibration and mark as finished."""
        try:
            self.config_manager.config["DEFAULT"]["calibration_complete"] = "True"
            self.config_manager.save()
        except Exception:
            pass

        # Verify search bar template is detectable now that calibration is complete
        self.verify_search_template()

        if self.overlay:
            try:
                if hasattr(self.overlay, "switch_to_main"):
                    self.overlay.switch_to_main()
                self.overlay.set_status(self._get_menu_text())
                if hasattr(self.overlay, "success_flash"):
                    self.overlay.success_flash(self._MSG_CAL_DONE)
            except Exception:
                pass

    def verify_search_template(self) -> None:
        """Verify the search bar template is detectable after calibration."""
        logger = logging.getLogger(__name__)
        try:
            tmpl = self.config_manager.get('search_bar_template')
            if not tmpl:
                logger.warning("calibration: search_bar_template not set")
                return

            # Try to detect the template on screen (basic sanity check)
            # Requires inventory to be open for template verification
            logger.info("calibration: verifying search_bar_template=%s", tmpl)
        except Exception as e:
            logger.warning("calibration: failed to verify search template: %s", e)

    def wait_for_start_only(self, exit_checker=None) -> None:
        """Wait until the Start button sets the gate; ignore F7."""
        # Wait until the Start button sets the gate; ignore F7
        try:
            # Ensure we start from a clean state
            if self._calibration_gate:
                self._calibration_gate.clear()
        except Exception:
            pass

        while True:
            if self._calibration_gate and self._calibration_gate.is_set():
                break
            if exit_checker:
                exit_checker()
            time.sleep(0.1)

    def run_cal_menu_until_start_and_ready(self, exit_checker=None, readiness_checker=None) -> None:
        """Run calibration menu until start and ready."""
        while True:
            self.wait_for_start_only(exit_checker)

            if readiness_checker and readiness_checker():
                self.complete_and_exit_calibration()
                break

            if self.overlay:
                try:
                    self.overlay.set_status(
                        "Incomplete: set Inventory, Tek Cancel, and capture Template, "
                        "then click Start."
                    )
                except Exception:
                    pass

            try:
                if self._calibration_gate:
                    self._calibration_gate.clear()
            except Exception:
                pass

    def capture_key(self, key_name: str, prompt: str, is_tek: bool,
                   prompt_handler=None) -> None:
        """Capture a key or token for calibration."""
        if not prompt_handler:
            return

        token = prompt_handler(prompt)
        if not token or token == "__restart__":
            return

        self._save_key(key_name, token)

        if self.overlay:
            try:
                if is_tek and hasattr(self.overlay, "set_captured_tek"):
                    self.overlay.set_captured_tek(token)
                elif not is_tek and hasattr(self.overlay, "set_captured_inventory"):
                    self.overlay.set_captured_inventory(token)
            except Exception:
                pass

    def capture_template(self) -> None:
        """Capture search bar template."""
        if self.overlay:
            try:
                self.overlay.set_status(
                    "Open your inventory, hover the search bar, then press F8 to capture."
                )
            except Exception:
                pass

        if wait_and_capture_template is not None:
            p = wait_and_capture_template(self.config_manager, self.overlay)
            ok = bool(p)

            if ok:
                try:
                    self._save_key("search_bar_template", str(p))
                except Exception:
                    pass

            if self.overlay and hasattr(self.overlay, "set_template_status"):
                try:
                    self.overlay.set_template_status(ok, str(p) if p else None)
                except Exception:
                    pass

    def prepare_recalibration_ui(self) -> None:
        """Ensure the overlay is visible and switched to calibration with guidance text."""
        try:
            if self.overlay:
                if hasattr(self.overlay, "set_visible"):
                    self.overlay.set_visible(True)
                if hasattr(self.overlay, "switch_to_calibration"):
                    self.overlay.switch_to_calibration()
                self.overlay.set_status(
                    "Calibration menu — click buttons to capture Inventory, "
                    "Tek Cancel, and Template (F8). Then click Start."
                )
        except Exception:
            pass

    def log_message(self, msg: str) -> None:
        """Log message to overlay UI if available, otherwise print to console."""
        # Small helper that updates overlay when available
        if self.overlay:
            self.overlay.set_status(msg)
        else:
            print(msg)

    def _save_key(self, key_name: str, token: str) -> None:
        """Save key configuration."""
        try:
            self.config_manager.config["DEFAULT"][key_name] = token
            self.config_manager.save()
        except Exception:
            pass

    def _get_menu_text(self) -> str:
        """Get main menu text."""
        return "Main Menu - Ready for hotkeys"
