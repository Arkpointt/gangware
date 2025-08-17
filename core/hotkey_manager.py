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
import sys

if sys.platform == "win32":
    import ctypes
    user32 = ctypes.windll.user32
else:
    user32 = None


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
        # Use a lightweight, dependency-free approach on Windows by
        # polling GetAsyncKeyState. This avoids requiring users to
        # install external packages; the app ships as an executable.
        if user32 is None:
            if self.overlay:
                self.overlay.set_status("Calibration is supported on Windows only.")
            return False

        def vk_name(vk: int) -> str:
            """Return a human-readable name for common virtual key codes."""
            # Mouse buttons
            mouse_map = {1: "left", 2: "right", 4: "middle", 5: "xbutton1", 6: "xbutton2"}
            if vk in mouse_map:
                return mouse_map[vk]
            # Letters
            if 0x41 <= vk <= 0x5A:
                return chr(vk)
            # Numbers
            if 0x30 <= vk <= 0x39:
                return chr(vk)
            # Function keys
            if 0x70 <= vk <= 0x87:
                return f"F{vk - 0x6F}"
            special = {
                0x1B: "esc",
                0x20: "space",
                0x09: "tab",
                0x0D: "enter",
                0x10: "shift",
                0x11: "ctrl",
                0x12: "alt",
            }
            return special.get(vk, f"vk_{vk}")

        def capture_input(prompt: str) -> Optional[str]:
            """Poll GetAsyncKeyState until a valid key or mouse button is pressed.

            Returns a string like 'key_A' or 'mouse_xbutton1', or '__restart__'
            when the user presses Escape to clear and re-enter.
            """
            if self.overlay:
                self.overlay.prompt_key_capture(prompt)

            while True:
                # Scan a reasonable range of virtual-key codes
                for vk in range(1, 256):
                    state = user32.GetAsyncKeyState(vk)
                    if state & 0x8000:
                        name = vk_name(vk)
                        # Left/right clicks are explicitly rejected
                        if name in ("left", "right"):
                            if self.overlay:
                                self.overlay.set_status(
                                    "Left/Right click not allowed — use another button or a keyboard key."
                                )
                            # small debounce
                            time.sleep(0.2)
                            break
                        # Esc acts as a restart/clear signal
                        if name == "esc":
                            if self.overlay:
                                self.overlay.set_status("Cleared current value — press a new key or button.")
                            return "__restart__"

                        # Determine whether this was a mouse button or keyboard key
                        if vk in (1, 2, 4, 5, 6):
                            return f"mouse_{name}"
                        return f"key_{name}"
                time.sleep(0.02)
        try:
            # Allow restart when user presses Esc — loop until a real value
            while True:
                inv_key = capture_input("Press your Inventory key (keyboard or mouse)")
                if not inv_key:
                    return False
                if inv_key == "__restart__":
                    # restart capture
                    continue
                break

            while True:
                tek_key = capture_input("Press your Tek Punch Cancel key (keyboard or mouse)")
                if not tek_key:
                    return False
                if tek_key == "__restart__":
                    continue
                break

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


