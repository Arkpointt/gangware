"""
Main Application Entry Point
Initializes managers, controllers, threads, and launches the GUI overlay.
"""

import queue
from core.config import ConfigManager
from core.state import StateManager
from core.hotkey_manager import HotkeyManager
from core.worker import Worker
from controllers.vision import VisionController
from controllers.controls import InputController
from gui.overlay import OverlayWindow


def main() -> None:
	"""Start managers, threads and launch the overlay UI.

	Keeps the entry point minimal; configuration and state are loaded,
	threads are started, and an optional UI demo task can be queued.
	"""

	config_manager = ConfigManager()
	state_manager = StateManager()

	# Check for calibration and essential settings
	calibration_complete = (
		config_manager.get('calibration_complete', fallback='False') == 'True'
	)
	essential_keys = ['resolution', 'log_level', 'ui_theme']
	missing_settings = [k for k in essential_keys if not config_manager.get(k)]

	if not calibration_complete or missing_settings:
		reason = []
		if not calibration_complete:
			reason.append('Calibration has not been completed.')
		if missing_settings:
			reason.append(f"Missing settings: {', '.join(missing_settings)}.")

		message = 'Calibration Mode Required:\n' + '\n'.join(reason)
		overlay = OverlayWindow(calibration_mode=True, message=message)
		overlay.show()
		return

	# Initialize controllers
	vision_controller = VisionController()
	input_controller = InputController()

	# Set up the task queue
	task_queue: queue.Queue = queue.Queue()

	# Launch the GUI overlay
	overlay = OverlayWindow()

	# Start hotkey listener thread
	hotkey_manager = HotkeyManager(config_manager, task_queue, state_manager)
	hotkey_manager.start()

	# Start worker thread (pass overlay for status updates)
	worker = Worker(
		config_manager,
		state_manager,
		vision_controller,
		input_controller,
		task_queue,
		status_callback=overlay,
	)
	worker.start()

	# Optional UI demo task
	ui_demo = config_manager.get('ui_demo', fallback='False') == 'True'
	if ui_demo:
		def demo_task(vision, input_ctrl):
			import time

			for i in range(5):
				overlay.set_status(f'Demo step {i + 1}/5')
				time.sleep(1)

			overlay.set_status('Demo complete')

		task_queue.put(demo_task)

	# Show overlay (blocks until closed)
	overlay.show()


if __name__ == '__main__':
	main()
