
"""
Main Application Entry Point
Initializes managers, controllers, threads, and launches the GUI overlay.
"""

import sys
import queue
from core.config import ConfigManager
from core.state import StateManager
from core.hotkey_manager import HotkeyManager
from core.worker import Worker
from controllers.vision import VisionController
from controllers.controls import InputController
from gui.overlay import OverlayWindow

def main():
	# Initialize configuration and state
	config_manager = ConfigManager()
	state_manager = StateManager()

	# Initialize controllers
	vision_controller = VisionController()
	input_controller = InputController()

	# Set up the task queue
	task_queue = queue.Queue()

	# Initialize and start HotkeyManager thread
	hotkey_manager = HotkeyManager(config_manager, task_queue, state_manager)
	hotkey_manager.start()

	# Initialize and start Worker thread
	worker = Worker(config_manager, state_manager, vision_controller, input_controller, task_queue)
	worker.start()

	# Launch the GUI overlay
	overlay = OverlayWindow()
	overlay.show()

if __name__ == "__main__":
	main()
