"""Config subpackage.

- vision: central knobs for vision thresholds, scales, and toggles
"""
# Import vision configuration explicitly to avoid F403
from .vision import (
    FAST_SCALES,
    FULL_SCALES,
    SERVER_SCALES_DEFAULT,
    BLACK_STD_SKIP,
    INVENTORY_ITEM_THRESHOLD,
    FAST_ONLY,
    PERF_ENABLED,
    ARTIFACT_MAX_DIM,
)

# Re-export all vision constants for convenience
__all__ = [
    "FAST_SCALES",
    "FULL_SCALES",
    "SERVER_SCALES_DEFAULT",
    "BLACK_STD_SKIP",
    "INVENTORY_ITEM_THRESHOLD",
    "FAST_ONLY",
    "PERF_ENABLED",
    "ARTIFACT_MAX_DIM",
]
