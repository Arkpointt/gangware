"""
Combat Macros
Executes combat-related macros (e.g., Tek Punch).
"""

import time
from typing import Optional

# The macro functions can optionally receive an overlay-like object that exposes
# set_hotkey_line_active(hotkey: str) and clear_hotkey_line_active(hotkey: str, fade_duration_ms: int)
# We pass overlay=None by default to avoid tight coupling.


def execute_tek_punch(input_controller):
    """
    Executes the Tek Punch macro using input automation.
    Args:
        input_controller: Instance of InputController for input automation.
    """
    print("Executing Tek Punch macro...")
    # Example: Simulate key press for Tek Punch (key is a placeholder)
    input_controller.type_text('T')  # Replace 'T' with actual key
    input_controller.click()         # Simulate punch
    print("Tek Punch executed.")


def execute_medbrew_burst(input_controller):
    """
    Executes the Medbrew Burst: spam hotbar slot 0 five times quickly.

    Assumes Medbrews are bound to the '0' hotbar slot in-game.
    """
    print("Executing Medbrew Burst macro (0 x5)...")
    try:
        # Press '0' five times with a short interval. Adjust interval if needed.
        input_controller.press_key('0', presses=5, interval=0.06)
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
