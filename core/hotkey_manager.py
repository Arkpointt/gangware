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
    from pynput import keyboard as pkb, mouse as pmouse  # type: ignore
except Exception:
    pkb = None
    pmouse = None


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
        # Prefer pynput for combined keyboard+mouse capture
        if pkb is None or pmouse is None:
            if self.overlay:
                self.overlay.set_status("Calibration requires the 'pynput' package.")
            return False

        from threading import Event

        def capture_input(prompt: str) -> Optional[str]:
            """Wait for either a keyboard key or a mouse button, reject
            left/right clicks and the Esc key. Returns a normalized name.
            """
            if self.overlay:
                self.overlay.prompt_key_capture(prompt)

            result: dict = {"value": None}
            done = Event()

            # Keyboard callback
            def on_press(key):
                try:
                    name = None
                    if hasattr(key, "char") and key.char is not None:
                        name = key.char
                    else:
                        name = key.name  # special keys like esc, enter
                except Exception:
                    name = str(key)

                if name is None:
                    return

                # Normalize and handle Escape as a "restart" signal
                if str(name).lower() in ("esc", "escape"):
                    # Signal that the user wants to clear/restart the capture
                    result["value"] = "__restart__"
                    if self.overlay:
                        self.overlay.set_status("Cleared current value — press a new key or button.")
                    done.set()
                    return False

                result["value"] = f"key_{str(name)}"
                done.set()
                return False

            # Mouse callback
            def on_click(x, y, button, pressed):
                # We only care about press events
                if not pressed:
                    return
                try:
                    bname = button.name
                except Exception:
                    bname = str(button).lower()

                # Reject left and right clicks explicitly
                if bname in ("left", "right"):
                    if self.overlay:
                        self.overlay.set_status("Left/Right click not allowed — use another button or a keyboard key.")
                    return

                result["value"] = f"mouse_{bname}"
                done.set()
                return False

            k_listener = pkb.Listener(on_press=on_press)
            m_listener = pmouse.Listener(on_click=on_click)

            k_listener.start()
            m_listener.start()

            # Wait until an allowed input is captured
            done.wait()

            # Stop listeners
            try:
                k_listener.stop()
            except Exception:
                pass
            try:
                m_listener.stop()
            except Exception:
                pass

            return result["value"]
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


