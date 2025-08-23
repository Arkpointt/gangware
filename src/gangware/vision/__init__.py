"""Vision package: pure image ops and matching strategies.

Submodules:
- preprocess: stateless image preprocessing utilities
- matcher: multi-scale, multi-variant template matching
- controller: vision orchestration and screen capture
"""
from .preprocess import (
    edges,
    screen_variants,
    make_tile_mask,
    apply_mask,
    resize_tpl,
    tpl_variants,
    create_server_button_mask,
)
from .matcher import best_match_multi, match_methods
from .controller import VisionController

__all__ = [
    "edges",
    "screen_variants",
    "make_tile_mask",
    "apply_mask",
    "resize_tpl",
    "tpl_variants",
    "create_server_button_mask",
    "best_match_multi",
    "match_methods",
    "VisionController",
]
