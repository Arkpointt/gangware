"""Vision configuration constants.

This module contains configuration values for the vision system including
scales, thresholds, and performance settings.
"""

# Scale ranges for template matching
FAST_SCALES = [0.8, 0.9, 1.0, 1.1, 1.2]
FULL_SCALES = [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5]
SERVER_SCALES_DEFAULT = [0.8, 0.9, 1.0, 1.1, 1.2, 1.3]

# Performance and quality settings
BLACK_STD_SKIP = 10.0  # Skip frames with standard deviation below this value
FAST_ONLY = False  # If True, only use fast scales
PERF_ENABLED = True  # Enable performance logging

# Detection thresholds
INVENTORY_ITEM_THRESHOLD = 0.7  # Minimum confidence for inventory items

# Artifact settings
ARTIFACT_MAX_DIM = 800  # Maximum dimension for saved debug artifacts
