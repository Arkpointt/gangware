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
- Global hotkey handling (RegisterHotKey + polling fallbacks):
  - Global: F1 toggles overlay, F7 recalibration, F10 exit
  - In-game only: F2, F3, F4, Shift+Q, Shift+E, Shift+R
    (Only enqueue tasks when ArkAscended.exe is the active window)

Calibration uses the Windows GetAsyncKeyState polling to detect key/mouse input and mss to grab
screen regions for template capture. Calibration is marked complete only after the template is saved.
"""

import threading
import time
from typing import Optional, Tuple, Callable, Dict
import sys
import os
from pathlib import Path

import cv2  # type: ignore
import mss  # type: ignore
import numpy as np  # type: ignore

import ctypes

# Macro libraries
from macros import armor_swapper, combat

if sys.platform == "win32":
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    def _cursor_pos() -> Tuple[int, int]:
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        return int(pt.x), int(pt.y)
else:
    user32 = None
    kernel32 = None
    # Provide a minimal wintypes stub for non-Windows to satisfy linters/type-checkers.
    class _WinTypesStub:
        class MSG(ctypes.Structure):
            _fields_ = []
    wintypes = _WinTypesStub()


class HotkeyManager(threading.Thread):
    """Hotkey listener thread with global and game-specific hotkeys.

    - Global hotkeys (always active): F1 (toggle overlay), F7 (recalibrate), F10 (exit)
    - Game-specific hotkeys (only when ArkAscended.exe is the foreground process):
      F2, F3, F4, Shift+Q, Shift+E, Shift+R
    """

    def __init__(self, config_manager, task_queue, state_manager, overlay=None):
        super().__init__(daemon=True)
        self.config_manager = config_manager
        self.task_queue = task_queue
        self.state_manager = state_manager
        self.overlay = overlay
        self._recalibrate_event = threading.Event()
        self._f1_down = False  # debounce for F1 toggle (polling fallback)
        self._f7_down = False  # debounce for F7 recalibration (polling fallback)
        self._calibration_gate = threading.Event()
        # Common messages
        self._MSG_EXIT = "F10 pressed — exiting application"
        self._MSG_CAL_DONE = "Calibration complete"
        # Hotkey handler registry (id -> callable)
        self._hotkey_handlers: Dict[int, Callable[[], None]] = {}
        # Track whether global registration succeeded for F1 and F7 to suppress polling
        self._has_reg_f1 = False
        self._has_reg_f7 = False
        # Try to start a global hotkey message loop for robust handling
        self._start_hotkey_hook()

    # --------------------------- Thread entry ----------------------------
    def run(self):
        """Main loop for hotkey management with reduced branching."""
        self._ensure_calibrated()
        while True:
            self._handle_global_exit()
            self._handle_f1_toggle()  # polling fallback
            self._handle_f7_poll()    # polling fallback
            self._process_recalibration()
            time.sleep(0.1)

    def _ensure_calibrated(self) -> None:
        """Ensure calibration is completed; otherwise run the flow and update UI."""
        inv = self.config_manager.get("inventory_key")
        tek = self.config_manager.get("tek_punch_cancel_key")
        tmpl = self.config_manager.get("search_bar_template")
        if inv and tek and tmpl:
            if self.overlay:
                try:
                    self.overlay.set_status(self._menu_text())
                except Exception:
                    pass
            return

        self._log("Waiting for Start to begin calibration")
        self._poll_until_start_or_f7()
        self._log("Starting calibration: capture keys and search bar template")
        success = self.calibrate()
        if not success:
            self._log("Calibration aborted or failed")
            return

        self._log(self._MSG_CAL_DONE)
        if self.overlay and hasattr(self.overlay, "switch_to_main"):
            try:
                self.overlay.switch_to_main()
                self.overlay.set_status(self._menu_text())
                if hasattr(self.overlay, "show_success"):
                    self.overlay.show_success(self._MSG_CAL_DONE)
            except Exception:
                pass

    # --------------------------- Polling handlers ----------------------------
    def _maybe_exit_on_f10(self) -> None:
        try:
            if user32 is not None and (user32.GetAsyncKeyState(0x79) & 0x8000):
                self._log(self._MSG_EXIT)
                try:
                    self.task_queue.put_nowait(None)
                except Exception:
                    pass
                os._exit(0)
        except Exception:
            pass

    def _poll_until_start_or_f7(self) -> None:
        """Block until the calibration gate is set, F7 is pressed, or F10 exits."""
        while not self._calibration_gate.is_set():
            self._maybe_exit_on_f10()
            self._poll_f7_for_gate()
            time.sleep(0.1)

    def _handle_global_exit(self) -> None:
        self._maybe_exit_on_f10()

    def _handle_f1_toggle(self) -> None:
        # Suppress polling if global registration succeeded
        if getattr(self, "_has_reg_f1", False):
            return
        self._debounced_press(0x70, "_f1_down", self._on_hotkey_f1)

    def _handle_f7_poll(self) -> None:
        # Suppress polling if global registration succeeded
        if getattr(self, "_has_reg_f7", False):
            return
        try:
            if user32 is None:
                return
            is_down_f7 = bool(user32.GetAsyncKeyState(0x76) & 0x8000)
            self._update_f7_state(is_down_f7, set_gate=False)
        except Exception:
            pass

    def _update_f7_state(self, is_down_f7: bool, set_gate: bool) -> None:
        if is_down_f7 and not self._f7_down:
            self._f7_down = True
            if set_gate:
                try:
                    self._calibration_gate.set()
                except Exception:
                    pass
            self._prepare_recalibration_ui()
            if not set_gate:
                self._recalibrate_event.set()
        elif not is_down_f7 and self._f7_down:
            self._f7_down = False

    def _poll_f7_for_gate(self) -> None:
        if user32 is None:
            return
        try:
            is_down_f7 = bool(user32.GetAsyncKeyState(0x76) & 0x8000)
        except Exception:
            return
        self._update_f7_state(is_down_f7, set_gate=True)

    def _debounced_press(self, vk: int, flag_attr: str, on_press) -> None:
        try:
            if user32 is None:
                return
            is_down = bool(user32.GetAsyncKeyState(vk) & 0x8000)
            pressed = bool(getattr(self, flag_attr))
            if is_down and not pressed:
                setattr(self, flag_attr, True)
                try:
                    on_press()
                except Exception:
                    pass
            elif not is_down and pressed:
                setattr(self, flag_attr, False)
        except Exception:
            pass

    def _toggle_overlay_visibility(self) -> None:
        try:
            if self.overlay and hasattr(self.overlay, "toggle_visibility"):
                self.overlay.toggle_visibility()
        except Exception:
            pass

    # --------------------------- Hotkey hook (Windows) ----------------------------
    def _start_hotkey_hook(self) -> None:
        """Start a Windows message loop thread to catch global hotkeys via RegisterHotKey."""
        if sys.platform != "win32":
            return
        try:
            t = threading.Thread(target=self._hotkey_msg_loop, daemon=True)
            t.start()
        except Exception:
            pass

    def _hotkey_msg_loop(self) -> None:  # pragma: no cover - requires Windows messages
        try:
            msg = self._create_message_queue()
            self._register_hotkeys()
            self._pump_messages(msg)
        except Exception:
            pass
        finally:
            # Always attempt to unregister known IDs 1..9
            for i in range(1, 10):
                try:
                    user32.UnregisterHotKey(None, i)
                except Exception:
                    pass

    def _create_message_queue(self):
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
        return msg

    def _register_hotkeys(self) -> None:
        # IDs
        HK_F7 = 1
        HK_F10 = 2
        HK_F1 = 3
        HK_F2 = 4
        HK_F3 = 5
        HK_F4 = 6
        HK_S_Q = 7
        HK_S_E = 8
        HK_S_R = 9
        # Modifiers / VKs
        MOD_NONE = 0x0000
        MOD_SHIFT = 0x0004
        VK_F1, VK_F2, VK_F3, VK_F4 = 0x70, 0x71, 0x72, 0x73
        VK_F7, VK_F10 = 0x76, 0x79
        VK_Q, VK_E, VK_R = 0x51, 0x45, 0x52

        # Helper to register and log failures
        def _reg(id_: int, mod: int, vk: int, name: str) -> bool:
            try:
                ok = bool(user32.RegisterHotKey(None, id_, mod, vk))
                if not ok:
                    try:
                        err = kernel32.GetLastError() if kernel32 else 0
                        self._log(f"Failed to register hotkey {name} (id={id_}, err={err})")
                    except Exception:
                        self._log(f"Failed to register hotkey {name} (id={id_})")
                return ok
            except Exception:
                self._log(f"Exception while registering hotkey {name} (id={id_})")
                return False

        # Register global hotkeys
        ok_f7 = _reg(HK_F7, MOD_NONE, VK_F7, "F7")
        _reg(HK_F10, MOD_NONE, VK_F10, "F10")
        ok_f1 = _reg(HK_F1, MOD_NONE, VK_F1, "F1")
        self._has_reg_f7 = ok_f7
        self._has_reg_f1 = ok_f1
        # Register game-specific hotkeys
        _reg(HK_F2, MOD_NONE, VK_F2, "F2")
        _reg(HK_F3, MOD_NONE, VK_F3, "F3")
        _reg(HK_F4, MOD_NONE, VK_F4, "F4")
        _reg(HK_S_Q, MOD_SHIFT, VK_Q, "Shift+Q")
        _reg(HK_S_E, MOD_SHIFT, VK_E, "Shift+E")
        _reg(HK_S_R, MOD_SHIFT, VK_R, "Shift+R")

        # Map IDs to handlers to reduce branching in the message loop
        self._hotkey_handlers = {
            HK_F1: self._on_hotkey_f1,
            HK_F7: self._on_hotkey_f7,
            HK_F10: self._maybe_exit_on_f10,
            HK_F2: lambda: self._handle_macro_hotkey(self._task_equip_armor("flak"), "F2"),
            HK_F3: lambda: self._handle_macro_hotkey(self._task_equip_armor("tek"), "F3"),
            HK_F4: lambda: self._handle_macro_hotkey(self._task_equip_armor("mixed"), "F4"),
            HK_S_Q: lambda: self._handle_macro_hotkey(self._task_medbrew_burst(), "Shift+Q"),
            HK_S_E: lambda: self._handle_macro_hotkey(self._task_medbrew_hot_toggle(), None),
            HK_S_R: lambda: self._handle_macro_hotkey(self._task_tek_punch(), "Shift+R"),
        }

    def _on_hotkey_f1(self) -> None:
        self._toggle_overlay_visibility()

    def _on_hotkey_f7(self) -> None:
        self._request_recalibration()

    def _request_recalibration(self) -> None:
        self._prepare_recalibration_ui()
        self._recalibrate_event.set()

    def _pump_messages(self, msg) -> None:
        WM_HOTKEY = 0x0312
        while True:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0:
                break  # WM_QUIT
            if ret == -1:
                continue
            if msg.message == WM_HOTKEY:
                handler = self._hotkey_handlers.get(int(msg.wParam))
                if handler:
                    try:
                        handler()
                    except Exception:
                        pass
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    # --------------------------- Game detection ----------------------------
    def _is_ark_active(self) -> bool:
        """Return True if ArkAscended.exe is the foreground process (Windows only)."""
        if user32 is None or kernel32 is None:
            return False
        try:
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return False
            pid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
            if not hproc:
                return False
            try:
                buf_len = ctypes.wintypes.DWORD(260)
                while True:
                    buf = ctypes.create_unicode_buffer(buf_len.value)
                    ok = kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(buf_len))
                    if ok:
                        exe = os.path.basename(buf.value or "").lower()
                        return exe == "arkascended.exe"
                    # If buffer was too small, Windows sets required size; retry
                    needed = buf_len.value
                    if needed <= len(buf):
                        break
                    buf_len = ctypes.wintypes.DWORD(needed)
                return False
            finally:
                kernel32.CloseHandle(hproc)
        except Exception:
            return False

    # --------------------------- In-game macro handling ----------------------------
    def _handle_macro_hotkey(self, task_callable: Callable[[object, object], None], hotkey_label: Optional[str]) -> None:
        if not self._is_ark_active():
            # Silently ignore when Ark isn't the foreground window (no toast)
            return
        try:
            self.task_queue.put_nowait(task_callable)
            # Immediate success flash on the specific macro line (if provided)
            if hotkey_label and self.overlay and hasattr(self.overlay, "flash_hotkey_line"):
                try:
                    self.overlay.flash_hotkey_line(hotkey_label)
                except Exception:
                    pass
        except Exception:
            pass

    def _task_equip_armor(self, armor_set: str) -> Callable[[object, object], None]:
        def _job(vision_controller, input_controller):
            armor_swapper.execute(vision_controller, input_controller, armor_set)
        return _job

    def _task_medbrew_burst(self) -> Callable[[object, object], None]:
        def _job(_vision_controller, input_controller):
            combat.execute_medbrew_burst(input_controller)
        return _job

    def _task_medbrew_hot_toggle(self) -> Callable[[object, object], None]:
        # Separate handler to avoid identical implementation to burst
        def _job(_vision_controller, input_controller):
            # Pass overlay so the macro can hold the line green and fade after
            combat.execute_medbrew_hot_toggle(input_controller, self.overlay)
        return _job

    def _task_tek_punch(self) -> Callable[[object, object], None]:
        def _job(_vision_controller, input_controller):
            combat.execute_tek_punch(input_controller)
        return _job

    # --------------------------- Recalibration orchestration ----------------------------
    def _process_recalibration(self) -> None:
        if not self._recalibrate_event.is_set():
            return
        self._log("Recalibration requested")
        success = self.calibrate()
        if success and self.overlay and hasattr(self.overlay, "switch_to_main"):
            try:
                self.overlay.switch_to_main()
                self.overlay.set_status(self._menu_text())
                if hasattr(self.overlay, "show_success"):
                    self.overlay.show_success(self._MSG_CAL_DONE)
            except Exception:
                pass
        self._recalibrate_event.clear()

    # --------------------------- Calibration flow ----------------------------
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
            # Ensure UI is in calibration state
            self._ensure_calibration_ui()
            # 1) Capture keys
            keys = self._prompt_keys()
            if not keys:
                return False
            inv_key, tek_key = keys
            # Persist keys early
            self._save_keys(inv_key, tek_key)
            # 2) Capture template
            if self.overlay:
                self.overlay.set_status(
                    "Open your inventory, hover the search bar, then press F8 to capture."
                )
            tmpl_path = self._wait_and_capture_template()
            if not tmpl_path:
                if self.overlay:
                    self.overlay.set_status("Template capture cancelled or failed.")
                return False
            # 3) Finalize
            self._finalize_calibration(inv_key, tek_key, tmpl_path)
            return True
        except Exception as exc:  # pragma: no cover - environment dependent
            self._log(f"Calibration failed: {exc}")
            if self.overlay:
                self.overlay.set_status("Calibration failed: see logs")
            return False

    def _ensure_calibration_ui(self) -> None:
        if self.overlay and hasattr(self.overlay, "switch_to_calibration"):
            try:
                self.overlay.switch_to_calibration()
            except Exception:
                pass

    def _prompt_keys(self) -> Optional[Tuple[str, str]]:
        inv_key = self._prompt_until_valid("Press your Inventory key (keyboard or mouse)")
        if not inv_key:
            return None
        tek_key = self._prompt_until_valid(
            "Press your Tek Punch Cancel key (keyboard or mouse)"
        )
        if not tek_key:
            return None
        return inv_key, tek_key

    def _finalize_calibration(self, inv_key: str, tek_key: str, tmpl_path: Path) -> None:
        # Save template path and mark calibration complete
        self.config_manager.config["DEFAULT"]["search_bar_template"] = str(tmpl_path)
        self.config_manager.config["DEFAULT"]["calibration_complete"] = "True"
        self.config_manager.save()
        if self.overlay:
            self.overlay.set_status(
                f"Calibration saved: Inventory={inv_key}, TekCancel={tek_key}\nTemplate={tmpl_path}"
            )

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

        # Compute output path under per-user app data directory (same base as config.ini)
        # Example on Windows: %APPDATA%/Gangware/templates/search_bar.png
        base_dir = self.config_manager.config_path.parent
        out_dir = base_dir / "templates"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "search_bar.png"
        try:
            cv2.imwrite(str(out_path), bgr)
            return out_path
        except Exception:
            return None

    # --------------------------- Keyboard capture helpers ----------------------------
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
                self._log(self._MSG_EXIT)
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

    # --------------------------- External API ----------------------------
    def request_recalibration(self) -> None:
        """External trigger (e.g., GUI) to request recalibration on the hotkey thread."""
        # Ensure the calibration gate is open even if we're pre-start
        try:
            self._calibration_gate.set()
        except Exception:
            pass
        # Prepare the UI for user guidance
        self._prepare_recalibration_ui()
        self._recalibrate_event.set()

    def allow_calibration_start(self) -> None:
        """Allow the calibration to start by setting the gate event."""
        try:
            self._calibration_gate.set()
        except Exception:
            pass

    # --------------------------- Persistence & logging ----------------------------
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

    # --------------------------- UI helpers ----------------------------
    def _prepare_recalibration_ui(self) -> None:
        """Ensure the overlay is visible and switched to calibration with guidance text."""
        try:
            if self.overlay:
                if hasattr(self.overlay, "set_visible"):
                    self.overlay.set_visible(True)
                if hasattr(self.overlay, "switch_to_calibration"):
                    self.overlay.switch_to_calibration()
                self.overlay.set_status("Recalibration requested — follow on-screen prompts.")
        except Exception:
            pass

    def _menu_text(self) -> str:
        """Return the menu content listing categorized controls and hotkeys."""
        return (
            "Overlay Controls\n"
            "\n"
            "- F1: Hide/Unhide Overlay\n"
            "- F10: Exit the Application\n"
            "\n"
            "Macro Hotkeys (Ark window only)\n"
            "\n"
            "- F2: Equip Flak Armor\n"
            "- F3: Equip Tek Armor\n"
            "- F4: Equip Mixed Armor\n"
            "- Shift+Q: Medbrew Burst\n"
            "- Shift+E: Medbrew Heal-over-Time (Toggle)\n"
            "- Shift+R: Tek Punch\n"
            "\n"
            "Calibration Keys\n"
            "\n"
            "- F7: Start or restart Calibration Mode.\n"
            "- F8: The \"capture\" key, used during setup.\n"
        )
