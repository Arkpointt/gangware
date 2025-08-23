"""IO subpackage for platform-specific integrations.

- win: Windows helpers for foreground window and regions
- controls: Input automation and control system
"""
from .win import *  # convenience
from .controls import InputController

__all__ = ["InputController"]
