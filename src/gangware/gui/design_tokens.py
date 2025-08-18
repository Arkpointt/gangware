"""Design tokens for Gangware UI (single source of truth).
Do not change values here without updating the blueprint and tests.
"""

# Colors
CYAN = "#00DDFF"
ORANGE = "#FFB800"
TEXT_DEFAULT = "#D5DCE3"
STATUS_OK = "#31F37A"
BG_CARD_RGBA = "rgba(10,20,30,0.85)"
BG_SECTION_RGBA = "rgba(18,28,40,0.60)"
BORDER_CYAN = "rgba(0,221,255,0.40)"
BORDER_SECTION = "rgba(0,221,255,0.28)"
DIVIDER = "rgba(0,221,255,0.28)"
KEYCAP_BG = "rgba(15,30,45,0.92)"
KEYCAP_BORDER = "rgba(0,221,255,0.45)"
STATUSBOX_BG = "rgba(15,30,45,0.90)"
STATUSBOX_BORDER = "rgba(255,255,255,0.20)"

# Radii (pixels)
RADIUS_CARD = 14
RADIUS_SECTION = 10
RADIUS_KEYCAP = 10
RADIUS_TAB = 8
RADIUS_PRIMARY = 10

# Fonts
FONT_STACK = "'Orbitron', 'Segoe UI', Arial, sans-serif"
TITLE_SIZE = 34
SECTION_SIZE = 18
FONT_SIZE = 11  # slightly larger to match 0.66 scale

# Spacing & sizes (scaled ~0.6)
TAB_MIN_HEIGHT = 26  # was 40
TAB_PADDING_Y = 6    # was 8
TAB_PADDING_X = 11   # was 16
KEYCAP_PADDING_Y = 5 # was 6
KEYCAP_PADDING_X = 9 # was 12
SMALLBTN_PADDING_Y = 5  # was 6
SMALLBTN_PADDING_X = 9  # was 12
