"""Combat Feature Facade

Encapsulates all COMBAT actions exposed on the overlay's main page and
hotkeys (F2, F3, F4, Shift+Q, Shift+E, Shift+R) behind a clean API so
controllers can remain thin and the project follows Package-by-Feature.

Usage (from HotkeyManager):
    from gangware.features.combat import (
        task_equip_flak_fullset,
        task_equip_tek_fullset,
        task_equip_mixed_fullset,
        task_medbrew_burst,
        task_medbrew_hot_toggle,
        task_tek_punch,
    )

    self.task_queue.put_nowait(task_equip_flak_fullset())

Each factory returns a callable with signature (vision_controller, input_controller)
that is directly executable by the Worker.
"""
from __future__ import annotations

from typing import Callable

# Reuse existing macro implementations; this file only wires feature boundaries.
from ...macros import armor_swapper as _armor
from ...macros import combat as _combat


# ----------------------- Armor equip tasks (F2/F3/F4) -----------------------

def task_equip_flak_fullset() -> Callable[[object, object], None]:
    def _job(vision_controller, input_controller):
        _armor.execute(vision_controller, input_controller, "flak")
    return _job


def task_equip_tek_fullset() -> Callable[[object, object], None]:
    def _job(vision_controller, input_controller):
        _armor.execute(vision_controller, input_controller, "tek")
    return _job


def task_equip_mixed_fullset() -> Callable[[object, object], None]:
    def _job(vision_controller, input_controller):
        _armor.execute(vision_controller, input_controller, "mixed")
    return _job


# --------------------------- Combat actions (Q/E/R) -------------------------

def task_medbrew_burst() -> Callable[[object, object], None]:
    def _job(_vision_controller, input_controller):
        _combat.execute_medbrew_burst(input_controller)
    return _job


def task_medbrew_hot_toggle(overlay=None) -> Callable[[object, object], None]:
    # Provided for completeness; HotkeyManager uses a dedicated HOT thread.
    def _job(_vision_controller, input_controller):
        _combat.execute_medbrew_hot_toggle(input_controller, overlay)
    return _job


def task_tek_punch(config_manager) -> Callable[[object, object], None]:
    def _job(_vision_controller, input_controller):
        _combat.execute_tek_punch(input_controller, config_manager)
    return _job


__all__ = [
    "task_equip_flak_fullset",
    "task_equip_tek_fullset",
    "task_equip_mixed_fullset",
    "task_medbrew_burst",
    "task_medbrew_hot_toggle",
    "task_tek_punch",
]
