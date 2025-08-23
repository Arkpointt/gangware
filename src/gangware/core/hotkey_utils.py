"""Hotkey Utility Functions for Gangware.

Common utility functions for hotkey management, token parsing, and display formatting.
"""
from typing import Optional, Any


def get_token(config_manager: Optional[Any], key_name: str, default_token: str) -> str:
    """Get a hotkey token from config, with fallback handling.

    Args:
        config_manager: Configuration manager instance
        key_name: Configuration key name to lookup
        default_token: Fallback token if key not found

    Returns:
        Formatted token string (e.g., 'key_i', 'mouse_left')
    """
    try:
        token = None
        if config_manager is not None:
            token = config_manager.get(key_name)
        if not token:
            return default_token
        t = str(token).strip().lower()
        if t.startswith('key_') or t.startswith('mouse_'):
            return t
        # Back-compat: raw key like 'i'
        if len(t) > 0:
            return f"key_{t}"
        return default_token
    except Exception:
        return default_token


def token_display(token: str) -> str:
    """Human-friendly label for overlay messages.

    Args:
        token: Raw token string (e.g., 'key_i', 'mouse_left')

    Returns:
        Human-readable display string (e.g., 'I', 'LEFT')
    """
    t = (token or '').lower()
    if t.startswith('key_'):
        name = t[4:]
        return name.upper()
    if t == 'mouse_xbutton1':
        return 'XBUTTON1'
    if t == 'mouse_xbutton2':
        return 'XBUTTON2'
    if t == 'mouse_middle':
        return 'MIDDLE'
    if t == 'mouse_right':
        return 'RIGHT'
    if t == 'mouse_left':
        return 'LEFT'
    return token.upper()


def format_hotkey_status(inventory_token: str, tek_token: str) -> str:
    """Format hotkey status for display.

    Args:
        inventory_token: Inventory hotkey token
        tek_token: Tek cancel hotkey token

    Returns:
        Formatted status string
    """
    inv_display = token_display(inventory_token)
    tek_display = token_display(tek_token)
    return f"Inventory: {inv_display} | Tek Cancel: {tek_display}"


def validate_token_format(token: str) -> bool:
    """Validate that a token is properly formatted.

    Args:
        token: Token string to validate

    Returns:
        True if token is valid format
    """
    if not token:
        return False

    t = token.lower().strip()

    # Valid formats: key_*, mouse_*
    if t.startswith('key_') or t.startswith('mouse_'):
        return len(t) > 4  # Must have content after prefix

    return False
