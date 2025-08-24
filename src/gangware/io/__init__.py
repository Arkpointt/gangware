"""IO subpackage for platform-specific integrations.

- win: Windows helpers for foreground window and regions
- controls: Input automation and control system
"""
from .win import (
    get_foreground_executable_name_lower,
    get_foreground_window_region,
    get_ark_window_region,
)
from .controls import InputController

__all__ = [
    "InputController",
    "get_foreground_executable_name_lower",
    "get_foreground_window_region",
    "get_ark_window_region",
]
