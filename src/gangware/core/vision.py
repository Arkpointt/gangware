"""
Vision configuration knobs centralization.

All thresholds, scale ranges, and environment toggles live here. Controllers
and detectors import from this module instead of hardcoding values.
"""
from __future__ import annotations

from typing import List
import os

# Scale search sets
FAST_SCALES: List[float] = [0.90, 0.95, 1.00, 1.05, 1.10]
FULL_SCALES: List[float] = [round(0.55 + 0.05 * i, 2) for i in range(23)]  # 0.55..1.65

SERVER_SCALES_DEFAULT: List[float] = [round(0.8 + 0.05 * i, 2) for i in range(9)]  # 0.8..1.2

# Thresholds
BLACK_STD_SKIP: float = 1.0
INVENTORY_ITEM_THRESHOLD: float = 0.86

# Environment flags
FAST_ONLY: bool = os.environ.get("GW_VISION_FAST_ONLY", "0") == "1"
PERF_ENABLED: bool = os.environ.get("GW_VISION_PERF", "0") == "1"

# Artifact sizes
ARTIFACT_MAX_DIM: int = 640

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
