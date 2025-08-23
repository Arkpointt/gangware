from __future__ import annotations

# Import combat manager classes
from .tek_dash import TekDashManager
from .medbrew_hot import MedbrewHotManager
from .task_factory import ArmorTaskFactory
from .armor_equipment import ArmorEquipmentService
from .armor_matcher import ArmorMatcher
from .search_service import SearchService

# Import macro modules
from .macros import armor_swapper as _armor
from .macros import combat as _combat

"""Combat Feature Facade

Encapsulates all COMBAT actions exposed on the overlay's main page and
hotkeys (F2, F3, F4, Shift+Q, Shift+E, Shift+R) behind a clean API so
controllers can remain thin and the project follows Package-by-Feature.
"""


# Task factory functions for backward compatibility
def task_equip_flak_fullset():
    """Return a callable for equipping flak armor."""
    def _job(_vision_controller, input_controller):
        _armor.execute(_vision_controller, input_controller, "flak")
    return _job


def task_equip_tek_fullset():
    """Return a callable for equipping tek armor."""
    def _job(_vision_controller, input_controller):
        _armor.execute(_vision_controller, input_controller, "tek")
    return _job


def task_equip_mixed_fullset():
    """Return a callable for equipping mixed armor."""
    def _job(_vision_controller, input_controller):
        _armor.execute(_vision_controller, input_controller, "mixed")
    return _job


def task_medbrew_burst():
    """Return a callable for medbrew burst."""
    def _job(_vision_controller, input_controller):
        _combat.execute_medbrew_burst(input_controller)
    return _job


def task_medbrew_hot_toggle():
    """Return a callable for medbrew hot toggle."""
    def _job(_vision_controller, input_controller):
        _combat.execute_medbrew_hot_toggle(input_controller)
    return _job


def task_tek_punch(config_manager):
    """Return a callable for tek punch."""
    def _job(_vision_controller, input_controller):
        _combat.execute_tek_punch(input_controller, config_manager)
    return _job


__all__ = [
    # Manager classes
    "TekDashManager",
    "MedbrewHotManager",
    "ArmorTaskFactory",
    "ArmorEquipmentService",
    "ArmorMatcher",
    "SearchService",
    # Legacy task functions
    "task_equip_flak_fullset",
    "task_equip_tek_fullset",
    "task_equip_mixed_fullset",
    "task_medbrew_burst",
    "task_medbrew_hot_toggle",
    "task_tek_punch",
]
