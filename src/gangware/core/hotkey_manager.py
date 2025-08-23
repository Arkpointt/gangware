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
  - Global: F1 toggles overlay, F7 starts/captures calibration, F9 stops calibration, F10 exit
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

import mss  # type: ignore
import numpy as np  # type: ignore
from ..controllers.armor_matcher import ArmorMatcher
from ..features.debug.keys import capture_input_windows, wait_key_release
from ..features.debug.template import wait_and_capture_template

import ctypes
import logging

# Macro libraries
from ..macros import armor_swapper, combat

if sys.platform == "win32":
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

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

    HOTKEY_SHIFT_E = "Shift+E"
    HOTKEY_SHIFT_R = "Shift+R"

    def __init__(self, config_manager, task_queue, state_manager, input_controller=None, overlay=None):
        super().__init__(daemon=True)
        self.config_manager = config_manager
        self.task_queue = task_queue
        self.state_manager = state_manager
        self.input_controller = input_controller
        self.overlay = overlay
        # Tek Dash timing constants
        self._TEK_DASH_EST_DURATION = 0.9  # seconds
        self._TEK_DASH_INPUT_WINDOW = 0.2  # seconds before expected end
        # Medbrew HOT thread state
        self._hot_thread: Optional[threading.Thread] = None
        self._hot_stop_event = threading.Event()
        self._recalibrate_event = threading.Event()
        self._f1_down = False  # debounce for F1 toggle (polling fallback)
        self._f7_down = False  # debounce for F7 recalibration (polling fallback)
        self._calibration_gate = threading.Event()
        # Common messages
        self._MSG_EXIT = "F10 pressed — exiting application"
        self._MSG_CAL_DONE = "Calibration complete"
        self._MSG_MENU = "Main menu — overlay ready. Use F2/F3/F4 and Shift+Q/E/R in-game. F1 toggles overlay; F7 recalibrates."
        # Hotkey handler registry (id -> callable)
        self._hotkey_handlers: Dict[int, Callable[[], None]] = {}
        # Track whether global registration succeeded for F1 and F7 to suppress polling
        self._has_reg_f1 = False
        self._has_reg_f7 = False
        # Manual ROI capture state (first corner from F6 or None)
        self._roi_first_corner: Optional[Tuple[int, int]] = None
        # Try to start a global hotkey message loop for robust handling
        self._start_hotkey_hook()
        # Lazy-initialized armor matcher
        self._armor_matcher: Optional[ArmorMatcher] = None
        # Preload persisted ROI into environment so VisionController honors it
        try:
            _roi_str = str(self.config_manager.get("vision_roi", fallback="")).strip()
            if _roi_str:
                # If this is legacy absolute (no decimals), convert once to relative using current monitor
                if ',' in _roi_str and not _roi_str.count('.') >= 3:
                    monitor_bounds = self._get_current_monitor_bounds()
                    rel_roi = self._absolute_to_relative_roi(_roi_str, monitor_bounds)
                    if rel_roi:
                        self.config_manager.config["DEFAULT"]["vision_roi"] = rel_roi
                        try:
                            self.config_manager.save()
                        except Exception:
                            pass
                        _roi_str = rel_roi
                        logging.getLogger(__name__).info("startup: converted absolute ROI to relative: %s", rel_roi)

                # Defer absolute application to feature start.
                # Avoid mapping ROI at startup to prevent misalignment when Ark is not foreground.
                if _roi_str and "GW_VISION_ROI" not in os.environ:
                    logging.getLogger(__name__).info("startup: deferred ROI application until feature start")

            # Prefill ROI status in overlay if available (show absolute if applied)
            if _roi_str and self.overlay and hasattr(self.overlay, "set_roi_status"):
                try:
                    abs_roi = os.environ.get("GW_VISION_ROI", "")
                    self.overlay.set_roi_status(bool(abs_roi), abs_roi)
                except Exception:
                    pass
        except Exception:
            pass
        # Initialize Tek Dash state flags
        try:
            self.state_manager.set('tek_dash_busy', False)
            self.state_manager.set('tek_dash_buffer', False)
            self.state_manager.set('tek_dash_started_at', 0.0)
            self.state_manager.set('tek_dash_est_duration', self._TEK_DASH_EST_DURATION)
            self.state_manager.set('tek_dash_last_press_at', 0.0)
        except Exception:
            pass
        # Wire overlay calibration panel events if available
        try:
            if self.overlay:
                if hasattr(self.overlay, "on_capture_inventory"):
                    self.overlay.on_capture_inventory(lambda: self._ui_capture_key("inventory_key", "Press your Inventory key (keyboard or mouse)", is_tek=False))
                if hasattr(self.overlay, "on_capture_tek"):
                    self.overlay.on_capture_tek(lambda: self._ui_capture_key("tek_punch_cancel_key", "Press your Tek Punch Cancel key (keyboard or mouse)", is_tek=True))
                if hasattr(self.overlay, "on_capture_template"):
                    self.overlay.on_capture_template(self._ui_capture_template)
                if hasattr(self.overlay, "on_capture_roi"):
                    # Show a short tip: F6 twice to set top-left and bottom-right
                    self.overlay.on_capture_roi(lambda: self._tip_roi_capture())
                # Start button should open the calibration gate
                if hasattr(self.overlay, "on_start"):
                    self.overlay.on_start(self.allow_calibration_start)
                # Overlay recalibration (F7 or button) should trigger the flow
                if hasattr(self.overlay, "on_recalibrate"):
                    self.overlay.on_recalibrate(self.request_recalibration)

        except Exception:
            pass
        # End of init
        # Log system environment on startup for troubleshooting
        self._log_system_environment()

    def _get_current_monitor_bounds(self) -> dict:
        """Get the bounds of the monitor containing the mouse cursor."""
        try:
            import mss
            cursor_x, cursor_y = _cursor_pos()
            with mss.mss() as sct:
                # Find which monitor contains the cursor
                for i, monitor in enumerate(sct.monitors[1:], 1):  # Skip virtual screen (index 0)
                    if (monitor['left'] <= cursor_x < monitor['left'] + monitor['width'] and
                        monitor['top'] <= cursor_y < monitor['top'] + monitor['height']):
                        return monitor
                # Fallback to primary monitor if cursor not found in any monitor
                if len(sct.monitors) > 1:
                    return sct.monitors[1]
                else:
                    return sct.monitors[0]
        except Exception:
            # Fallback to virtual screen
            try:
                import mss
                with mss.mss() as sct:
                    return sct.monitors[0]
            except Exception:
                # Ultimate fallback
                return {'left': 0, 'top': 0, 'width': 1920, 'height': 1080}

    def _relative_to_absolute_roi(self, rel_str: str, monitor_bounds: Optional[dict] = None) -> str:
        """Convert relative ROI (percentages) to absolute pixels.

        Format: 'rel_x,rel_y,rel_w,rel_h' -> 'abs_x,abs_y,abs_w,abs_h'
        """
        try:
            if not rel_str.strip():
                return ""

            if monitor_bounds is None:
                monitor_bounds = self._get_current_monitor_bounds()

            parts = [float(p.strip()) for p in rel_str.split(',')]
            if len(parts) != 4:
                return ""

            rel_x, rel_y, rel_w, rel_h = parts

            # Convert relative (0.0-1.0) to absolute pixels
            abs_x = int(monitor_bounds['left'] + rel_x * monitor_bounds['width'])
            abs_y = int(monitor_bounds['top'] + rel_y * monitor_bounds['height'])
            abs_w = int(rel_w * monitor_bounds['width'])
            abs_h = int(rel_h * monitor_bounds['height'])

            return f"{abs_x},{abs_y},{abs_w},{abs_h}"
        except Exception:
            return ""

    def _absolute_to_relative_roi(self, abs_str: str, monitor_bounds: Optional[dict] = None) -> str:
        """Convert absolute ROI (pixels) to relative (percentages).

        Format: 'abs_x,abs_y,abs_w,abs_h' -> 'rel_x,rel_y,rel_w,rel_h'
        """
        try:
            if not abs_str.strip():
                return ""

            if monitor_bounds is None:
                monitor_bounds = self._get_current_monitor_bounds()

            parts = [int(p.strip()) for p in abs_str.split(',')]
            if len(parts) != 4:
                return ""

            abs_x, abs_y, abs_w, abs_h = parts

            # Convert absolute pixels to relative (0.0-1.0)
            rel_x = (abs_x - monitor_bounds['left']) / monitor_bounds['width']
            rel_y = (abs_y - monitor_bounds['top']) / monitor_bounds['height']
            rel_w = abs_w / monitor_bounds['width']
            rel_h = abs_h / monitor_bounds['height']

            # Clamp to valid range
            rel_x = max(0.0, min(1.0, rel_x))
            rel_y = max(0.0, min(1.0, rel_y))
            rel_w = max(0.0, min(1.0, rel_w))
            rel_h = max(0.0, min(1.0, rel_h))

            return f"{rel_x:.6f},{rel_y:.6f},{rel_w:.6f},{rel_h:.6f}"
        except Exception:
            return ""

    def _log_system_environment(self) -> None:
        """Log monitor geometry and other system info for troubleshooting."""
        logger = logging.getLogger(__name__)
        try:
            # Report monitor geometry
            mon_info = {}
            try:
                import mss
                with mss.mss() as sct:
                    mons = sct.monitors
                    for i, m in enumerate(mons):
                        mon_info[i] = {k: int(m.get(k, 0)) for k in ("left", "top", "width", "height")}
            except Exception:
                pass
            logger.info("startup: monitors=%s", mon_info)

            # Report ROI info (both relative and absolute)
            rel_roi = str(self.config_manager.get("vision_roi", fallback="")).strip()
            abs_roi = os.environ.get('GW_VISION_ROI', '').strip()
            if rel_roi:
                logger.info("startup: relative_roi=%s", rel_roi)
            if abs_roi:
                logger.info("startup: absolute_roi=%s", abs_roi)
        except Exception:
            pass

    # --------------------------- Thread entry ----------------------------

    def _get_foreground_rect(self) -> tuple[int, int, int, int] | None:
        try:
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None
            rc = RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rc)):
                return None
            return int(rc.left), int(rc.top), int(rc.right), int(rc.bottom)
        except Exception:
            return None

    def _get_virtual_screen_rect(self) -> tuple[int, int, int, int] | None:
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

    def _get_ark_window_rect_by_proc(self) -> tuple[int, int, int, int] | None:
        """Find Ark window by enumerating windows and matching the process image name.

        Returns the window rect even if Ark is not the foreground window.
        """
        try:
            target_exe = "arkascended.exe"
            found_hwnd = wintypes.HWND()

            @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            def _enum_proc(hwnd, lparam):
                try:
                    # Skip invisible/minimized windows
                    if not user32.IsWindowVisible(hwnd):
                        return True
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                    hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
                    if not hproc:
                        return True
                    try:
                        buf_len = wintypes.DWORD(260)
                        while True:
                            buf = ctypes.create_unicode_buffer(buf_len.value)
                            ok = kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(buf_len))
                            if ok:
                                exe = os.path.basename(buf.value or "").lower()
                                if exe == target_exe:
                                    found_hwnd.value = hwnd
                                    return False
                                break
                            needed = buf_len.value
                            if needed <= len(buf):
                                break
                            buf_len = wintypes.DWORD(needed)
                    finally:
                        kernel32.CloseHandle(hproc)
                except Exception:
                    return True
                return True

            user32.EnumWindows(_enum_proc, 0)
            if not found_hwnd.value:
                return None
            rc = RECT()
            if not user32.GetWindowRect(found_hwnd, ctypes.byref(rc)):
                return None
            return int(rc.left), int(rc.top), int(rc.right), int(rc.bottom)
        except Exception:
            return None

    def _get_ark_window_rect_by_title(self) -> tuple[int, int, int, int] | None:
        """Find Ark window by title substring (case-insensitive) and return its rect."""
        try:
            target = "arkascended"
            found_hwnd = wintypes.HWND()

            @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            def _enum_proc(hwnd, lparam):
                # Skip invisible windows
                try:
                    if not user32.IsWindowVisible(hwnd):
                        return True
                except Exception:
                    pass
                # Get title
                try:
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length <= 0:
                        return True
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = (buf.value or "").lower()
                except Exception:
                    title = ""
                if target in title:
                    found_hwnd.value = hwnd
                    return False  # stop enumeration
                return True

            user32.EnumWindows(_enum_proc, 0)
            if not found_hwnd.value:
                return None
            rc = RECT()
            if not user32.GetWindowRect(found_hwnd, ctypes.byref(rc)):
                return None
            return int(rc.left), int(rc.top), int(rc.right), int(rc.bottom)
        except Exception:
            return None

    def _ensure_ark_foreground(self, timeout: float = 3.0) -> bool:
        """Try to make ArkAscended.exe the foreground window within timeout.

        Returns True if Ark becomes foreground; False otherwise.
        """
        if user32 is None or kernel32 is None:
            return False
        import time as _t
        end = _t.time() + max(0.0, float(timeout))
        SW_RESTORE = 9

        def _find_hwnd_by_proc() -> wintypes.HWND | None:
            target_exe = "arkascended.exe"
            found_hwnd = wintypes.HWND()

            @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            def _enum_proc(hwnd, lparam):
                try:
                    if not user32.IsWindowVisible(hwnd):
                        return True
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                    hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
                    if not hproc:
                        return True
                    try:
                        buf_len = wintypes.DWORD(260)
                        while True:
                            buf = ctypes.create_unicode_buffer(buf_len.value)
                            ok = kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(buf_len))
                            if ok:
                                exe = os.path.basename(buf.value or "").lower()
                                if exe == target_exe:
                                    found_hwnd.value = hwnd
                                    return False
                                break
                            needed = buf_len.value
                            if needed <= len(buf):
                                break
                            buf_len = wintypes.DWORD(needed)
                    finally:
                        kernel32.CloseHandle(hproc)
                except Exception:
                    return True
                return True

            user32.EnumWindows(_enum_proc, 0)
            return found_hwnd if found_hwnd.value else None

        # If already foreground, done
        try:
            if self._is_ark_active():
                return True
        except Exception:
            pass

        while _t.time() < end:
            hwnd = _find_hwnd_by_proc()
            if hwnd and hwnd.value:
                try:
                    user32.ShowWindow(hwnd, SW_RESTORE)
                except Exception:
                    pass
                try:
                    user32.SetForegroundWindow(hwnd)
                except Exception:
                    pass
                # Confirm
                try:
                    if self._is_ark_active():
                        return True
                except Exception:
                    pass
            _t.sleep(0.1)
        return False

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
                    # Prefill GUI with retained values so they remain visible
                    self._prefill_overlay_panel()
                    self.overlay.set_status("Calibration complete. Application ready for use.")
                except Exception:
                    pass
            return

        # Show calibration panel and process until ready
        self._show_calibration_menu("Calibration menu — use the buttons to capture each item, then click Start.")
        self._run_cal_menu_until_start_and_ready()

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
            # Normal recalibration UI flow
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
            # Always attempt to unregister known IDs 1..11
            for i in range(1, 12):
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
        HK_F6 = 10
        HK_F9 = 11
        HK_F11 = 12

        # Modifiers / VKs
        MOD_NONE = 0x0000
        MOD_SHIFT = 0x0004
        VK_F1, VK_F2, VK_F3, VK_F4 = 0x70, 0x71, 0x72, 0x73
        VK_F6, VK_F7, VK_F9, VK_F10 = 0x75, 0x76, 0x78, 0x79
        VK_F11 = 0x7A
        VK_Q, VK_E, VK_R = 0x51, 0x45, 0x52

        # Register global hotkeys via helper
        self._has_reg_f7 = self._reg_hotkey(HK_F7, MOD_NONE, VK_F7, "F7")
        self._reg_hotkey(HK_F9, MOD_NONE, VK_F9, "F9")
        self._reg_hotkey(HK_F10, MOD_NONE, VK_F10, "F10")
        self._has_reg_f1 = self._reg_hotkey(HK_F1, MOD_NONE, VK_F1, "F1")
        # F11 is available for future use
        self._reg_hotkey(HK_F11, MOD_NONE, VK_F11, "F11")
        # Manual ROI capture (global)
        self._reg_hotkey(HK_F6, MOD_NONE, VK_F6, "F6")

        # Register game-specific hotkeys via data-driven loop
        for id_, mod, vk, name in [
            (HK_F2, MOD_NONE, VK_F2, "F2"),
            (HK_F3, MOD_NONE, VK_F3, "F3"),
            (HK_F4, MOD_NONE, VK_F4, "F4"),
            (HK_S_Q, MOD_SHIFT, VK_Q, "Shift+Q"),
            (HK_S_E, MOD_SHIFT, VK_E, self.HOTKEY_SHIFT_E),
            (HK_S_R, MOD_SHIFT, VK_R, self.HOTKEY_SHIFT_R),
        ]:
            self._reg_hotkey(id_, mod, vk, name)

        # Map IDs to handlers
        self._hotkey_handlers = self._build_hotkey_handlers(
            HK_F1, HK_F7, HK_F9, HK_F10, HK_F2, HK_F3, HK_F4, HK_S_Q, HK_S_E, HK_S_R, HK_F6, HK_F11
        )

    def _reg_hotkey(self, id_: int, mod: int, vk: int, name: str) -> bool:
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

    def _build_hotkey_handlers(
        self,
        hk_f1: int,
        hk_f7: int,
        hk_f9: int,
        hk_f10: int,
        hk_f2: int,
        hk_f3: int,
        hk_f4: int,
        hk_s_q: int,
        hk_s_e: int,
        hk_s_r: int,
        hk_f6: int,
        hk_f11: int,
    ) -> Dict[int, Callable[[], None]]:
        return {
            hk_f1: self._on_hotkey_f1,
            hk_f7: self._on_hotkey_f7,
            hk_f9: self._on_hotkey_f9,
            hk_f10: self._maybe_exit_on_f10,
            hk_f2: lambda: self._handle_macro_hotkey(self._task_equip_flak_fullset(), "F2"),
            hk_f3: lambda: self._handle_macro_hotkey(self._task_equip_tek_fullset(), "F3"),
            hk_f4: lambda: self._handle_macro_hotkey(self._task_equip_mixed_fullset(), "F4"),
            hk_s_q: lambda: self._handle_macro_hotkey(self._task_medbrew_burst(), "Shift+Q"),
            hk_s_e: self._on_hotkey_shift_e,
            hk_s_r: self._on_hotkey_shift_r,
            hk_f6: self._on_hotkey_f6,
            hk_f11: self._on_hotkey_f11,
        }

    def _on_hotkey_f1(self) -> None:
        self._toggle_overlay_visibility()

    def _on_hotkey_f7(self) -> None:
        """Trigger recalibration when F7 is pressed."""
        try:
            self._recalibrate_event.set()
        except Exception:
            pass

    def _on_hotkey_f11(self) -> None:
        """F11 hotkey handler - currently disabled."""
        pass

    def _on_hotkey_f9(self) -> None:
        """F9 hotkey handler - currently disabled."""
        pass

    def _on_hotkey_f6(self) -> None:
        """Two-press manual ROI capture (F6): first press stores top-left, second sets bottom-right.

        Saves relative ROI as percentages and persists under config key 'vision_roi'.
        Sets absolute ROI in GW_VISION_ROI for current session.
        """
        if user32 is None:
            return
        try:
            x, y = _cursor_pos()
        except Exception:
            return
        # First press
        if self._roi_first_corner is None:
            self._roi_first_corner = (x, y)
            if self.overlay:
                try:
                    self.overlay.set_status("ROI: first corner saved. Move to bottom-right and press F6 again.")
                    if hasattr(self.overlay, "set_roi_status"):
                        # Mark as pending while capturing
                        self.overlay.set_roi_status(False)
                except Exception:
                    pass
            return
        # Second press
        x1, y1 = self._roi_first_corner
        self._roi_first_corner = None
        left = min(x1, x)
        top = min(y1, y)
        width = abs(x - x1)
        height = abs(y - y1)
        if width < 8 or height < 8:
            if self.overlay:
                try:
                    self.overlay.set_status("ROI too small — press F6 twice again.")
                except Exception:
                    pass
            return

        # Get monitor bounds for the selected ROI
        monitor_bounds = self._get_current_monitor_bounds()

        # Clamp to monitor bounds
        left = max(monitor_bounds["left"], min(left, monitor_bounds["left"] + monitor_bounds["width"] - width))
        top = max(monitor_bounds["top"], min(top, monitor_bounds["top"] + monitor_bounds["height"] - height))

        # Create absolute ROI string for current session
        abs_roi_str = f"{int(left)},{int(top)},{int(width)},{int(height)}"
        os.environ["GW_VISION_ROI"] = abs_roi_str

        # Convert to relative coordinates for storage
        rel_roi_str = self._absolute_to_relative_roi(abs_roi_str, monitor_bounds)

        # Persist relative coordinates in config
        try:
            self.config_manager.config["DEFAULT"]["vision_roi"] = rel_roi_str
            self.config_manager.save()
            logging.getLogger(__name__).info("F6: saved relative ROI: %s (absolute: %s)", rel_roi_str, abs_roi_str)
        except Exception:
            pass

        # Save a snapshot image of the selected ROI for user confirmation
        snapshot_path_str = None
        try:
            with mss.mss() as sct:
                region = {"left": int(left), "top": int(top), "width": int(width), "height": int(height)}
                grabbed = sct.grab(region)
                bgr = np.array(grabbed)[:, :, :3]  # drop alpha
            base_dir = self.config_manager.config_path.parent
            out_dir = base_dir / "templates"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / "roi.png"
            try:
                import cv2  # ensure available in this scope
                cv2.imwrite(str(out_path), bgr)
                snapshot_path_str = str(out_path)
            except Exception:
                snapshot_path_str = None
        except Exception:
            snapshot_path_str = None
        if self.overlay:
            try:
                if snapshot_path_str:
                    self.overlay.set_status(
                        f"ROI set to {width}x{height} at ({left},{top}) [Relative: {rel_roi_str[:20]}...]. Saved snapshot: {snapshot_path_str}. F6 twice to change."
                    )
                else:
                    self.overlay.set_status(
                        f"ROI set to {width}x{height} at ({left},{top}) [Relative]. (Snapshot save failed.) F6 twice to change."
                    )
                if hasattr(self.overlay, "set_roi_status"):
                    # Show absolute coordinates in overlay for user reference
                    self.overlay.set_roi_status(True, abs_roi_str)
            except Exception:
                pass

    def _tip_roi_capture(self) -> None:
        if self.overlay and hasattr(self.overlay, "set_status"):
            try:
                self.overlay.set_status("ROI capture: move to top-left and press F6, then bottom-right and press F6.")
            except Exception:
                pass

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
            exe = self._foreground_executable_name()
            return exe == "arkascended.exe"
        except Exception:
            return False

    def _foreground_executable_name(self) -> str:
        """Return the lowercase executable name of the foreground process on Windows."""
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not hproc:
            return ""
        try:
            buf_len = wintypes.DWORD(260)
            while True:
                buf = ctypes.create_unicode_buffer(buf_len.value)
                ok = kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(buf_len))
                if ok:
                    return os.path.basename(buf.value or "").lower()
                needed = buf_len.value
                if needed <= len(buf):
                    break
                buf_len = wintypes.DWORD(needed)
            return ""
        finally:
            kernel32.CloseHandle(hproc)

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

    def _on_hotkey_shift_e(self) -> None:
        """Toggle Medbrew Heal-over-Time in a dedicated background thread."""
        if not self._is_ark_active():
            return
        # If already running, request stop
        t = getattr(self, "_hot_thread", None)
        if t is not None and t.is_alive():
            try:
                self._hot_stop_event.set()
            except Exception:
                pass
            return
        # Otherwise, start a new HOT thread
        self._start_hot_thread()

    def _start_hot_thread(self) -> None:
        if self.input_controller is None:
            return
        try:
            self._hot_stop_event.clear()
        except Exception:
            pass
        # Mark line active in overlay
        try:
            if self.overlay and hasattr(self.overlay, "set_hotkey_line_active"):
                self.overlay.set_hotkey_line_active(self.HOTKEY_SHIFT_E)
        except Exception:
            pass
        start_time = time.perf_counter()
        t = threading.Thread(target=self._hot_thread_loop, args=(start_time,), daemon=True)
        self._hot_thread = t
        try:
            t.start()
        except Exception:
            pass

    def _hot_thread_loop(self, start: float) -> None:
        total_duration = 22.5
        interval = 1.5
        presses = int(total_duration / interval) + 1
        try:
            for i in range(presses):
                if self._hot_stop_event.is_set():
                    break
                target = start + i * interval
                self._hot_wait_until(target)
                if self._hot_stop_event.is_set():
                    break
                try:
                    if self.input_controller:
                        self.input_controller.press_key('0', presses=1)
                except Exception:
                    pass
        finally:
            self._hot_on_finish()

    def _hot_wait_until(self, deadline: float) -> None:
        import time as _t
        while not self._hot_stop_event.is_set():
            now = _t.perf_counter()
            remain = deadline - now
            if remain <= 0:
                break
            _t.sleep(min(0.05, remain))

    def _hot_on_finish(self) -> None:
        # Clear active line with smooth fade animation
        try:
            if self.overlay and hasattr(self.overlay, "clear_hotkey_line_active"):
                self.overlay.clear_hotkey_line_active(self.HOTKEY_SHIFT_E, fade_duration_ms=2400)
        except Exception:
            pass

    def _on_hotkey_shift_r(self) -> None:
        """Tek Dash input window buffering: only buffer within last 200ms of current run."""
        if not self._is_ark_active():
            return

        self._record_tek_dash_press_timestamp()
        busy = self._get_tek_dash_busy_state()
        pending = self._is_task_pending(lambda t: self._is_tek_punch_task(t))

        if not busy and not pending:
            self._start_new_tek_dash()

    def _record_tek_dash_press_timestamp(self) -> None:
        """Record the timestamp of the tek dash key press for input window evaluation."""
        try:
            import time as _t
            self.state_manager.set('tek_dash_last_press_at', _t.perf_counter())
        except Exception:
            pass

    def _get_tek_dash_busy_state(self) -> bool:
        """Get the current busy state of tek dash, defaulting to False on error."""
        try:
            return bool(self.state_manager.get('tek_dash_busy', False))
        except Exception:
            return False

    def _start_new_tek_dash(self) -> None:
        """Initialize state and queue a new tek dash task."""
        self._initialize_tek_dash_state()
        self._queue_tek_dash_task()

    def _initialize_tek_dash_state(self) -> None:
        """Set up the state manager for a new tek dash."""
        try:
            self.state_manager.set('tek_dash_busy', True)
            self.state_manager.set('tek_dash_buffer', False)
            self.state_manager.set('tek_dash_started_at', 0.0)
            self.state_manager.set('tek_dash_est_duration', self._TEK_DASH_EST_DURATION)
        except Exception:
            pass

    def _queue_tek_dash_task(self) -> None:
        """Queue the tek punch task and flash the overlay if available."""
        try:
            self.task_queue.put_nowait(self._task_tek_punch())
            self._flash_tek_dash_overlay()
        except Exception:
            pass

    def _flash_tek_dash_overlay(self) -> None:
        """Flash the hotkey line in the overlay for tek dash feedback."""
        if self.overlay and hasattr(self.overlay, "flash_hotkey_line"):
            try:
                self.overlay.flash_hotkey_line(self.HOTKEY_SHIFT_R)
            except Exception:
                pass

    def _is_task_pending(self, predicate: Callable[[object], bool]) -> bool:
        """Check if any queued task matches predicate, thread-safely if possible."""
        q = getattr(self, "task_queue", None)
        if q is None:
            return False
        try:
            queue_attr = getattr(q, "queue", None)
            mutex = getattr(q, "mutex", None)
            if queue_attr is None or mutex is None:
                try:
                    items = list(q.queue)  # type: ignore[attr-defined]
                except Exception:
                    return False
                return any(predicate(item) for item in items)
            mutex.acquire()
            try:
                return any(predicate(item) for item in queue_attr)
            finally:
                mutex.release()
        except Exception:
            return False

    @staticmethod
    def _is_tek_punch_task(task_obj: object) -> bool:
        try:
            if callable(task_obj) and getattr(task_obj, "_gw_task_id", "") == "tek_punch":
                return True
            if isinstance(task_obj, dict):
                label = str(task_obj.get("label", "")).lower()
                name = str(task_obj.get("name", "")).lower()
                if "tek" in label and "punch" in label:
                    return True
                if "tek" in name and "punch" in name:
                    return True
        except Exception:
            pass
        return False

    def _task_equip_armor(self, armor_set: str) -> Callable[[object, object], None]:
        def _job(vision_controller, input_controller):
            armor_swapper.execute(vision_controller, input_controller, armor_set)
        return _job

    def _task_medbrew_burst(self) -> Callable[[object, object], None]:
        def _job(_vision_controller, input_controller):
            combat.execute_medbrew_burst(input_controller)
        return _job

    def _task_medbrew_hot_toggle(self) -> Callable[[object, object], None]:
        # Legacy path preserved but not used; HOT now runs in its own thread
        def _job(_vision_controller, input_controller):
            combat.execute_medbrew_hot_toggle(input_controller, self.overlay)
        return _job

    def _task_tek_punch(self) -> Callable[[object, object], None]:
        def _job(_vision_controller, input_controller):
            # Pass config manager so macro can read tek_punch_cancel_key
            combat.execute_tek_punch(input_controller, self.config_manager)
        try:
            setattr(_job, "_gw_task_id", "tek_punch")
        except Exception:
            pass
        return _job

    # --------------------------- Recalibration orchestration ----------------------------
    def _process_recalibration(self) -> None:
        """Handle recalibration request by showing menu and running calibration flow."""
        if not self._recalibrate_event.is_set():
            return
        self._log("Recalibration requested")
        self._show_calibration_menu("Calibration menu — use the buttons to capture each item, then click Start.")
        self._run_cal_menu_until_start_and_ready()
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
            # Debounce F7 release before starting capture to avoid capturing F7 itself
            try:
                wait_key_release(0x76, 0.8)
            except Exception:
                pass
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
            tmpl_path = wait_and_capture_template(self.config_manager, self.overlay)
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

    # --------------------------- Keyboard capture helpers ----------------------------

    def _prompt_until_valid(self, prompt: str) -> Optional[str]:
        """Prompt the user repeatedly until a non-restart value is captured.

        Returns the captured token, or None on unrecoverable failure.
        """
        while True:
            token = capture_input_windows(prompt, self.overlay)
            if not token:
                return None
            if token == "__restart__":
                continue
            return token

    # --------------------------- External API ----------------------------
    def request_recalibration(self) -> None:
        """External trigger (e.g., GUI) to request recalibration on the hotkey thread."""
        # Ensure the calibration gate is open during pre-start phase
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

    def _save_key(self, name: str, value: str) -> None:
        try:
            self.config_manager.config["DEFAULT"][name] = str(value)
            self.config_manager.save()
        except Exception:
            pass

    # --------------------------- Calibration menu helpers ----------------------------
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
        if not self.overlay:
            return
        try:
            if hasattr(self.overlay, "set_visible"):
                self.overlay.set_visible(True)
            if hasattr(self.overlay, "switch_to_calibration"):
                self.overlay.switch_to_calibration()
            self._prefill_overlay_panel()
            if status:
                self.overlay.set_status(status)
        except Exception:
            pass

    def _is_calibration_ready(self) -> bool:
        inv = self.config_manager.get("inventory_key")
        tek = self.config_manager.get("tek_punch_cancel_key")
        tmpl = self.config_manager.get("search_bar_template")
        return bool(inv and tek and tmpl)

    def _menu_text(self):
        """
        Return the main menu text.
        """
        return self._MSG_MENU

    # --------------------------- Utility: resolve config tokens ----------------------------
    @staticmethod
    def _get_token(config_manager, key_name: str, default_token: str) -> str:
        """Return a normalized token like 'key_i' or 'mouse_xbutton2'.

        If an old plain key like 'i' is stored, normalize to 'key_i'.
        """
        try:
            token = None
            if config_manager is not None:
                token = config_manager.get(key_name)
            if not token:
                return default_token
            t = str(token).strip().lower()
            if t.startswith('key_') or t.startswith('mouse_'):
                return t
            # Back-compat: raw key like 'i'
            if len(t) > 0:
                return f"key_{t}"
            return default_token
        except Exception:
            return default_token

    @staticmethod
    def _token_display(token: str) -> str:
        """Human-friendly label for overlay messages."""
        t = (token or '').lower()
        if t.startswith('key_'):
            name = t[4:]
            return name.upper()
        if t == 'mouse_xbutton1':
            return 'XBUTTON1'
        if t == 'mouse_xbutton2':
            return 'XBUTTON2'
        if t == 'mouse_middle':
            return 'MIDDLE'
        if t == 'mouse_right':
            return 'RIGHT'
        if t == 'mouse_left':
            return 'LEFT'
        return t.upper() or 'UNKNOWN'

    # --------------------------- Macro: search and type ----------------------------
    def _task_search_and_type(self, text: str) -> Callable[[object, object], None]:
        def _job(vision_controller, input_controller):
            import time as _t
            import random as _rand
            corr = f"f2-{int(_t.time())}-{_rand.randint(1000,9999)}"
            logger = logging.getLogger(__name__)
            try:
                # 1) Open inventory using configured token (keyboard or mouse)
                inv_token = self._get_token(self.config_manager, 'inventory_key', 'key_i')
                t_phase = _t.perf_counter()
                try:
                    if self.overlay:
                        self.overlay.set_status(f"Opening inventory with {self._token_display(inv_token)}...")
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
                # Give the game UI time to open
                try:
                    time.sleep(0.25)
                except Exception:
                    pass
                try:
                    logger.info("macro=F2 phase=open_inventory corr=%s duration_ms=%.1f", corr, (_t.perf_counter() - t_phase) * 1000.0)
                except Exception:
                    pass

                # 2) Locate the saved template path
                tmpl = self.config_manager.get('search_bar_template')
                if not tmpl:
                    self._log('Search bar template not set. Use F8 on Calibration page.')
                    return
                # F6 ROI constraints are bypassed for search-bar detection to ensure visibility.
                # This ROI will be applied later as an inventory sub-region for item matching.
                _abs_roi_env = os.environ.get('GW_VISION_ROI', '').strip()
                # Retry search with gradually relaxed confidence; re-open inventory if needed
                coords = None
                for attempt in range(5):
                    # Gradually relax confidence from 0.70 down to 0.50
                    conf = max(0.50, 0.70 - 0.03 * attempt)
                    try:
                        if self.overlay:
                            self.overlay.set_status(f"Finding search bar… attempt {attempt+1}/8 (conf>={conf:.2f})")
                    except Exception:
                        pass
                    try:
                        # Disable ROI constraints for full-window template search
                        _prev_abs = None
                        if _abs_roi_env:
                            try:
                                _prev_abs = os.environ.pop('GW_VISION_ROI', None)
                            except Exception:
                                _prev_abs = None
                        # Constrain search to a band above the inventory area (from F6 ROI or existing inventory ROI)
                        band = None
                        try:
                            inv_hint = None
                            if _abs_roi_env:
                                parts = [int(p.strip()) for p in _abs_roi_env.split(',')]
                                if len(parts) == 4:
                                    inv_hint = { 'left': parts[0], 'top': parts[1], 'width': parts[2], 'height': parts[3] }
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
                                band = { 'left': int(band_left), 'top': int(band_top), 'width': int(band_w), 'height': int(band_h) }
                        except Exception:
                            band = None
                        prev_manual_roi = getattr(vision_controller, 'search_roi', None)
                        try:
                            if band is not None and hasattr(vision_controller, 'set_search_roi'):
                                vision_controller.set_search_roi(band)
                            # Force fast-only search to reduce latency for search-bar detection
                            _prev_fast = os.environ.get('GW_VISION_FAST_ONLY')
                            try:
                                os.environ['GW_VISION_FAST_ONLY'] = '1'
                                coords = vision_controller.find_template(str(tmpl), confidence=conf)
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
                    except Exception as e:
                        logger.exception("macro=F2 phase=find_bar corr=%s attempt=%d error=%s", corr, attempt + 1, str(e))
                        coords = None
                    if coords:
                        logger.info("macro=F2 phase=find_bar corr=%s attempt=%d result=match coords=%s conf>=%.2f", corr, attempt + 1, str(coords), conf)
                        # Log which monitor this detection is on
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
                                        logger.info("vision: search bar found on monitor %d: %s", i, str(mon))
                                        break
                        except Exception:
                            pass
                        break
                    # On the 4th attempt, try pressing inventory again (some UIs toggle)
                    if attempt == 2:
                        try:
                            if hasattr(input_controller, 'press_token'):
                                input_controller.press_token(inv_token)
                            else:
                                name = inv_token.split('_', 1)[1] if '_' in inv_token else inv_token
                                if inv_token.startswith('key_'):
                                    input_controller.press_key(name)
                        except Exception:
                            pass
                    try:
                        time.sleep(0.04)
                    except Exception:
                        pass
                try:
                    logger.info("macro=F2 phase=find_bar corr=%s duration_ms=%.1f found=%s", corr, (_t.perf_counter() - t_phase) * 1000.0, bool(coords))
                except Exception:
                    pass
                if not coords:
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
                        self._log(f'Search bar not found. Best score={bs:.2f} (need >= 0.50–0.70). Try re-capturing closer to the field center.')
                    else:
                        logging.getLogger(__name__).info("search: miss after 8 attempts. no debug meta available")
                        self._log('Search bar not found on screen.')
                    return

                # 3) Click, clear field safely, type text (avoid Ctrl+A to prevent stray 'A')
                try:
                    if self.overlay:
                        self.overlay.set_status("Clicking search box and typing...")
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
                        logger.info("macro=F2 phase=focus_field corr=%s duration_ms=%.1f", corr, (_t.perf_counter() - t_phase) * 1000.0)
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
                        logger.info("macro=F2 phase=clear_field corr=%s duration_ms=%.1f", corr, (_t.perf_counter() - t_phase) * 1000.0)
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
                        logger.info("macro=F2 phase=type_and_apply corr=%s duration_ms=%.1f", corr, (_t.perf_counter() - t_phase) * 1000.0)
                    except Exception:
                        pass

                    # Give the game a brief moment to apply the filter before scanning
                    try:
                        _t.sleep(0.05)
                    except Exception:
                        pass

                    # ROI calibration from search bar and fast tier-aware item match
                    try:
                        start_roi = _t.perf_counter()
                        # If F6 ROI exists, use it directly for speed instead of slow calibration
                        inv_roi = None
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
                                    logging.getLogger(__name__).info("F6 ROI: using F6 ROI directly for speed (skipping calibration)")
                            except Exception:
                                pass

                        # Only do slow calibration if no F6 ROI available
                        if inv_roi is None:
                            cal_start = _t.perf_counter()
                            try:
                                # Use a slightly lower confidence for calibration to improve robustness at 4K
                                inv_roi = vision_controller.calibrate_inventory_roi_from_search(str(tmpl), min_conf=0.65)
                            except Exception:
                                inv_roi = None
                            cal_time = (_t.perf_counter() - cal_start) * 1000.0
                            logging.getLogger(__name__).info("timing: ROI calibration = %.1f ms", cal_time)
                        # If user provided an absolute ROI via F6, reinterpret it as a sub-ROI of inventory
                        # so matching happens only inside the selected box.
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
                                    logging.getLogger(__name__).info("F6 ROI intersection: F6=(%d,%d,%d,%d) inv=(%d,%d,%d,%d) result=(%d,%d,%d,%d)",
                                                                     abs_left, abs_top, abs_w, abs_h,
                                                                     inv_left, inv_top, inv_w, inv_h,
                                                                     inter_left, inter_top, inter_right-inter_left, inter_bottom-inter_top)

                                    # Log which monitors these ROIs are on
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
                                            logging.getLogger(__name__).info("F6 ROI monitors: F6_ROI=%s, INV_ROI=%s", f6_mon, inv_mon)
                                    except Exception:
                                        pass

                                    if inter_right > inter_left and inter_bottom > inter_top and inv_w > 0 and inv_h > 0:
                                        rl = (inter_left - inv_left) / float(inv_w)
                                        rt = (inter_top - inv_top) / float(inv_h)
                                        rw = (inter_right - inter_left) / float(inv_w)
                                        rh = (inter_bottom - inter_top) / float(inv_h)
                                        os.environ['GW_INV_SUBROI'] = f"{rl:.4f},{rt:.4f},{rw:.4f},{rh:.4f}"
                                        logging.getLogger(__name__).info("F6 ROI: using intersection as sub-ROI: rel=(%.3f,%.3f,%.3f,%.3f)",
                                                                         rl, rt, rw, rh)
                                    else:
                                        # No overlap: clear sub-ROI to avoid hiding items
                                        logging.getLogger(__name__).info("F6 ROI: no overlap with inventory ROI, clearing sub-ROI")
                                        if 'GW_INV_SUBROI' in os.environ:
                                            os.environ.pop('GW_INV_SUBROI', None)
                        except Exception:
                            pass
                        # Fallback: if calibration failed but F6 ROI exists, use it directly as inventory ROI
                        try:
                            if inv_roi is None and _abs_roi_env:
                                parts2 = [int(p.strip()) for p in _abs_roi_env.split(',')]
                                if len(parts2) == 4:
                                    vision_controller.inventory_roi = {
                                        'left': int(parts2[0]), 'top': int(parts2[1]),
                                        'width': int(parts2[2]), 'height': int(parts2[3])
                                    }
                                    logging.getLogger(__name__).info("F6 ROI: using F6 as inventory ROI (calibration failed)")
                        except Exception:
                            pass

                        # Additional fallback: if F6 ROI exists but has no overlap with detected inventory,
                        # use F6 ROI directly instead of the bad auto-detection
                        try:
                            if _abs_roi_env and isinstance(inv_roi, dict) and 'GW_INV_SUBROI' not in os.environ:
                                parts3 = [int(p.strip()) for p in _abs_roi_env.split(',')]
                                if len(parts3) == 4:
                                    vision_controller.inventory_roi = {
                                        'left': int(parts3[0]), 'top': int(parts3[1]),
                                        'width': int(parts3[2]), 'height': int(parts3[3])
                                    }
                                    logging.getLogger(__name__).info("F6 ROI: overriding auto-detected inventory ROI due to no overlap")
                        except Exception:
                            pass

                        roi_bgr, roi_region = vision_controller.grab_inventory_bgr()
                        dur_roi = (_t.perf_counter() - start_roi) * 1000.0
                        logging.getLogger(__name__).info("macro=F2 phase=roi_grab corr=%s duration_ms=%.1f roi=%dx%d", corr,
                                                         dur_roi, int(roi_region.get('width', 0)), int(roi_region.get('height', 0)))

                        # Armor matcher (lazy init)
                        if self._armor_matcher is None:
                            base_dir = self.config_manager.config_path.parent
                            self._armor_matcher = ArmorMatcher(assets_dir=Path('assets'), app_templates_dir=base_dir / 'templates')

                        name_norm = str(text).strip().lower().replace(' ', '_')
                        start_match = _t.perf_counter()
                        match = self._armor_matcher.best_for_name(roi_bgr, name_norm, threshold=0.22, early_exit=True)
                        dur_match = (_t.perf_counter() - start_match) * 1000.0
                        logging.getLogger(__name__).info("macro=F2 phase=match_item corr=%s name=%s duration_ms=%.1f found=%s", corr,
                                                         name_norm, dur_match, bool(match))

                        if match:
                            x, y, _, _, w, h = match
                            # Capture a small patch before interaction to detect change after equip
                            try:
                                _pre_patch = None
                                try:
                                    yy0 = max(0, int(y))
                                    xx0 = max(0, int(x))
                                    yy1 = min(int(y + h), roi_bgr.shape[0])
                                    xx1 = min(int(x + w), roi_bgr.shape[1])
                                    if yy1 > yy0 and xx1 > xx0:
                                        _pre_patch = roi_bgr[yy0:yy1, xx0:xx1].copy()
                                except Exception:
                                    _pre_patch = None
                            except Exception:
                                _pre_patch = None
                            abs_x = int(roi_region['left']) + int(x) + int(w) // 2
                            abs_y = int(roi_region['top']) + int(y) + int(h) // 2

                            # Time the mouse movement and clicking
                            start_mouse = _t.perf_counter()
                            input_controller.move_mouse(abs_x, abs_y)
                            mouse_move_time = (_t.perf_counter() - start_mouse) * 1000.0

                            try:
                                _t.sleep(0.025)  # small settle after moving mouse
                            except Exception:
                                pass

                            start_click = _t.perf_counter()
                            input_controller.click_button('left', presses=1, interval=0.0)
                            click_time = (_t.perf_counter() - start_click) * 1000.0

                            try:
                                _t.sleep(0.045)  # let the item focus register
                            except Exception:
                                pass

                            start_equip = _t.perf_counter()
                            # Ensure equip registers: double E press with minimal interval
                            input_controller.press_key('e', presses=1, interval=0.0)
                            try:
                                _t.sleep(0.090)  # slight gap for game to register E
                            except Exception:
                                pass
                            input_controller.press_key('e', presses=1, interval=0.0)
                            # Small settle after second E before verifying
                            try:
                                _t.sleep(0.030)
                            except Exception:
                                pass

                            # Intelligent wait: confirm local patch changes (item moved/equipped) before proceeding
                            try:
                                changed = False
                                for _chk in range(6):  # up to ~120ms
                                    try:
                                        _t.sleep(0.02)
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
                                        _t.sleep(0.006)
                                    except Exception:
                                        pass
                                    input_controller.press_key('e', presses=1, interval=0.0)
                            except Exception:
                                pass

                            equip_time = (_t.perf_counter() - start_equip) * 1000.0

                            total_interaction = mouse_move_time + 2.0 + click_time + 1.0 + equip_time
                            logging.getLogger(__name__).info("macro=F2 phase=click_and_equip corr=%s mouse_ms=%.1f click_ms=%.1f equip_ms=%.1f total_ms=%.1f",
                                                             corr, mouse_move_time, click_time, equip_time, total_interaction)
                        else:
                            # Include best observed score for visibility
                            best_sc = None
                            try:
                                if self._armor_matcher and hasattr(self._armor_matcher, 'get_last_best'):
                                    best_sc = self._armor_matcher.get_last_best(name_norm)
                            except Exception:
                                best_sc = None
                            if best_sc is not None:
                                logging.getLogger(__name__).info("macro=F2 phase=match_item corr=%s name=%s result=no_match best_score=%.3f", corr, name_norm, float(best_sc))
                            else:
                                logging.getLogger(__name__).info("macro=F2 phase=match_item corr=%s name=%s result=no_match", corr, name_norm)
                    except Exception:
                        pass
                except Exception:
                    pass
                finally:
                    pass
            except Exception:
                pass
        try:
            setattr(_job, '_gw_task_id', 'search_and_type')
        except Exception:
            pass
        return _job

    def _task_equip_flak_fullset(self) -> Callable[[object, object], None]:
        """
        Create a task for equipping a complete Flak armor set (F2 hotkey).

        Automatically searches for and equips all Flak armor pieces in sequence.
        Supports multiple armor tiers (Ascendant, Mastercraft) with automatic detection.

        Returns:
            Callable task function for the worker queue
        """
        pieces = [
            "Flak Helmet",
            "Flak Chestpiece",
            "Flak Leggings",
            "Flak Gauntlets",
            "Flak Boots",
        ]
        def _job(vision_controller, input_controller):
            import time as _t
            logger = logging.getLogger(__name__)
            try:
                # 1) Open inventory (supports keyboard or mouse token)
                inv_token = self._get_token(self.config_manager, 'inventory_key', 'key_i')
                try:
                    if hasattr(input_controller, 'press_token'):
                        input_controller.press_token(inv_token)
                    else:
                        name = inv_token.split('_', 1)[1] if '_' in inv_token else inv_token
                        if inv_token.startswith('key_'):
                            input_controller.press_key(name)
                except Exception:
                    pass
                _t.sleep(0.25)

                # 2) Locate the search bar ONCE (fast scan, band around inventory)
                tmpl = self.config_manager.get('search_bar_template')
                if not tmpl:
                    self._log('Search bar template not set. Use F8 on Calibration page.')
                    return
                _abs_roi_env = os.environ.get('GW_VISION_ROI', '').strip()
                coords = None
                for attempt in range(5):
                    conf = max(0.50, 0.70 - 0.03 * attempt)
                    _prev_abs = None
                    try:
                        if _abs_roi_env:
                            _prev_abs = os.environ.pop('GW_VISION_ROI', None)
                        # Try a search band above the inventory area to reduce search space
                        band = None
                        try:
                            inv_hint = None
                            if _abs_roi_env:
                                parts = [int(p.strip()) for p in _abs_roi_env.split(',')]
                                if len(parts) == 4:
                                    inv_hint = { 'left': parts[0], 'top': parts[1], 'width': parts[2], 'height': parts[3] }
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
                                try:
                                    import mss
                                    with mss.mss() as sct:
                                        vb = sct.monitors[0]
                                        band_left = max(vb['left'], min(band_left, vb['left'] + vb['width'] - band_w))
                                        band_top = max(vb['top'], min(band_top, vb['top'] + vb['height'] - band_h))
                                except Exception:
                                    pass
                                band = { 'left': int(band_left), 'top': int(band_top), 'width': int(band_w), 'height': int(band_h) }
                        except Exception:
                            band = None
                        prev_manual_roi = getattr(vision_controller, 'search_roi', None)
                        try:
                            if band is not None and hasattr(vision_controller, 'set_search_roi'):
                                vision_controller.set_search_roi(band)
                            _prev_fast = os.environ.get('GW_VISION_FAST_ONLY')
                            try:
                                os.environ['GW_VISION_FAST_ONLY'] = '1'
                                coords = vision_controller.find_template(str(tmpl), confidence=conf)
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
                    finally:
                        if _prev_abs is not None:
                            os.environ['GW_VISION_ROI'] = _prev_abs
                    if coords:
                        break
                    if attempt == 2:
                        try:
                            if hasattr(input_controller, 'press_token'):
                                input_controller.press_token(inv_token)
                            else:
                                name = inv_token.split('_', 1)[1] if '_' in inv_token else inv_token
                                if inv_token.startswith('key_'):
                                    input_controller.press_key(name)
                        except Exception:
                            pass
                    _t.sleep(0.04)
                if not coords:
                    self._log('Search bar not found — aborting fullset equip.')
                    return

                # 3) Determine inventory ROI once (honor F6 absolute ROI if set)
                inv_roi = None
                if _abs_roi_env:
                    try:
                        parts = [int(p.strip()) for p in _abs_roi_env.split(',')]
                        if len(parts) == 4:
                            inv_roi = {
                                'left': int(parts[0]), 'top': int(parts[1]),
                                'width': int(parts[2]), 'height': int(parts[3])
                            }
                            vision_controller.inventory_roi = inv_roi
                            logging.getLogger(__name__).info("F6 ROI: using F6 ROI directly for speed (skipping calibration)")
                    except Exception:
                        inv_roi = None
                if inv_roi is None:
                    try:
                        inv_roi = vision_controller.calibrate_inventory_roi_from_search(str(tmpl), min_conf=0.65)
                    except Exception:
                        inv_roi = None
                # Compute sub-ROI from F6 ROI intersection if available
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
                            if inter_right > inter_left and inter_bottom > inter_top and inv_w > 0 and inv_h > 0:
                                rl = (inter_left - inv_left) / float(inv_w)
                                rt = (inter_top - inv_top) / float(inv_h)
                                rw = (inter_right - inter_left) / float(inv_w)
                                rh = (inter_bottom - inter_top) / float(inv_h)
                                os.environ['GW_INV_SUBROI'] = f"{rl:.4f},{rt:.4f},{rw:.4f},{rh:.4f}"
                            else:
                                os.environ.pop('GW_INV_SUBROI', None)
                except Exception:
                    pass

                # Ensure armor matcher
                if self._armor_matcher is None:
                    base_dir = self.config_manager.config_path.parent
                    self._armor_matcher = ArmorMatcher(assets_dir=Path('assets'), app_templates_dir=base_dir / 'templates')

                # 4) Rapidly filter, click, and equip each piece

                for idx, disp in enumerate(pieces):
                    try:
                        # Focus search field
                        input_controller.move_mouse(*coords)
                        _t.sleep(0.01)
                        input_controller.click_button('left', presses=1, interval=0.0)
                        _t.sleep(0.01)
                        # Use Ctrl+A to select all text, then Delete to clear
                        input_controller.hotkey('ctrl', 'a')
                        _t.sleep(0.03)  # allow selection highlight to register
                        input_controller.press_key('delete')
                        _t.sleep(0.02)
                        # Type/paste the piece name and apply filter
                        try:
                            if hasattr(input_controller, 'paste_text'):
                                input_controller.paste_text(disp, pre_delay=0.01, settle=0.005)
                            else:
                                input_controller.type_text_precise(disp, interval=0.01, pre_delay=0.03)
                        except Exception:
                            try:
                                input_controller.type_text_precise(disp, interval=0.01, pre_delay=0.03)
                            except Exception:
                                pass
                        _t.sleep(0.010)
                        input_controller.press_key('enter')
                        # Allow the filter UI to update very briefly
                        _t.sleep(0.060)

                        # Grab inventory ROI and try to match the item quickly
                        name_norm = str(disp).strip().lower().replace(' ', '_')
                        roi_bgr, roi_region = vision_controller.grab_inventory_bgr()
                        match = None
                        for _try in range(6):  # allow brief UI update windows before giving up
                            try:
                                match = self._armor_matcher.best_for_name(roi_bgr, name_norm, threshold=0.25, early_exit=True)
                            except Exception:
                                match = None
                            if match:
                                break
                            _t.sleep(0.02)  # allow UI to update
                            try:
                                roi_bgr, roi_region = vision_controller.grab_inventory_bgr()
                            except Exception:
                                pass

                        if match:
                            x, y, _, _, w, h = match
                            abs_x = int(roi_region['left']) + int(x) + int(w) // 2
                            abs_y = int(roi_region['top']) + int(y) + int(h) // 2
                            input_controller.move_mouse(abs_x, abs_y)
                            _t.sleep(0.025)  # small settle after move
                            input_controller.click_button('left', presses=1, interval=0.0)
                            _t.sleep(0.045)  # let focus register
                            # Ensure equip registers: double E with a short gap
                            input_controller.press_key('e', presses=1, interval=0.0)
                            _t.sleep(0.090)
                            input_controller.press_key('e', presses=1, interval=0.0)
                            # Small settle after second E before moving on
                            _t.sleep(0.030)
                            # Quick verify if item is still in the same place; if so, retry click+E once
                            try:
                                prev_cx, prev_cy = int(abs_x), int(abs_y)
                                roi_after, reg_after = vision_controller.grab_inventory_bgr()
                                m2 = self._armor_matcher.best_for_name(roi_after, name_norm, threshold=0.28, early_exit=True)
                                if m2:
                                    x2, y2, _, _, w2, h2 = m2
                                    cx2 = int(reg_after['left']) + int(x2) + int(w2) // 2
                                    cy2 = int(reg_after['top']) + int(y2) + int(h2) // 2
                                    if abs(cx2 - prev_cx) <= 8 and abs(cy2 - prev_cy) <= 8:
                                        input_controller.click_button('left', presses=1, interval=0.0)
                                        _t.sleep(0.006)
                                        input_controller.press_key('e', presses=1, interval=0.0)
                            except Exception:
                                pass
                            _t.sleep(0.020)  # tiny settle between pieces
                        else:
                            logger.info("macro=F2 fullset: no match for %s", name_norm)
                    except Exception as e:
                        logger.exception("macro=F2 fullset: error on piece %s: %s", str(disp), str(e))

                # Close inventory via Escape to ensure a clean exit from the loop
                try:
                    input_controller.press_key('esc')
                except Exception:
                    pass

            except Exception as e:
                try:
                    logger.exception("macro=F2 fullset: fatal error: %s", str(e))
                except Exception:
                    pass
            finally:
                pass
            # end _job
        try:
            setattr(_job, '_gw_task_id', 'equip_flak_fullset')
        except Exception:
            pass
        return _job

    def _task_equip_tek_fullset(self) -> Callable[[object, object], None]:
        """
        Create a task for equipping a complete Tek armor set (F3 hotkey).

        Automatically searches for and equips all Tek armor pieces in sequence.
        Uses F6 ROI optimization when available for faster search bar detection.

        Returns:
            Callable task function for the worker queue
        """
        pieces = [
            "Tek Helmet",
            "Tek Chestpiece",
            "Tek Leggings",
            "Tek Gauntlets",
            "Tek Boots",
        ]
        def _job(vision_controller, input_controller):
            import time as _t
            logger = logging.getLogger(__name__)
            try:
                # 1) Open inventory (supports keyboard or mouse token)
                inv_token = self._get_token(self.config_manager, 'inventory_key', 'key_i')
                try:
                    if hasattr(input_controller, 'press_token'):
                        input_controller.press_token(inv_token)
                    else:
                        name = inv_token.split('_', 1)[1] if '_' in inv_token else inv_token
                        if inv_token.startswith('key_'):
                            input_controller.press_key(name)
                except Exception:
                    pass
                # 1) Open inventory (supports keyboard or mouse token)
                inv_token = self._get_token(self.config_manager, 'inventory_key', 'key_i')
                try:
                    if hasattr(input_controller, 'press_token'):
                        input_controller.press_token(inv_token)
                    else:
                        name = inv_token.split('_', 1)[1] if '_' in inv_token else inv_token
                        if inv_token.startswith('key_'):
                            input_controller.press_key(name)
                except Exception:
                    pass
                _t.sleep(0.25)

                # 2) Locate the search bar ONCE (use F6 ROI shortcut if available)
                tmpl = self.config_manager.get('search_bar_template')
                if not tmpl:
                    self._log('Search bar template not set. Use F8 on Calibration page.')
                    return
                _abs_roi_env = os.environ.get('GW_VISION_ROI', '').strip()
                coords = None

                # Use F6 ROI for fast search bar positioning when available
                if _abs_roi_env:
                    try:
                        parts = [int(p.strip()) for p in _abs_roi_env.split(',')]
                        if len(parts) == 4:
                            roi_left, roi_top, roi_w, roi_h = parts
                            # Calculate search bar position relative to inventory area
                            search_x = roi_left + int(roi_w * 0.15)  # 15% from left edge
                            search_y = max(50, roi_top - 50)  # 50px above ROI, minimum 50px from top
                            coords = (search_x, search_y)
                            logging.getLogger(__name__).info("F3 Tek: using F6 ROI to estimate search bar position (%d,%d)", search_x, search_y)
                    except Exception:
                        coords = None

                # Fall back to template matching if F6 optimization unavailable
                if coords is None:
                    for attempt in range(5):
                        conf = max(0.50, 0.70 - 0.03 * attempt)
                        _prev_abs = None
                        try:
                            if _abs_roi_env:
                                _prev_abs = os.environ.pop('GW_VISION_ROI', None)
                            band = None
                            try:
                                inv_hint = None
                                if _abs_roi_env:
                                    parts = [int(p.strip()) for p in _abs_roi_env.split(',')]
                                    if len(parts) == 4:
                                        inv_hint = { 'left': parts[0], 'top': parts[1], 'width': parts[2], 'height': parts[3] }
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
                                    try:
                                        import mss
                                        with mss.mss() as sct:
                                            vb = sct.monitors[0]
                                            band_left = max(vb['left'], min(band_left, vb['left'] + vb['width'] - band_w))
                                            band_top = max(vb['top'], min(band_top, vb['top'] + vb['height'] - band_h))
                                    except Exception:
                                        pass
                                    band = { 'left': int(band_left), 'top': int(band_top), 'width': int(band_w), 'height': int(band_h) }
                            except Exception:
                                band = None
                            prev_manual_roi = getattr(vision_controller, 'search_roi', None)
                            try:
                                if band is not None and hasattr(vision_controller, 'set_search_roi'):
                                    vision_controller.set_search_roi(band)
                                _prev_fast = os.environ.get('GW_VISION_FAST_ONLY')
                                try:
                                    os.environ['GW_VISION_FAST_ONLY'] = '1'
                                    coords = vision_controller.find_template(str(tmpl), confidence=conf)
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
                        finally:
                            if _abs_roi_env and _prev_abs is not None:
                                os.environ['GW_VISION_ROI'] = _prev_abs
                        if coords:
                            break
                        if attempt == 2:
                            try:
                                if hasattr(input_controller, 'press_token'):
                                    input_controller.press_token(inv_token)
                                else:
                                    name = inv_token.split('_', 1)[1] if '_' in inv_token else inv_token
                                    if inv_token.startswith('key_'):
                                        input_controller.press_key(name)
                            except Exception:
                                pass
                        _t.sleep(0.04)
                if not coords:
                    self._log('Search bar not found — aborting tek fullset equip.')
                    return

                # 3) Determine inventory ROI once (honor F6 absolute ROI if set)
                inv_roi = None
                if _abs_roi_env:
                    try:
                        parts = [int(p.strip()) for p in _abs_roi_env.split(',')]
                        if len(parts) == 4:
                            inv_roi = {
                                'left': int(parts[0]), 'top': int(parts[1]),
                                'width': int(parts[2]), 'height': int(parts[3])
                            }
                            vision_controller.inventory_roi = inv_roi
                            logging.getLogger(__name__).info("F6 ROI: using F6 ROI directly for speed (skipping calibration)")
                    except Exception:
                        inv_roi = None
                if inv_roi is None:
                    try:
                        inv_roi = vision_controller.calibrate_inventory_roi_from_search(str(tmpl), min_conf=0.65)
                    except Exception:
                        inv_roi = None
                # Compute sub-ROI from F6 ROI intersection if available (same as F2)
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
                            if inter_right > inter_left and inter_bottom > inter_top and inv_w > 0 and inv_h > 0:
                                rl = (inter_left - inv_left) / float(inv_w)
                                rt = (inter_top - inv_top) / float(inv_h)
                                rw = (inter_right - inter_left) / float(inv_w)
                                rh = (inter_bottom - inter_top) / float(inv_h)
                                os.environ['GW_INV_SUBROI'] = f"{rl:.4f},{rt:.4f},{rw:.4f},{rh:.4f}"
                            else:
                                os.environ.pop('GW_INV_SUBROI', None)
                except Exception:
                    pass

                # Ensure armor matcher
                if self._armor_matcher is None:
                    base_dir = self.config_manager.config_path.parent
                    self._armor_matcher = ArmorMatcher(assets_dir=Path('assets'), app_templates_dir=base_dir / 'templates')

                for idx, disp in enumerate(pieces):
                    try:
                        # Focus search field
                        input_controller.move_mouse(*coords)
                        _t.sleep(0.01)
                        input_controller.click_button('left', presses=1, interval=0.0)
                        _t.sleep(0.01)
                        # Use Ctrl+A to select all text, then Delete to clear
                        input_controller.hotkey('ctrl', 'a')
                        _t.sleep(0.03)  # allow selection highlight to register
                        input_controller.press_key('delete')
                        _t.sleep(0.02)
                        # Type/paste the piece name and apply filter
                        try:
                            if hasattr(input_controller, 'paste_text'):
                                input_controller.paste_text(disp, pre_delay=0.01, settle=0.005)
                            else:
                                input_controller.type_text_precise(disp, interval=0.01, pre_delay=0.03)
                        except Exception:
                            try:
                                input_controller.type_text_precise(disp, interval=0.01, pre_delay=0.03)
                            except Exception:
                                pass
                        _t.sleep(0.010)
                        input_controller.press_key('enter')
                        # Allow the filter UI to update very briefly
                        _t.sleep(0.060)

                        # Grab inventory ROI and try to match the item quickly
                        name_norm = str(disp).strip().lower().replace(' ', '_')
                        roi_bgr, roi_region = vision_controller.grab_inventory_bgr()
                        match = None
                        for _try in range(6):  # allow brief UI update windows before giving up
                            try:
                                match = self._armor_matcher.best_for_name(roi_bgr, name_norm, threshold=0.25, early_exit=True)
                            except Exception:
                                match = None
                            if match:
                                break
                            _t.sleep(0.02)  # allow UI to update
                            try:
                                roi_bgr, roi_region = vision_controller.grab_inventory_bgr()
                            except Exception:
                                pass

                        if match:
                            x, y, _, _, w, h = match
                            abs_x = int(roi_region['left']) + int(x) + int(w) // 2
                            abs_y = int(roi_region['top']) + int(y) + int(h) // 2
                            input_controller.move_mouse(abs_x, abs_y)
                            _t.sleep(0.025)  # small settle after move
                            input_controller.click_button('left', presses=1, interval=0.0)
                            _t.sleep(0.045)  # let focus register
                            # Ensure equip registers: double E with a short gap
                            input_controller.press_key('e', presses=1, interval=0.0)
                            _t.sleep(0.090)
                            input_controller.press_key('e', presses=1, interval=0.0)
                            # Small settle after second E before moving on
                            _t.sleep(0.030)
                            # Quick verify if item is still in the same place; if so, retry click+E once
                            try:
                                prev_cx, prev_cy = int(abs_x), int(abs_y)
                                roi_after, reg_after = vision_controller.grab_inventory_bgr()
                                m2 = self._armor_matcher.best_for_name(roi_after, name_norm, threshold=0.28, early_exit=True)
                                if m2:
                                    x2, y2, _, _, w2, h2 = m2
                                    cx2 = int(reg_after['left']) + int(x2) + int(w2) // 2
                                    cy2 = int(reg_after['top']) + int(y2) + int(h2) // 2
                                    if abs(cx2 - prev_cx) <= 8 and abs(cy2 - prev_cy) <= 8:
                                        input_controller.click_button('left', presses=1, interval=0.0)
                                        _t.sleep(0.006)
                                        input_controller.press_key('e', presses=1, interval=0.0)
                            except Exception:
                                pass
                            _t.sleep(0.020)  # tiny settle between pieces
                        else:
                            logger.info("macro=F3 tek fullset: no match for %s", name_norm)
                    except Exception as e:
                        logger.exception("macro=F3 tek fullset: error on piece %s: %s", str(disp), str(e))

                # Close inventory via Escape
                try:
                    input_controller.press_key('esc')
                except Exception:
                    pass
            finally:
                pass
        try:
            setattr(_job, '_gw_task_id', 'equip_tek_fullset')
        except Exception:
            pass
        return _job

    def _task_equip_mixed_fullset(self) -> Callable[[object, object], None]:
        """
        Create a task for equipping a mixed armor set configuration (F4 hotkey).

        Equips an optimized mixed set:
        - Flak Helmet (protection focus)
        - Tek Chestpiece (durability and stats)
        - Tek Gauntlets (advanced features)
        - Flak Leggings (mobility)
        - Flak Boots (comfort and protection)

        Returns:
            Callable task function for the worker queue
        """
        pieces = [
            "Flak Helmet",
            "Tek Chestpiece",
            "Tek Gauntlets",
            "Flak Leggings",
            "Flak Boots",
        ]
        def _job(vision_controller, input_controller):
            import time as _t
            logger = logging.getLogger(__name__)
            try:
                # 1) Open inventory (supports keyboard or mouse token)
                inv_token = self._get_token(self.config_manager, 'inventory_key', 'key_i')
                try:
                    if hasattr(input_controller, 'press_token'):
                        input_controller.press_token(inv_token)
                    else:
                        name = inv_token.split('_', 1)[1] if '_' in inv_token else inv_token
                        if inv_token.startswith('key_'):
                            input_controller.press_key(name)
                except Exception:
                    pass
                # 1) Open inventory (supports keyboard or mouse token)
                inv_token = self._get_token(self.config_manager, 'inventory_key', 'key_i')
                try:
                    if hasattr(input_controller, 'press_token'):
                        input_controller.press_token(inv_token)
                    else:
                        name = inv_token.split('_', 1)[1] if '_' in inv_token else inv_token
                        if inv_token.startswith('key_'):
                            input_controller.press_key(name)
                except Exception:
                    pass
                _t.sleep(0.25)

                # 2) Locate the search bar ONCE (use F6 ROI shortcut if available)
                tmpl = self.config_manager.get('search_bar_template')
                if not tmpl:
                    self._log('Search bar template not set. Use F8 on Calibration page.')
                    return
                _abs_roi_env = os.environ.get('GW_VISION_ROI', '').strip()
                coords = None

                # Use F6 ROI for fast search bar positioning when available
                if _abs_roi_env:
                    try:
                        parts = [int(p.strip()) for p in _abs_roi_env.split(',')]
                        if len(parts) == 4:
                            roi_left, roi_top, roi_w, roi_h = parts
                            # Calculate search bar position relative to inventory area
                            search_x = roi_left + int(roi_w * 0.15)  # 15% from left edge
                            search_y = max(50, roi_top - 50)  # 50px above ROI, minimum 50px from top
                            coords = (search_x, search_y)
                            logging.getLogger(__name__).info("F4 Mixed: using F6 ROI to estimate search bar position (%d,%d)", search_x, search_y)
                    except Exception:
                        coords = None

                # Fall back to template matching if F6 optimization unavailable
                if coords is None:
                    for attempt in range(5):
                        conf = max(0.50, 0.70 - 0.03 * attempt)
                        _prev_abs = None
                        try:
                            if _abs_roi_env:
                                _prev_abs = os.environ.pop('GW_VISION_ROI', None)
                            band = None
                            try:
                                inv_hint = None
                                if _abs_roi_env:
                                    parts = [int(p.strip()) for p in _abs_roi_env.split(',')]
                                    if len(parts) == 4:
                                        inv_hint = { 'left': parts[0], 'top': parts[1], 'width': parts[2], 'height': parts[3] }
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
                                    try:
                                        import mss
                                        with mss.mss() as sct:
                                            vb = sct.monitors[0]
                                            band_left = max(vb['left'], min(band_left, vb['left'] + vb['width'] - band_w))
                                            band_top = max(vb['top'], min(band_top, vb['top'] + vb['height'] - band_h))
                                    except Exception:
                                        pass
                                    band = { 'left': int(band_left), 'top': int(band_top), 'width': int(band_w), 'height': int(band_h) }
                            except Exception:
                                band = None
                            prev_manual_roi = getattr(vision_controller, 'search_roi', None)
                            try:
                                if band is not None and hasattr(vision_controller, 'set_search_roi'):
                                    vision_controller.set_search_roi(band)
                                _prev_fast = os.environ.get('GW_VISION_FAST_ONLY')
                                try:
                                    os.environ['GW_VISION_FAST_ONLY'] = '1'
                                    coords = vision_controller.find_template(str(tmpl), confidence=conf)
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
                        finally:
                            if _abs_roi_env and _prev_abs is not None:
                                os.environ['GW_VISION_ROI'] = _prev_abs
                        if coords:
                            break
                        if attempt == 2:
                            try:
                                if hasattr(input_controller, 'press_token'):
                                    input_controller.press_token(inv_token)
                                else:
                                    name = inv_token.split('_', 1)[1] if '_' in inv_token else inv_token
                                    if inv_token.startswith('key_'):
                                        input_controller.press_key(name)
                            except Exception:
                                pass
                        _t.sleep(0.04)
                if not coords:
                    self._log('Search bar not found — aborting mixed fullset equip.')
                    return

                # 3) Determine inventory ROI once (honor F6 absolute ROI if set) and compute sub-ROI like F2
                inv_roi = None
                if _abs_roi_env:
                    try:
                        parts = [int(p.strip()) for p in _abs_roi_env.split(',')]
                        if len(parts) == 4:
                            inv_roi = {
                                'left': int(parts[0]), 'top': int(parts[1]),
                                'width': int(parts[2]), 'height': int(parts[3])
                            }
                            vision_controller.inventory_roi = inv_roi
                            logging.getLogger(__name__).info("F6 ROI: using F6 ROI directly for speed (skipping calibration)")
                    except Exception:
                        inv_roi = None
                if inv_roi is None:
                    try:
                        inv_roi = vision_controller.calibrate_inventory_roi_from_search(str(tmpl), min_conf=0.65)
                    except Exception:
                        inv_roi = None
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
                            if inter_right > inter_left and inter_bottom > inter_top and inv_w > 0 and inv_h > 0:
                                rl = (inter_left - inv_left) / float(inv_w)
                                rt = (inter_top - inv_top) / float(inv_h)
                                rw = (inter_right - inter_left) / float(inv_w)
                                rh = (inter_bottom - inter_top) / float(inv_h)
                                os.environ['GW_INV_SUBROI'] = f"{rl:.4f},{rt:.4f},{rw:.4f},{rh:.4f}"
                            else:
                                os.environ.pop('GW_INV_SUBROI', None)
                except Exception:
                    pass

                # Ensure armor matcher
                if self._armor_matcher is None:
                    base_dir = self.config_manager.config_path.parent
                    self._armor_matcher = ArmorMatcher(assets_dir=Path('assets'), app_templates_dir=base_dir / 'templates')

                for idx, disp in enumerate(pieces):
                    try:
                        # Focus search field
                        input_controller.move_mouse(*coords)
                        _t.sleep(0.01)
                        input_controller.click_button('left', presses=1, interval=0.0)
                        _t.sleep(0.01)
                        # Use Ctrl+A to select all text, then Delete to clear
                        input_controller.hotkey('ctrl', 'a')
                        _t.sleep(0.03)  # allow selection highlight to register
                        input_controller.press_key('delete')
                        _t.sleep(0.02)
                        # Type/paste the piece name and apply filter
                        try:
                            if hasattr(input_controller, 'paste_text'):
                                input_controller.paste_text(disp, pre_delay=0.01, settle=0.005)
                            else:
                                input_controller.type_text_precise(disp, interval=0.01, pre_delay=0.03)
                        except Exception:
                            try:
                                input_controller.type_text_precise(disp, interval=0.01, pre_delay=0.03)
                            except Exception:
                                pass
                        _t.sleep(0.010)
                        input_controller.press_key('enter')
                        # Allow the filter UI to update very briefly
                        _t.sleep(0.060)

                        # Grab inventory ROI and try to match the item quickly
                        name_norm = str(disp).strip().lower().replace(' ', '_')
                        roi_bgr, roi_region = vision_controller.grab_inventory_bgr()
                        match = None
                        # Apply optimized threshold for Tek Gauntlets detection accuracy
                        threshold = 0.22 if name_norm == 'tek_gauntlets' else 0.25
                        for _try in range(6):  # allow brief UI update windows before giving up
                            try:
                                match = self._armor_matcher.best_for_name(roi_bgr, name_norm, threshold=threshold, early_exit=True)
                            except Exception:
                                match = None
                            if match:
                                break
                            _t.sleep(0.02)  # allow UI to update
                            try:
                                roi_bgr, roi_region = vision_controller.grab_inventory_bgr()
                            except Exception:
                                pass

                        if match:
                            x, y, _, _, w, h = match
                            abs_x = int(roi_region['left']) + int(x) + int(w) // 2
                            abs_y = int(roi_region['top']) + int(y) + int(h) // 2
                            input_controller.move_mouse(abs_x, abs_y)
                            _t.sleep(0.025)  # small settle after move
                            input_controller.click_button('left', presses=1, interval=0.0)
                            _t.sleep(0.045)  # let focus register
                            # Ensure equip registers: double E with a short gap
                            input_controller.press_key('e', presses=1, interval=0.0)
                            _t.sleep(0.090)
                            input_controller.press_key('e', presses=1, interval=0.0)
                            # Small settle after second E before moving on
                            _t.sleep(0.030)
                            # Quick verify if item is still in the same place; if so, retry click+E once
                            try:
                                prev_cx, prev_cy = int(abs_x), int(abs_y)
                                roi_after, reg_after = vision_controller.grab_inventory_bgr()
                                m2 = self._armor_matcher.best_for_name(roi_after, name_norm, threshold=0.28, early_exit=True)
                                if m2:
                                    x2, y2, _, _, w2, h2 = m2
                                    cx2 = int(reg_after['left']) + int(x2) + int(w2) // 2
                                    cy2 = int(reg_after['top']) + int(y2) + int(h2) // 2
                                    if abs(cx2 - prev_cx) <= 8 and abs(cy2 - prev_cy) <= 8:
                                        input_controller.click_button('left', presses=1, interval=0.0)
                                        _t.sleep(0.006)
                                        input_controller.press_key('e', presses=1, interval=0.0)
                            except Exception:
                                pass
                            _t.sleep(0.020)  # tiny settle between pieces
                        else:
                            logger.info("macro=F4 mixed fullset: no match for %s", name_norm)
                    except Exception as e:
                        logger.exception("macro=F4 mixed fullset: error on piece %s: %s", str(disp), str(e))

                # Close inventory via Escape to ensure a clean exit from the loop
                try:
                    input_controller.press_key('esc')
                except Exception:
                    pass
            except Exception as e:
                try:
                    logger.exception("macro=F4 mixed fullset: fatal error: %s", str(e))
                except Exception:
                    pass
            finally:
                pass
            # end _job
        try:
            setattr(_job, '_gw_task_id', 'equip_mixed_fullset')
        except Exception:
            pass
        return _job

    def _complete_and_exit_calibration(self) -> None:
        try:
            self.config_manager.config["DEFAULT"]["calibration_complete"] = "True"
            self.config_manager.save()
        except Exception:
            pass
        # Verify search bar template is detectable now that calibration is complete
        self._verify_search_template()
        if self.overlay:
            try:
                if hasattr(self.overlay, "switch_to_main"):
                    self.overlay.switch_to_main()
                self.overlay.set_status(self._menu_text())
                if hasattr(self.overlay, "success_flash"):
                    self.overlay.success_flash(self._MSG_CAL_DONE)
            except Exception:
                pass

    def _verify_search_template(self) -> None:
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

    def _wait_for_start_only(self) -> None:
        # Wait until the Start button sets the gate; ignore F7
        try:
            # Ensure we start from a clean state
            self._calibration_gate.clear()
        except Exception:
            pass
        while not self._calibration_gate.is_set():
            self._maybe_exit_on_f10()
            time.sleep(0.1)

    def _run_cal_menu_until_start_and_ready(self) -> None:
        while True:
            self._wait_for_start_only()
            if self._is_calibration_ready():
                self._complete_and_exit_calibration()
                break
            if self.overlay:
                try:
                    self.overlay.set_status("Incomplete: set Inventory, Tek Cancel, and capture Template, then click Start.")
                except Exception:
                    pass
            try:
                self._calibration_gate.clear()
            except Exception:
                pass

    # --------------------------- UI calibration handlers ----------------------------
    def _ui_capture_key(self, key_name: str, prompt: str, is_tek: bool) -> None:
        token = self._prompt_until_valid(prompt)
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

    def _ui_capture_template(self) -> None:
        if self.overlay:
            try:
                self.overlay.set_status("Open your inventory, hover the search bar, then press F8 to capture.")
            except Exception:
                pass
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

    def _log(self, msg: str) -> None:
        """Log message to overlay UI if available, otherwise print to console."""
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
                self.overlay.set_status("Calibration menu — click buttons to capture Inventory, Tek Cancel, and Template (F8). Then click Start.")
        except Exception:
            pass
