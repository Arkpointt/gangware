"""Debug/Overlay pixel helpers.

This module provides pixel target utilities for the debug overlay.
Note: Functionality has been simplified to stub implementations.
"""
from __future__ import annotations

from typing import List, Tuple, Any

# Placeholder targets
TARGETS: dict[str, Any] = {}

def list_targets():
    """Return empty list."""
    return []

def save_norm_and_patch(*args, **kwargs):
    """No-op placeholder function."""
    pass

def load_norm(*args, **kwargs):
    """No-op placeholder function."""
    return None

def load_patch(*args, **kwargs):
    """No-op placeholder function."""
    return None

def norm_to_abs(*args, **kwargs):
    """No-op placeholder function."""
    return None

def load_abs(*args, **kwargs):
    """No-op placeholder function."""
    return None

def overlay_items() -> List[Tuple[str, str]]:
    """Return list of (display_name, key) for the overlay combo box."""
    return [(display, key) for (key, display) in list_targets()]

__all__ = [
    "TARGETS",
    "list_targets",
    "overlay_items",
    "save_norm_and_patch",
    "load_norm",
    "load_patch",
    "norm_to_abs",
    "load_abs",
]
