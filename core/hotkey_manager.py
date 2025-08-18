
"""
Hotkey Manager Module
Listens for hotkey commands and populates the task queue.

This implementation provides:
- A calibration flow to capture user-specific keys: the Inventory key and the Tek Punch Cancel key.
  The captured values are persisted into the provided ConfigManager under DEFAULT as
  `inventory_key` and `tek_punch_cancel_key`.
- Template capture step: prompts user to open inventory, hover the search bar,
  and press F8 to capture a small image region saved as a template. The path is
  stored under `search_bar_template`.
- Basic global hotkey handling on Windows using the Win32 API:
  - F1 toggles overlay visibility when available
  - F7 triggers recalibration (also detected globally)
  - F8 is used during calibration to capture the search bar template
  - F10 exits the application (best-effort)

The calibration uses the Windows GetAsyncKeyState polling to detect key/mouse input and mss to grab
screen regions for template capture. Calibration is marked complete only after the template is saved.
"""

import threading
import time
from typing import Optional, Tuple
import sys
import os
from pathlib import Path

import cv2  # type: ignore
import mss  # type: ignore
import numpy as np  # type: ignore

if sys.platform == "win32":
    import ctypes

    user32 = ctypes.windll.user32

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    def _cursor_pos() -> Tuple[int, int]:
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        return int(pt.x), int(pt.y)
else:
    user32 = None


class HotkeyManager(threading.Thread):
    """Hotkey listener thread.

    The thread can run a calibration flow when the required keys are not
    present in configuration. Calibration uses the Windows API to capture
    the next key press and F8-triggered screen capture for the search bar
    template.
    """

    def __init__(self, config_manager, task_queue, state_manager, overlay=None):
        super().__init__(daemon=True)
        self.config_manager = config_manager
        self.task_queue = task_queue
        self.state_manager = state_manager
        self.overlay = overlay
        self._recalibrate_event = threading.Event()
        self._f1_down = False  # debounce for F1 toggle
        self._f7_down = False  # debounce for F7 recalibration
        self._calibration_gate = threading.Event()

    def run(self):
        """Main loop for hotkey management.

        Ensures calibration is completed, then enters a polling loop for a
        minimal set of global hotkeys.
        """
        # If keys or template are missing, run calibration
        inv = self.config_manager.get("inventory_key")
        tek = self.config_manager.get("tek_punch_cancel_key")
        tmpl = self.config_manager.get("search_bar_template")
        if not inv or not tek or not tmpl:
            self._log("Waiting for Start to begin calibration")
            # Poll for F10 exit while waiting for Start
            while not self._calibration_gate.is_set():
                try:
                    if user32 is not None and (user32.GetAsyncKeyState(0x79) & 0x8000):
                        self._log("F10 pressed — exiting application")
                        try:
                            self.task_queue.put_nowait(None)
                        except Exception:
                            pass
                        os._exit(0)
                except Exception:
                    pass
                time.sleep(0.1)
            self._log("Starting calibration: capture keys and search bar template")
            success = self.calibrate()
            if success:
                self._log("Calibration complete")
            else:
                self._log("Calibration aborted or failed")

        # Main hotkey loop + recalibration trigger
        while True:
            # Global exit (F10) on Windows
            try:
                if user32 is not None and (user32.GetAsyncKeyState(0x79) & 0x8000):
                    self._log("F10 pressed — exiting application")
                    try:
                        # Try to stop the worker thread gracefully
                        self.task_queue.put_nowait(None)
                    except Exception:
                        pass
                    os._exit(0)
            except Exception:
                # Never let hotkey polling crash the thread
                pass

            # F1 toggles overlay visibility (debounced)
            try:
                if user32 is not None:
                    is_down = bool(user32.GetAsyncKeyState(0x70) & 0x8000)
                    if is_down and not self._f1_down:
                        # Rising edge
                        self._f1_down = True
                        try:
                            if self.overlay and hasattr(self.overlay, "toggle_visibility"):
                                self.overlay.toggle_visibility()
                        except Exception:
                            pass
                    elif not is_down and self._f1_down:
                        # Released
                        self._f1_down = False
            except Exception:
                pass

            # F7 triggers recalibration (global detection via Win32)
            try:
                if user32 is not None:
                    is_down_f7 = bool(user32.GetAsyncKeyState(0x76) & 0x8000)
                    if is_down_f7 and not self._f7_down:
                        # Rising edge -> request recalibration
                        self._f7_down = True
                        self._recalibrate_event.set()
                    elif not is_down_f7 and self._f7_down:
                        self._f7_down = False
            except Exception:
                pass

            # Recalibration requested
            if self._recalibrate_event.is_set():
                self._log("Recalibration requested")
                success = self.calibrate()
                if success and self.overlay and hasattr(self.overlay, "switch_to_main"):
                    try:
                        self.overlay.switch_to_main()
                    except Exception:
                        pass
                self._recalibrate_event.clear()

            time.sleep(0.1)

    def _maybe_exit_on_f10(self) -> None:
        try:
            if user32 is not None and (user32.GetAsyncKeyState(0x79) & 0x8000):
                self._log("F10 pressed — exiting application")
                try:
                    self.task_queue.put_nowait(None)
                except Exception:
                    pass
                os._exit(0)
        except Exception:
            pass

    def calibrate(self) -> bool:
        """Run interactive calibration capturing two keys and a template.

        Returns True when all values were captured and saved, False on
        error or if Windows API is unavailable.
        """
        if user32 is None:
            if self.overlay:
                self.overlay.set_status("Calibration is supported on Windows only.")
            return False

        try:
            # 1) Inventory key
            inv_key = self._prompt_until_valid("Press your Inventory key (keyboard or mouse)")
            if not inv_key:
                return False

            # 2) Tek Punch Cancel key
            tek_key = self._prompt_until_valid(
                "Press your Tek Punch Cancel key (keyboard or mouse)"
            )
            if not tek_key:
                return False

            # Persist the keys (not marking calibration complete yet)
            self._save_keys(inv_key, tek_key)

            # 3) Template capture: ask user to press F8 while hovering the search bar
            if self.overlay:
                self.overlay.set_status(
                    "Open your inventory, hover the search bar, then press F8 to capture."
                )

            tmpl_path = self._wait_and_capture_template()
            if not tmpl_path:
                if self.overlay:
                    self.overlay.set_status("Template capture cancelled or failed.")
                return False

            # Save template path and mark calibration complete
            self.config_manager.config["DEFAULT"]["search_bar_template"] = str(tmpl_path)
            self.config_manager.config["DEFAULT"]["calibration_complete"] = "True"
            self.config_manager.save()

            if self.overlay:
                self.overlay.set_status(
                    f"Calibration saved: Inventory={inv_key}, TekCancel={tek_key}\nTemplate={tmpl_path}"
                )
            return True
        except Exception as exc:  # pragma: no cover - environment dependent
            self._log(f"Calibration failed: {exc}")
            if self.overlay:
                self.overlay.set_status("Calibration failed: see logs")
            return False

    def _wait_and_capture_template(self) -> Optional[Path]:
        """Wait for F8 press and capture a small region around the cursor.

        Returns the saved Path on success, or None on failure/cancel.
        """
        # Wait for F8
        while True:
            is_down_f8 = bool(user32.GetAsyncKeyState(0x77) & 0x8000)
            if is_down_f8:
                break
            self._maybe_exit_on_f10()
            time.sleep(0.02)
        # Debounce: wait for release
        while bool(user32.GetAsyncKeyState(0x77) & 0x8000):
            self._maybe_exit_on_f10()
            time.sleep(0.02)

        try:
            x, y = _cursor_pos()
        except Exception:
            return None

        # Capture rectangle around cursor (width x height)
        w, h = 220, 50
        left = x - w // 2
        top = y - h // 2

        with mss.mss() as sct:
            # Clamp to virtual screen bounds (monitors[0] is the virtual bounding box)
            vb = sct.monitors[0]
            left = max(vb["left"], min(left, vb["left"] + vb["width"] - w))
            top = max(vb["top"], min(top, vb["top"] + vb["height"] - h))

            region = {"left": int(left), "top": int(top), "width": int(w), "height": int(h)}
            img = np.array(sct.grab(region))  # BGRA
            bgr = img[:, :, :3]

        # Compute output path assets/templates/search_bar.png relative to project root
        project_root = Path(__file__).resolve().parents[1]
        out_dir = project_root / "assets" / "templates"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "search_bar.png"
        try:
            cv2.imwrite(str(out_path), bgr)
            return out_path
        except Exception:
            return None

    def _vk_name(self, vk: int) -> str:
        """Return a human-readable name for common virtual key codes.

        Kept as an instance method so it can be unit-tested separately.
        """
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

    def _capture_input_windows(self, prompt: str) -> Optional[str]:
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
                    result = self._process_pressed_vk(vk)
                    if result == "__debounce__":
                        # small debounce handled in helper; skip to outer loop
                        break
                    return result
            self._maybe_exit_on_f10()
            time.sleep(0.02)

    def _process_pressed_vk(self, vk: int) -> Optional[str]:
        """Map a pressed virtual-key into a token or control signal.

        Returns:
        - 'mouse_x...' or 'key_X' for a valid input
        - '__restart__' when Esc was pressed
        - '__debounce__' when an invalid (left/right) mouse button was pressed
        """
        name = self._vk_name(vk)
        # F10 exits application from any capture loop
        if name == "F10":
            try:
                self._log("F10 pressed — exiting application")
                try:
                    self.task_queue.put_nowait(None)
                except Exception:
                    pass
            finally:
                os._exit(0)
        # Left/right clicks are explicitly rejected
        if name in ("left", "right"):
            if self.overlay:
                self.overlay.set_status(
                    "Left/Right click not allowed — use another button or a keyboard key."
                )
            time.sleep(0.2)
            return "__debounce__"

        # Esc acts as a restart/clear signal
        if name == "esc":
            if self.overlay:
                self.overlay.set_status("Cleared current value — press a new key or button.")
            return "__restart__"

        if vk in (1, 2, 4, 5, 6):
            return f"mouse_{name}"
        return f"key_{name}"

    def _prompt_until_valid(self, prompt: str) -> Optional[str]:
        """Prompt the user repeatedly until a non-restart value is captured.

        Returns the captured token, or None on unrecoverable failure.
        """
        while True:
            token = self._capture_input_windows(prompt)
            if not token:
                return None
            if token == "__restart__":
                continue
            return token

    def request_recalibration(self) -> None:
        """External trigger (e.g., GUI) to request recalibration on the hotkey thread."""
        self._recalibrate_event.set()

    def allow_calibration_start(self) -> None:
        """Allow the calibration to start by setting the gate event."""
        try:
            self._calibration_gate.set()
        except Exception:
            pass

    def _save_keys(self, inv_key: str, tek_key: str) -> None:
        """Persist captured calibration keys into the config manager (without completion)."""
        self.config_manager.config["DEFAULT"]["inventory_key"] = str(inv_key)
        self.config_manager.config["DEFAULT"]["tek_punch_cancel_key"] = str(tek_key)
        self.config_manager.save()

    def _log(self, msg: str) -> None:
        # Small helper that updates overlay when available
        if self.overlay:
            self.overlay.set_status(msg)
        else:
            print(msg)
