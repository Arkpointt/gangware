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
        Performs a mouse click.
        """
        pydirectinput.click()

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
