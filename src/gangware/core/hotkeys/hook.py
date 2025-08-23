"""Windows global hotkey hook.

Encapsulates RegisterHotKey registration and a Windows message pump in a small,
reusable class so feature controllers (e.g., HotkeyManager) can stay thin.

Usage (Windows only):
    from ..win32 import utils as w32
    from .hook import HotkeyHook

    # Define IDs and key combos (modifiers + virtual-key code)
    ids = {
        1: (0x0000, 0x76, "F7"),
        2: (0x0000, 0x79, "F10"),
        # ...
    }

    def on_f7():
        pass

    handlers = { 1: on_f7, 2: lambda: ... }
    hook = HotkeyHook(ids, handlers)
    hook.start()

Notes:
- Non-Windows platforms are effectively no-ops (start() returns False).
- Registration failures are logged but do not raise; polling fallbacks can still be used.
"""
from __future__ import annotations

import ctypes
import logging
import threading
from typing import Callable, Dict, Tuple

from ..win32 import utils as w32

user32 = w32.user32
wintypes = w32.wintypes

WM_HOTKEY = 0x0312


class HotkeyHook:
    """Register and pump global hotkeys (Windows only)."""

    def __init__(
        self,
        id_to_vk: Dict[int, Tuple[int, int, str]],
        id_to_handler: Dict[int, Callable[[], None]],
        logger: logging.Logger | None = None,
    ) -> None:
        self._id_to_vk = dict(id_to_vk)
        self._id_to_handler = dict(id_to_handler)
        self._logger = logger or logging.getLogger(__name__)
        self._thread: threading.Thread | None = None
        self._running = threading.Event()

    # ----------------------------- lifecycle -----------------------------
    def start(self) -> bool:
        """Start the message loop thread and register hotkeys.

        Returns True if the hook thread was started on Windows; False otherwise.
        """
        if user32 is None:
            self._logger.info("hotkey_hook: non-Windows platform; skipping hook")
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._running.set()
        t = threading.Thread(target=self._message_loop, daemon=True)
        self._thread = t
        try:
            t.start()
            return True
        except Exception:
            self._logger.exception("hotkey_hook: failed to start message loop thread")
            return False

    def stop(self) -> None:
        if user32 is None:
            return
        try:
            self._running.clear()
            # Best-effort: request the thread to exit by posting WM_QUIT
            user32.PostQuitMessage(0)  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=1.5)
        except Exception:
            pass

    # ------------------------------ internals ----------------------------
    def _message_loop(self) -> None:  # pragma: no cover - requires Windows messages
        try:
            msg = self._create_message_queue()
            self._register_hotkeys()
            self._pump_messages(msg)
        except Exception:
            self._logger.exception("hotkey_hook: message loop crashed")
        finally:
            # Always try to unregister known IDs
            for hid in list(self._id_to_vk.keys()):
                try:
                    user32.UnregisterHotKey(None, hid)  # type: ignore
                except Exception:
                    pass

    def _create_message_queue(self):
        msg = wintypes.MSG()  # type: ignore[attr-defined]
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # type: ignore
        return msg

    def _register_hotkeys(self) -> None:
        # id_to_vk: id -> (modifier, vk, name)
        for hid, (mod, vk, name) in self._id_to_vk.items():
            try:
                ok = bool(user32.RegisterHotKey(None, hid, mod, vk))  # type: ignore
                if not ok:
                    self._logger.info("hotkey_hook: failed to register %s (id=%d)", name, hid)
            except Exception:
                self._logger.info("hotkey_hook: exception registering %s (id=%d)", name, hid)

    def _pump_messages(self, msg) -> None:
        while self._running.is_set():
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)  # type: ignore
            if ret == 0:
                break  # WM_QUIT
            if ret == -1:
                continue
            if int(getattr(msg, "message", 0)) == WM_HOTKEY:
                try:
                    handler = self._id_to_handler.get(int(getattr(msg, "wParam", 0)))
                    if handler:
                        handler()
                except Exception:
                    self._logger.exception("hotkey_hook: handler raised")
            user32.TranslateMessage(ctypes.byref(msg))  # type: ignore
            user32.DispatchMessageW(ctypes.byref(msg))  # type: ignore
