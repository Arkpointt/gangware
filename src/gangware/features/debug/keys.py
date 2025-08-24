"""Calibration key-capture service for Windows.

Encapsulates GetAsyncKeyState scanning, token normalization, ignored keys during
calibration, Esc-to-restart behavior, and key-release debounce.

The HotkeyManager delegates to these helpers to keep the controller thin.
"""
from __future__ import annotations

import time
from typing import Optional, Protocol

from ...core.win32 import utils as w32


class OverlayProtocol(Protocol):
    """Protocol for overlay objects with status and prompt methods."""
    def set_status(self, text: str) -> None: ...
    def prompt_key_capture(self, prompt: str) -> None: ...

user32 = w32.user32

# Ignored keys during calibration input (debounced)
_IGNORED = {"F1", "F7"}


def vk_name(vk: int) -> str:
    """Return a human-readable name for common virtual key codes.

    Names align with what input controllers expect (e.g., 'left', 'right',
    'space', 'enter', 'num5', 'F12', etc.).
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
    # Common special keys
    special = {
        0x1B: "esc",
        0x20: "space",
        0x09: "tab",
        0x0D: "enter",
        0x10: "shift",
        0x11: "ctrl",
        0x12: "alt",
        0x08: "backspace",
        0x2D: "insert",
        0x2E: "delete",
        0x24: "home",
        0x23: "end",
        0x21: "pageup",
        0x22: "pagedown",
        0x2C: "printscreen",
        0x14: "capslock",
        0x90: "numlock",
        0x91: "scrolllock",
    }
    # Arrow keys
    arrows = {0x25: "left", 0x26: "up", 0x27: "right", 0x28: "down"}
    if vk in arrows:
        return arrows[vk]
    # Numpad digits
    if 0x60 <= vk <= 0x69:
        return f"num{vk - 0x60}"
    return special.get(vk, f"vk_{vk}")


def is_mouse_vk(vk: int) -> bool:
    return vk in (1, 2, 4, 5, 6)


def process_pressed_vk(vk: int) -> Optional[str]:
    """Map a pressed virtual-key into a token/control signal.

    Returns:
      - 'mouse_x...' or 'key_X' for a valid input
      - '__restart__' when Esc was pressed
      - '__debounce__' for ignored inputs (F1/F7)
    """
    name = vk_name(vk)
    # Ignored calibration control keys (debounced)
    if name in _IGNORED:
        time.sleep(0.05)
        return "__debounce__"
    # Esc clears current value and restarts prompt
    if name == "esc":
        return "__restart__"
    # Allow any mouse button
    if is_mouse_vk(vk):
        return f"mouse_{name}"
    # Keyboard key normalized
    return f"key_{name}"


def capture_input_windows(prompt: str, overlay: Optional[OverlayProtocol] = None) -> Optional[str]:
    """Poll GetAsyncKeyState until a valid key or mouse button is pressed.

    Returns a normalized token or '__restart__'. Returns None if Windows API is unavailable.
    """
    if user32 is None:
        if overlay and hasattr(overlay, "set_status"):
            overlay.set_status("Calibration is supported on Windows only.")
        return None

    try:
        if overlay and hasattr(overlay, "prompt_key_capture"):
            overlay.prompt_key_capture(prompt)
    except Exception:
        pass

    while True:
        # Scan a reasonable range of virtual-key codes
        for vk in range(1, 256):
            try:
                state = user32.GetAsyncKeyState(vk)
            except Exception:
                state = 0
            if state & 0x8000:
                result = process_pressed_vk(vk)
                if result == "__debounce__":
                    break  # continue outer loop
                return result
        time.sleep(0.02)


def wait_key_release(vk: int, timeout: float = 1.0) -> None:
    """Wait for a virtual key to be released, with timeout protection."""
    if user32 is None:
        return
    end = time.time() + max(0.0, float(timeout))
    while time.time() < end:
        try:
            if not bool(user32.GetAsyncKeyState(vk) & 0x8000):
                break
        except Exception:
            break
        time.sleep(0.02)
