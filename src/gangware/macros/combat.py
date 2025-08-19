"""
Combat Macros
Executes combat-related macros (e.g., Tek Punch).
"""

import time
from typing import Optional

# The macro functions can optionally receive an overlay-like object that exposes
# set_hotkey_line_active(hotkey: str) and clear_hotkey_line_active(hotkey: str, fade_duration_ms: int)
# We pass overlay=None by default to avoid tight coupling.


# Smart cooldown timestamp for Tek Punch (allow immediate retrigger once complete)
_last_tek_punch_ready_at: float = 0.0


def _resolve_cancel_key(config_manager) -> str:
    """Return a pydirectinput-friendly key from config token like 'key_e'.

    Falls back to 'e' if unavailable.
    """
    try:
        token = None
        if config_manager is not None:
            token = config_manager.get("tek_punch_cancel_key")
        if not token:
            return 'e'
        token = str(token).strip()
        if token.startswith('key_'):
            return token[4:].lower()
        # Mouse tokens are not reliably supported by pydirectinput for extra buttons.
        # Fall back to a reasonable default if a mouse token was captured.
        return 'e'
    except Exception:
        return 'e'


def execute_tek_punch(input_controller, config_manager=None):
    """Perform Tek Punch with a timestamp-based smart cooldown.

    Sequence:
    - Hold right-click 700ms
    - Release right-click
    - Wait 100ms
    - Double-tap cancel key from config (DEFAULT.tek_punch_cancel_key)

    Cooldown: Uses a timestamp so calls during an active sequence are ignored,
    but the macro is immediately available again after completion.
    """
    global _last_tek_punch_ready_at
    now = __import__('time').perf_counter()
    if now < _last_tek_punch_ready_at:
        # Still within the active window from a previous run; skip
        print("Tek Punch skipped due to active cooldown window.")
        return

    cancel_key = _resolve_cancel_key(config_manager)

    print("Executing Tek Punch macro...")
    try:
        import time
        # Hold right-click for 700 ms
        input_controller.mouse_down('right')
        time.sleep(0.7)
        input_controller.mouse_up('right')
        # Small delay
        time.sleep(0.1)
        # Double-tap cancel key quickly
        input_controller.press_key(cancel_key, presses=2, interval=0.06)
    except Exception as e:
        print(f"Tek Punch error: {e}")
    finally:
        # Mark ready timestamp at actual completion time
        _last_tek_punch_ready_at = __import__('time').perf_counter()
        print("Tek Punch executed.")


def execute_medbrew_burst(input_controller):
    """
    Executes the Medbrew Burst: spam hotbar slot 0 five times quickly.

    Assumes Medbrews are bound to the '0' hotbar slot in-game.
    """
    print("Executing Medbrew Burst macro (0 x5)...")
    try:
        # Press '0' five times with ~200ms between presses for reliability.
        input_controller.press_key('0', presses=5, interval=0.20)
    except Exception as e:
        print(f"Medbrew Burst error: {e}")
    finally:
        print("Medbrew Burst executed.")


def execute_medbrew_hot_toggle(input_controller, overlay: Optional[object] = None):
    """Heal-over-time effect: press '0' every 1.5s for 22.5s.

    Behavior:
    - Immediately marks Shift+E line active (green) in the overlay if available.
    - Presses '0' at 0.0s, 1.5s, ..., up to 22.5s (inclusive: 16 presses).
    - After the loop, requests a slow fade-out of the Shift+E line.
    """
    HOTKEY_LABEL = "Shift+E"
    total_duration = 22.5
    interval = 1.5
    presses = int(total_duration / interval) + 1  # include t=0 and t=22.5 -> 16

    print(f"Executing Medbrew HOT over-time: 0 every {interval}s for {total_duration}s...")

    # Mark line active in overlay
    try:
        if overlay and hasattr(overlay, "set_hotkey_line_active"):
            overlay.set_hotkey_line_active(HOTKEY_LABEL)
    except Exception:
        pass

    try:
        start = time.perf_counter()
        for i in range(presses):
            # Schedule each press at start + i*interval
            target = start + i * interval
            now = time.perf_counter()
            delay = target - now
            if delay > 0:
                time.sleep(delay)
            try:
                input_controller.press_key('0', presses=1)
            except Exception as e:
                print(f"Medbrew HOT press error at {i}: {e}")
    except Exception as e:
        print(f"Medbrew HOT error: {e}")
    finally:
        print("Medbrew HOT completed.")
        try:
            if overlay and hasattr(overlay, "clear_hotkey_line_active"):
                # Slow fade to match the requested behavior
                overlay.clear_hotkey_line_active(HOTKEY_LABEL, fade_duration_ms=2400)
        except Exception:
            pass
