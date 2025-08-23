"""Calibration Management for ARK: Survival Ascended.

Handles vision template calibration and UI interaction for setting up
inventory and Tek armor templates.
"""
import logging
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger(__name__)


class CalibrationManager:
    """Manages vision template calibration process."""

    def __init__(self, config_manager: Any, overlay: Optional[Any] = None):
        self.config_manager = config_manager
        self.overlay = overlay

        # Calibration state
        self._calibration_active = False
        self._recalibration_requested = False

    def ensure_calibrated(self) -> None:
        """Ensure vision templates are calibrated before use."""
        inv = self.config_manager.get("inventory_key")
        tek = self.config_manager.get("tek_punch_cancel_key")
        tmpl = self.config_manager.get("search_bar_template")
        if inv and tek and tmpl:
            if self.overlay:
                try:
                    # Prefill GUI with retained values so they remain visible
                    self._prefill_overlay_panel()
                    self.overlay.set_status("Calibration complete. Application ready for use.")
                except Exception:
                    pass
            return

        # Show calibration panel and process until ready
        self._show_calibration_menu("Calibration menu — use the buttons to capture each item, then click Start.")

    def process_recalibration(self, recalibrate_event: Any) -> None:
        """Handle recalibration request by processing the event."""
        if not recalibrate_event.is_set():
            return
        logger.info("Recalibration requested")
        self._show_calibration_menu("Calibration menu — use the buttons to capture each item, then click Start.")
        # Process calibration flow here
        recalibrate_event.clear()

    def is_calibration_ready(self) -> bool:
        """Check if all required templates are calibrated."""
        try:
            # Check for required template files
            required_templates = [
                "inventory_button_template.png",
                "tek_armor_template.png"
            ]

            assets_path = Path("assets")
            for template in required_templates:
                template_path = assets_path / template
                if not template_path.exists():
                    return False

            # Check config for calibration completion
            return bool(self.config_manager.get("calibration_complete", False))
        except Exception as e:
            logger.error(f"Error checking calibration readiness: {e}")
            return False

    def _prefill_overlay_panel(self) -> None:
        """Populate overlay calibration panel with current configuration values."""
        if not self.overlay:
            return
        try:
            if hasattr(self.overlay, "set_captured_inventory"):
                inv0 = self.config_manager.get("inventory_key")
                if inv0:
                    self.overlay.set_captured_inventory(inv0)
            if hasattr(self.overlay, "set_captured_tek"):
                tek0 = self.config_manager.get("tek_punch_cancel_key")
                if tek0:
                    self.overlay.set_captured_tek(tek0)
            if hasattr(self.overlay, "set_template_status"):
                tmpl0 = self.config_manager.get("search_bar_template")
                self.overlay.set_template_status(bool(tmpl0), tmpl0 or None)
        except Exception:
            pass

    def _show_calibration_menu(self, status: Optional[str] = None) -> None:
        """Show the calibration menu with optional status message."""
        if self.overlay:
            try:
                if hasattr(self.overlay, "switch_to_calibration"):
                    self.overlay.switch_to_calibration()
                if status:
                    self.overlay.set_status(status)
            except Exception:
                pass
