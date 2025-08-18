"""Control System Module
Handles all input automation tasks.
"""

import pydirectinput


class InputController:
    """Main class for mouse, keyboard, and input automation."""

    def __init__(self):
        # Initialization if needed
        pass

    def move_mouse(self, x, y):
        """
        Moves mouse to (x, y).
        """
        pydirectinput.moveTo(x, y)

    def click(self):
        """
        Performs a left mouse click.
        """
        pydirectinput.click(button='left')

    def click_button(self, button: str, presses: int = 1, interval: float = 0.05):
        """Click a specific mouse button one or more times.

        Args:
            button: 'left', 'right', or 'middle'. Other values (e.g., 'xbutton1')
                    are attempted but may not be supported by pydirectinput.
            presses: Number of clicks.
            interval: Delay between clicks.
        """
        try:
            pydirectinput.click(button=button, clicks=presses, interval=interval)
        except Exception:
            # Fallback: attempt default click if unsupported
            for _ in range(max(1, presses)):
                pydirectinput.click(button='left')
                if interval > 0:
                    try:
                        import time as _t
                        _t.sleep(interval)
                    except Exception:
                        pass

    def mouse_down(self, button: str = 'left'):
        """Press and hold a mouse button (left/right/middle)."""
        pydirectinput.mouseDown(button=button)

    def mouse_up(self, button: str = 'left'):
        """Release a previously held mouse button (left/right/middle)."""
        pydirectinput.mouseUp(button=button)

    def type_text(self, text):
        """
        Types the given text.
        """
        pydirectinput.write(text)

    def press_key(self, key: str, presses: int = 1, interval: float = 0.05):
        """Press a key one or more times with an optional interval between presses.

        Args:
            key: The key to press (e.g., '0', 'e', 'f1').
            presses: Number of times to press the key.
            interval: Delay in seconds between presses.
        """
        # pydirectinput mirrors PyAutoGUI's API and supports press with repeats.
        pydirectinput.press(key, presses=presses, interval=interval)
