"""Windows helper utilities used across Gangware.

This module centralizes OS-specific helpers so other modules remain smaller and focused.
All functions are defensive: they return safe fallbacks on non-Windows platforms.
"""
from __future__ import annotations

import os
import sys
import ctypes
from typing import Optional, Tuple, TYPE_CHECKING, Any

# Optional deps with proper typing
mss: Optional[Any]
try:
    import mss
except ImportError:  # pragma: no cover - optional import
    mss = None

# Type-safe Windows API imports
if TYPE_CHECKING:
    from ctypes import wintypes
    user32: Any
    kernel32: Any
    POINT: Any
    RECT: Any
elif sys.platform == "win32":
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
else:  # pragma: no cover - non-Windows fallback
    class _WinTypesStub:
        class MSG(ctypes.Structure):
            _fields_: list[tuple[str, object]] = []
    wintypes = _WinTypesStub()
    user32 = None
    kernel32 = None
    POINT = object
    RECT = object


def cursor_pos() -> Tuple[int, int]:
    """Return current cursor position in screen coordinates."""
    if sys.platform != "win32" or user32 is None:
        return (0, 0)
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return int(getattr(pt, "x", 0)), int(getattr(pt, "y", 0))


def virtual_screen_rect() -> Optional[tuple[int, int, int, int]]:
    """Return the virtual screen rectangle (union of all monitors)."""
    if mss is None:
        return None
    try:
        with mss.mss() as sct:
            vb = sct.monitors[0]
            L = int(vb.get("left", 0))
            T = int(vb.get("top", 0))
            R = L + int(vb.get("width", 0))
            B = T + int(vb.get("height", 0))
            return (L, T, R, B)
    except Exception:
        return None


def current_monitor_bounds() -> dict:
    """Return monitor bounds dict containing the current cursor position.

    Keys: left, top, width, height
    """
    if mss is None:
        return {"left": 0, "top": 0, "width": 1920, "height": 1080}
    try:
        cx, cy = cursor_pos()
        with mss.mss() as sct:
            # Find which monitor contains the cursor
            for monitor in sct.monitors[1:]:  # skip virtual screen at index 0
                if (monitor.get("left", 0) <= cx < monitor.get("left", 0) + monitor.get("width", 0)
                    and monitor.get("top", 0) <= cy < monitor.get("top", 0) + monitor.get("height", 0)):
                    return {
                        "left": int(monitor.get("left", 0)),
                        "top": int(monitor.get("top", 0)),
                        "width": int(monitor.get("width", 0)),
                        "height": int(monitor.get("height", 0)),
                    }
            # Fallback to primary monitor if not found
            if len(sct.monitors) > 1:
                m = sct.monitors[1]
            else:
                m = sct.monitors[0]
            return {
                "left": int(m.get("left", 0)),
                "top": int(m.get("top", 0)),
                "width": int(m.get("width", 0)),
                "height": int(m.get("height", 0)),
            }
    except Exception:
        # Ultimate fallback
        return {"left": 0, "top": 0, "width": 1920, "height": 1080}


def relative_to_absolute_roi(rel_str: str, monitor_bounds: Optional[dict] = None) -> str:
    """Convert relative ROI ("x,y,w,h" in 0..1) to absolute pixel string."""
    try:
        s = (rel_str or "").strip()
        if not s:
            return ""
        if monitor_bounds is None:
            monitor_bounds = current_monitor_bounds()
        parts = [float(p.strip()) for p in s.split(",")]
        if len(parts) != 4:
            return ""
        rx, ry, rw, rh = parts
        ax = int(monitor_bounds["left"] + rx * monitor_bounds["width"])
        ay = int(monitor_bounds["top"] + ry * monitor_bounds["height"])
        aw = int(rw * monitor_bounds["width"])
        ah = int(rh * monitor_bounds["height"])
        return f"{ax},{ay},{aw},{ah}"
    except Exception:
        return ""


def absolute_to_relative_roi(abs_str: str, monitor_bounds: Optional[dict] = None) -> str:
    """Convert absolute pixel ROI ("x,y,w,h") to relative string."""
    try:
        s = (abs_str or "").strip()
        if not s:
            return ""
        if monitor_bounds is None:
            monitor_bounds = current_monitor_bounds()
        parts = [int(p.strip()) for p in s.split(",")]
        if len(parts) != 4:
            return ""
        ax, ay, aw, ah = parts
        rx = (ax - monitor_bounds["left"]) / max(1, monitor_bounds["width"])
        ry = (ay - monitor_bounds["top"]) / max(1, monitor_bounds["height"])
        rw = aw / max(1, monitor_bounds["width"])
        rh = ah / max(1, monitor_bounds["height"])
        rx = max(0.0, min(1.0, rx))
        ry = max(0.0, min(1.0, ry))
        rw = max(0.0, min(1.0, rw))
        rh = max(0.0, min(1.0, rh))
        return f"{rx:.6f},{ry:.6f},{rw:.6f},{rh:.6f}"
    except Exception:
        return ""


def ark_window_rect_by_proc() -> Optional[tuple[int, int, int, int]]:
    """Find Ark window by process image name (arkascended.exe) and return rect."""
    if sys.platform != "win32" or user32 is None or kernel32 is None:
        return None
    target_exe = "arkascended.exe"
    found_hwnd = wintypes.HWND()

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _enum_proc(hwnd, lparam):  # pragma: no cover - requires Windows GUI
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
    if not getattr(found_hwnd, "value", None):
        return None
    rc = RECT()
    if not user32.GetWindowRect(found_hwnd, ctypes.byref(rc)):
        return None
    return (int(rc.left), int(rc.top), int(rc.right), int(rc.bottom))


def ark_window_rect_by_title() -> Optional[tuple[int, int, int, int]]:
    """Find Ark window by title substring (case-insensitive)."""
    if sys.platform != "win32" or user32 is None:
        return None
    target = "arkascended"
    found_hwnd = wintypes.HWND()

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _enum_proc(hwnd, lparam):  # pragma: no cover - requires Windows GUI
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
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
            return False
        return True

    user32.EnumWindows(_enum_proc, 0)
    if not getattr(found_hwnd, "value", None):
        return None
    rc = RECT()
    if not user32.GetWindowRect(found_hwnd, ctypes.byref(rc)):
        return None
    return (int(rc.left), int(rc.top), int(rc.right), int(rc.bottom))


def ensure_ark_foreground(timeout: float = 3.0) -> bool:
    """Try to make ArkAscended.exe the foreground window within timeout."""
    if sys.platform != "win32" or user32 is None or kernel32 is None:
        return False
    import time as _t
    end = _t.time() + max(0.0, float(timeout))
    SW_RESTORE = 9

    def _find_hwnd_by_proc():
        target_exe = "arkascended.exe"
        found_hwnd = wintypes.HWND()

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def _enum_proc(hwnd, lparam):  # pragma: no cover - requires Windows GUI
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
        return found_hwnd if getattr(found_hwnd, "value", None) else None

    # Quick success if already foreground
    if foreground_executable_name() == "arkascended.exe":
        return True

    while _t.time() < end:
        hwnd = _find_hwnd_by_proc()
        if hwnd and getattr(hwnd, "value", None):
            try:
                user32.ShowWindow(hwnd, SW_RESTORE)
            except Exception:
                pass
            try:
                user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
            if foreground_executable_name() == "arkascended.exe":
                return True
        _t.sleep(0.1)
    return False


def foreground_executable_name() -> str:
    """Return the lowercase executable name of the foreground process on Windows."""
    if sys.platform != "win32" or user32 is None or kernel32 is None:
        return ""
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
