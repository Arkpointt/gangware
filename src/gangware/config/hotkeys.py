"""Hotkey configuration: VK codes, modifiers, and default ID mapping.

Centralizes hotkey bindings in one place to keep controllers thin and
configuration-driven. IDs are chosen to match legacy behavior.
"""
from __future__ import annotations

from typing import Dict, Tuple

# Modifiers
MOD_NONE = 0x0000
MOD_SHIFT = 0x0004

# Virtual-key codes (Windows)
VK_F1, VK_F2, VK_F3, VK_F4 = 0x70, 0x71, 0x72, 0x73
VK_F6, VK_F7, VK_F9, VK_F10 = 0x75, 0x76, 0x78, 0x79
VK_F11 = 0x7A
VK_Q, VK_E, VK_R = 0x51, 0x45, 0x52


def build_default_id_map(shift_e_label: str, shift_r_label: str) -> Dict[int, Tuple[int, int, str]]:
    """Return the default id -> (modifier, VK, display name) mapping.

    The IDs mirror legacy values to preserve existing behavior/wiring.
    """
    return {
        1: (MOD_NONE, VK_F7, "F7"),
        11: (MOD_NONE, VK_F9, "F9"),
        2: (MOD_NONE, VK_F10, "F10"),
        3: (MOD_NONE, VK_F1, "F1"),
        12: (MOD_NONE, VK_F11, "F11"),
        10: (MOD_NONE, VK_F6, "F6"),
        4: (MOD_NONE, VK_F2, "F2"),
        5: (MOD_NONE, VK_F3, "F3"),
        6: (MOD_NONE, VK_F4, "F4"),
        7: (MOD_SHIFT, VK_Q, "Shift+Q"),
        8: (MOD_SHIFT, VK_E, shift_e_label),
        9: (MOD_SHIFT, VK_R, shift_r_label),
    }
