# Configuration

This document summarizes configuration precedence and key toggles per the v6.5 Engineering Blueprint.

## Precedence

1. Environment variables
2. %APPDATA%/Gangware/config.ini
3. Repository defaults (e.g., src defaults)

Avoid hardcoding constants in feature code; prefer config values with safe defaults.

## Feature Flags

Feature flags live in `configs/feature_flags.yml` (optional). Each flag should document:
- Default
- Owner
- Rollback plan

## Environment Variables

Vision/Performance:
- `GW_VISION_PERF=1` — emit performance timings from VisionController
- `GW_VISION_FAST_ONLY=1` — restrict template search to fast scales (used selectively)
- `GW_VISION_ROI="abs_left,abs_top,abs_width,abs_height"` — absolute ROI for vision
- `GW_INV_SUBROI="rel_left,rel_top,rel_width,rel_height"` — sub-ROI inside inventory

AutoSim (Connection Failed detection):
- `GW_CF_DEBUG=1` — log template detection scores
- `GW_MODAL_DEBUG=1` — log modal heuristic scores
- `GW_CF_ROIS="x1,y1,x2,y2;..."` — fractional ROIs for popup scanning

Armor Search/Matching:
- `GW_ITEM_MATCH_WINDOW=0.7` — seconds to scan for item match before advancing

## Config Keys (config.ini)

Core/UI:
- `ui_theme`, `log_level`, `resolution`

Calibration:
- `inventory_key` — token like `key_i`, `mouse_xbutton2`
- `tek_punch_cancel_key` — token used in Tek punch macro
- `calibration_complete` — `True` once keys captured

Coordinates (captured via overlay F7):
- `coord_main_menu`, `coord_select_game`, `coord_search_box`, `coord_join_game`, `coord_back`, `coord_battleye_symbol`
- `search_bar_coords` — absolute coordinates of search box (replaces template)

ROI:
- `vision_roi` — relative ROI (`rel_left,rel_top,rel_width,rel_height`) used to derive `GW_VISION_ROI`

Search Template (legacy path kept for compatibility, prefer coordinates):
- `search_bar_template` — absolute path to search bar template image

## Notes

- The overlay displays ROI/coordinate status for quick verification.
- Prefer coordinates for frequently-interacted UI (e.g., search bar) for speed; keep templates as fallback.
- When applying `vision_roi` from config, convert to absolute with monitor bounds at feature start (not at app startup) to avoid misalignment.
