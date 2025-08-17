"""
Hotkey Manager Module
Listens for hotkey commands and populates the task queue.

This implementation adds a small calibration flow used to capture two
user-specific keys: the Inventory key and the Tek Punch Cancel key. The
captured values are written into the provided ConfigManager under the
DEFAULT section as `inventory_key` and `tek_punch_cancel_key`.
"""

import threading
import time
from typing import Optional

try:
    import keyboard  # type: ignore
except Exception:
    keyboard = None


class HotkeyManager(threading.Thread):
    """Hotkey listener thread.

    The thread can run a calibration flow when the required keys are not
    present in configuration. Calibration uses the `keyboard` package to
    capture the next key press.
    """

    def __init__(self, config_manager, task_queue, state_manager, overlay=None):
        super().__init__(daemon=True)
        self.config_manager = config_manager
        self.task_queue = task_queue
        self.state_manager = state_manager
        self.overlay = overlay

    def run(self):
        """Main loop for hotkey management.

        For now this starts by ensuring calibration has been completed.
        After calibration this method would normally register global
        hotkeys and dispatch tasks; that part remains a placeholder.
        """
        # If keys are missing, run calibration
        inv = self.config_manager.get("inventory_key")
        tek = self.config_manager.get("tek_punch_cancel_key")
        if not inv or not tek:
            self._log("Starting calibration: capturing Inventory and Tek Punch keys")
            success = self.calibrate()
            if success:
                self._log("Calibration complete")
            else:
                self._log("Calibration aborted or failed")

        # Main hotkey loop placeholder
        while True:
            time.sleep(1)

    def calibrate(self) -> bool:
        """Run interactive calibration capturing two key presses.

        Returns True when both keys were captured and saved, False on
        error or if the `keyboard` dependency is missing.
        """
        if keyboard is None:
            # Keyboard package not available - notify via overlay and abort
            if self.overlay:
                self.overlay.set_status("Calibration requires the 'keyboard' package.")
            return False

        # Helper to capture a single key press
        def capture(prompt: str) -> Optional[str]:
            if self.overlay:
                self.overlay.prompt_key_capture(prompt)
            # Wait for the next key event
            event = keyboard.read_event(suppress=False)
            # We're interested in key down events
            while event.event_type != "down":
                event = keyboard.read_event(suppress=False)
            # Normalize the name
            name = event.name
            # Convert numbers on top row to their key names when available
            return name

        try:
            inv_key = capture("Press your Inventory key (hobat 1-0 on some keyboards)")
            if not inv_key:
                return False
            tek_key = capture("Press your Tek Punch Cancel key (hobat 1-0)")
            if not tek_key:
                return False

            # Save into config
            self.config_manager.config["DEFAULT"]["inventory_key"] = str(inv_key)
            self.config_manager.config["DEFAULT"]["tek_punch_cancel_key"] = str(tek_key)
            self.config_manager.save()

            if self.overlay:
                self.overlay.set_status(f"Calibration saved: Inventory={inv_key}, TekCancel={tek_key}")
            return True
        except Exception as exc:  # pragma: no cover - environment dependent
            self._log(f"Calibration failed: {exc}")
            if self.overlay:
                self.overlay.set_status("Calibration failed: see logs")
            return False

    def _log(self, msg: str) -> None:
        # Small helper that updates overlay when available
        if self.overlay:
            self.overlay.set_status(msg)
        else:
            print(msg)


