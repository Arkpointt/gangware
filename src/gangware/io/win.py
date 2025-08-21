"""
Windows-specific helpers for querying the foreground window and regions.

Separated from controllers to keep platform IO concerns isolated and testable.
"""
from __future__ import annotations

import os
import ctypes
from typing import Optional, Dict

if os.name == "nt":
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    def get_foreground_executable_name_lower() -> str:
        try:
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
        except Exception:
            return ""

    def get_foreground_window_region() -> Optional[Dict[str, int]]:
        try:
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None
            rc = RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rc)):
                return None
            left, top = int(rc.left), int(rc.top)
            width, height = int(rc.right - rc.left), int(rc.bottom - rc.top)
            if width <= 0 or height <= 0:
                return None
            return {"left": left, "top": top, "width": width, "height": height}
        except Exception:
            return None

    def get_ark_window_region() -> Optional[Dict[str, int]]:
        try:
            if get_foreground_executable_name_lower() != "arkascended.exe":
                return None
            return get_foreground_window_region()
        except Exception:
            return None
else:
    def get_foreground_executable_name_lower() -> str:
        return ""

    def get_foreground_window_region():
        return None

    def get_ark_window_region():
        return None

__all__ = [
    "get_foreground_executable_name_lower",
    "get_foreground_window_region",
    "get_ark_window_region",
]
