"""
Combat Macros
Executes combat-related macros (e.g., Tek Punch).
"""


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


def execute_medbrew_hot_toggle(input_controller):
    """Toggle a slow heal by using '0' once (placeholder for future stateful toggle).

    This is distinct from burst and kept minimal to avoid code duplication warnings.
    """
    print("Executing Medbrew HOT toggle (0 x1)...")
    try:
        input_controller.press_key('0', presses=1)
    except Exception as e:
        print(f"Medbrew HOT toggle error: {e}")
    finally:
        print("Medbrew HOT toggle executed.")
