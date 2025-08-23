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

import mss
import numpy as np
from ..features.combat.armor_matcher import ArmorMatcher
from ..features.debug.keys import capture_input_windows, wait_key_release
from ..features.debug.template import wait_and_capture_template

import ctypes
import logging

# Macro libraries
from ..features.combat.macros import armor_swapper, combat

# Windows utilities - use centralized module instead of duplicating
from .win32 import utils as w32

if sys.platform == "win32":
    from ctypes import wintypes
    user32 = w32.user32
    kernel32 = w32.kernel32
    POINT = w32.POINT
    RECT = w32.RECT
    _cursor_pos = w32.cursor_pos
else:
    from ctypes import wintypes
    user32 = None
    kernel32 = None
    POINT = object
    RECT = object
    def _cursor_pos() -> Tuple[int, int]:
        return (0, 0)


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
                    monitor_bounds = w32.current_monitor_bounds()
                    rel_roi = w32.absolute_to_relative_roi(_roi_str, monitor_bounds)
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
        # Monitor and ROI logging already handled by debug logging

    def _absolute_to_relative_roi(self, abs_str: str, monitor_bounds: Optional[dict] = None) -> str:
        """Convert absolute ROI (pixels) to relative (percentages).

        Format: 'abs_x,abs_y,abs_w,abs_h' -> 'rel_x,rel_y,rel_w,rel_h'
        """
        try:
            if not abs_str.strip():
                return ""

            if monitor_bounds is None:
                monitor_bounds = w32.current_monitor_bounds()

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

    # --------------------------- Thread entry ----------------------------

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
        from .calibration import CalibrationManager
        calibration_manager = CalibrationManager(self.config_manager, self.overlay)
        calibration_manager.ensure_calibrated()

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
        monitor_bounds = w32.current_monitor_bounds()

        # Clamp to monitor bounds
        left = max(monitor_bounds["left"], min(left, monitor_bounds["left"] + monitor_bounds["width"] - width))
        top = max(monitor_bounds["top"], min(top, monitor_bounds["top"] + monitor_bounds["height"] - height))

        # Create absolute ROI string for current session
        abs_roi_str = f"{int(left)},{int(top)},{int(width)},{int(height)}"
        os.environ["GW_VISION_ROI"] = abs_roi_str

        # Convert to relative coordinates for storage
        rel_roi_str = w32.absolute_to_relative_roi(abs_roi_str, monitor_bounds)

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
        from .task_management import TaskManager
        task_manager = TaskManager(self.task_queue, self.overlay)
        task_manager.handle_macro_hotkey(task_callable, hotkey_label)

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
        from .task_management import TaskManager
        task_manager = TaskManager(self.task_queue, self.overlay)
        task_manager.queue_tek_dash_task(self._task_tek_punch())

    def _flash_tek_dash_overlay(self) -> None:
        """Flash the hotkey line in the overlay for tek dash feedback."""
        from .task_management import TaskManager
        task_manager = TaskManager(self.task_queue, self.overlay)
        task_manager.flash_tek_dash_overlay(self.HOTKEY_SHIFT_R)

    def _is_task_pending(self, predicate: Callable[[object], bool]) -> bool:
        """Check if any queued task matches predicate, thread-safely if possible."""
        from .task_management import TaskManager
        task_manager = TaskManager(self.task_queue, self.overlay)
        return task_manager.is_task_pending(predicate)

    @staticmethod
    def _is_tek_punch_task(task_obj: object) -> bool:
        from .task_management import TaskManager
        return TaskManager.is_tek_punch_task(task_obj)

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
        from .calibration import CalibrationManager
        calibration_manager = CalibrationManager(self.config_manager, self.overlay)
        calibration_manager.process_recalibration(self._recalibrate_event)

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
        """Return a normalized token like 'key_i' or 'mouse_xbutton2'."""
        from .hotkey_utils import get_token
        return get_token(config_manager, key_name, default_token)

    @staticmethod
    def _token_display(token: str) -> str:
        """Human-friendly label for overlay messages."""
        from .hotkey_utils import token_display
        return token_display(token)

    # --------------------------- Macro: search and type ----------------------------
    def _task_search_and_type(self, text: str) -> Callable[[object, object], None]:
        """Create task for searching and typing text in inventory."""
        from ..features.combat.search_service import SearchService
        search_service = SearchService(self.config_manager, self.overlay)
        return search_service.create_search_and_type_task(text)

    def _task_equip_flak_fullset(self) -> Callable[[object, object], None]:
        """Create task for equipping complete Flak armor set (F2 hotkey)."""
        from ..features.combat.armor_equipment import ArmorEquipmentService
        armor_service = ArmorEquipmentService(self.config_manager, self.input_controller)
        return armor_service.create_flak_fullset_task()

    def _task_equip_tek_fullset(self) -> Callable[[object, object], None]:
        """Create task for equipping complete Tek armor set (F3 hotkey)."""
        from ..features.combat.armor_equipment import ArmorEquipmentService
        armor_service = ArmorEquipmentService(self.config_manager, self.input_controller)
        return armor_service.create_tek_fullset_task()

    def _task_equip_mixed_fullset(self) -> Callable[[object, object], None]:
        """Create task for equipping mixed armor set configuration (F4 hotkey)."""
        from ..features.combat.armor_equipment import ArmorEquipmentService
        armor_service = ArmorEquipmentService(self.config_manager, self.input_controller)
        return armor_service.create_mixed_fullset_task()

    def _complete_and_exit_calibration(self) -> None:
        """Complete calibration and mark as finished."""
        from ..features.debug.calibration_service import CalibrationService
        calibration_service = CalibrationService(self.config_manager, self.overlay, self._calibration_gate)
        calibration_service.complete_and_exit_calibration()

    def _verify_search_template(self) -> None:
        """Verify the search bar template is detectable after calibration."""
        from ..features.debug.calibration_service import CalibrationService
        calibration_service = CalibrationService(self.config_manager, self.overlay, self._calibration_gate)
        calibration_service.verify_search_template()

    def _wait_for_start_only(self) -> None:
        """Wait until the Start button sets the gate; ignore F7."""
        from ..features.debug.calibration_service import CalibrationService
        calibration_service = CalibrationService(self.config_manager, self.overlay, self._calibration_gate)
        calibration_service.wait_for_start_only(self._maybe_exit_on_f10)

    def _run_cal_menu_until_start_and_ready(self) -> None:
        """Run calibration menu until start and ready."""
        from ..features.debug.calibration_service import CalibrationService
        calibration_service = CalibrationService(self.config_manager, self.overlay, self._calibration_gate)
        calibration_service.run_cal_menu_until_start_and_ready(
            self._maybe_exit_on_f10,
            self._is_calibration_ready
        )

    # --------------------------- UI calibration handlers ----------------------------
    def _ui_capture_key(self, key_name: str, prompt: str, is_tek: bool) -> None:
        """Capture a key or token for calibration."""
        from ..features.debug.calibration_service import CalibrationService
        calibration_service = CalibrationService(self.config_manager, self.overlay, self._calibration_gate)
        calibration_service.capture_key(key_name, prompt, is_tek, self._prompt_until_valid)

    def _ui_capture_template(self) -> None:
        """Capture search bar template."""
        from ..features.debug.calibration_service import CalibrationService
        calibration_service = CalibrationService(self.config_manager, self.overlay, self._calibration_gate)
        calibration_service.capture_template()

    def _log(self, msg: str) -> None:
        """Log message to overlay UI if available, otherwise print to console."""
        from ..features.debug.calibration_service import CalibrationService
        calibration_service = CalibrationService(self.config_manager, self.overlay, self._calibration_gate)
        calibration_service.log_message(msg)

    # --------------------------- UI helpers ----------------------------
    def _prepare_recalibration_ui(self) -> None:
        """Ensure the overlay is visible and switched to calibration with guidance text."""
        from ..features.debug.calibration_service import CalibrationService
        calibration_service = CalibrationService(self.config_manager, self.overlay, self._calibration_gate)
        calibration_service.prepare_recalibration_ui()
