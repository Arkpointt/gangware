
"""
Control System Module
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
