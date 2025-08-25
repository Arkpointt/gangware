
"""Main Application entry point.

Initializes managers, controllers, threads, and launches the GUI overlay.
"""

import queue
import sys
import os

# Add the src directory to the Python path for proper imports
if getattr(sys, 'frozen', False):
    # Running as executable
    application_path = os.path.dirname(sys.executable)
    src_path = os.path.join(application_path, 'src')
else:
    # Running as script - go up from gangware/main.py to src directory
    application_path = os.path.dirname(os.path.abspath(__file__))  # gangware dir
    src_path = os.path.dirname(application_path)  # src dir

if src_path not in sys.path:
    sys.path.insert(0, src_path)

from gangware.core.config import ConfigManager
from gangware.core.state import StateManager
from gangware.core.hotkey_manager import HotkeyManager
from gangware.core.worker import Worker
from gangware.core.resolution_monitor import ResolutionMonitor
from gangware.vision.controller import VisionController
from gangware.io.controls import InputController
from gangware.core.logging_setup import setup_logging
from gangware.core.health import start_health_monitor
from gangware.features.autosim import AutoSim



def main() -> None:
    """Start managers, threads and launch the overlay UI.

    Keeps the entry point minimal; configuration and state are loaded,
    threads are started, and an optional UI demo task can be queued.
    """

    # Ensure a Qt application exists before any potential QWidget usage during imports
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    config_manager = ConfigManager()
    # Initialize logging very early and store session path for support
    session_dir = setup_logging(config_manager)
    try:
        # Save path to config for easy support reference (not persisted every run)
        config_manager.config["DEFAULT"]["last_log_session"] = str(session_dir)
        config_manager.save()
    except Exception:
        pass

    # Install a global exception hook to log unhandled exceptions
    import sys as _sys
    import logging as _logging

    def _excepthook(exc_type, exc, tb):
        _logging.getLogger(__name__).exception("Unhandled exception:", exc_info=(exc_type, exc, tb))
        # Delegate to default hook after logging
        _sys.__excepthook__(exc_type, exc, tb)

    _sys.excepthook = _excepthook
    state_manager = StateManager()

    # Check for calibration and essential settings
    calibration_complete = (
        config_manager.get("calibration_complete", fallback="False") == "True"
    )
    essential_keys = ["resolution", "log_level", "ui_theme"]
    missing_settings = [k for k in essential_keys if not config_manager.get(k)]

    # Import overlay after QApplication is guaranteed to exist
    from gangware.gui.overlay import OverlayWindow

    if not calibration_complete or missing_settings:
        reason = []
        if not calibration_complete:
            reason.append("Calibration has not been completed.")
        if missing_settings:
            reason.append(f"Missing settings: {', '.join(missing_settings)}.")

        message = "Calibration Mode Required:\n" + "\n".join(reason)
        overlay = OverlayWindow(calibration_mode=True, message=message)
    else:
        overlay = OverlayWindow()

    # Initialize controllers
    vision_controller = VisionController()
    input_controller = InputController()

    # Set up the task queue
    task_queue: queue.Queue = queue.Queue()

    # Start hotkey listener thread (pass overlay for status updates / calibration prompts)
    hotkey_manager = HotkeyManager(
        config_manager, task_queue, state_manager,
        input_controller=input_controller, overlay=overlay
    )
    # Connect overlay shortcuts before starting threads to ensure signals are handled
    overlay.on_recalibrate(lambda: hotkey_manager.request_recalibration())
    overlay.on_start(lambda: hotkey_manager.allow_calibration_start())
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

    # Start resolution monitor thread
    resolution_monitor = ResolutionMonitor(config_manager, overlay, interval=10.0)
    resolution_monitor.start()

    # Prepare autosim, start only when user presses Utilities Start or F11
    from PyQt6.QtCore import QTimer
    try:
        autosim = AutoSim(state_manager, config_manager, overlay)

        # Create periodic timer for autosim.tick() to handle resume signals
        autosim_tick_timer = QTimer()
        autosim_tick_timer.timeout.connect(autosim.tick)
        autosim_tick_timer.start(200)  # Check every 200ms for resume signals

        def _handle_autosim_start():
            try:
                # Get server number from overlay input
                server_number = overlay.get_server_number() if hasattr(overlay, "get_server_number") else ""

                # Validate server number is provided and not empty
                if not server_number.strip():
                    # Show warning and keep overlay visible
                    overlay.set_status("WARNING: Please enter a server number before starting AutoSim")
                    return

                # Validate server number is numeric (basic validation)
                try:
                    int(server_number.strip())
                except ValueError:
                    overlay.set_status("WARNING: Server number must be a valid number")
                    return

                # Hide overlay and start autosim
                overlay.set_visible(False)
                # Start autosim after 3 seconds
                QTimer.singleShot(3000, lambda: autosim.start(server_number))
            except Exception:
                # If something goes wrong, show error and keep overlay visible
                overlay.set_status("ERROR: Failed to start AutoSim")
                return

        def _handle_autosim_stop():
            try:
                autosim.stop()
                overlay.set_visible(True)  # Show overlay when autosim stops
            except Exception:
                pass

        if hasattr(overlay, "on_autosim_start"):
            overlay.on_autosim_start(_handle_autosim_start)
        if hasattr(overlay, "on_autosim_stop"):
            overlay.on_autosim_stop(_handle_autosim_stop)

        # Clean up timer on app shutdown
        def cleanup_autosim():
            autosim_tick_timer.stop()
            autosim.stop()
        app.aboutToQuit.connect(cleanup_autosim)
    except Exception:
        pass

    # Health monitoring (lightweight, configurable)
    try:
        hm_enabled = config_manager.get("health_monitor", fallback="True")
        if str(hm_enabled).strip().lower() in ("true", "1", "yes", "on"):
            # Ensure a non-None, clean string before converting to float (satisfies Pylance typing)
            interval_str: str = config_manager.get("health_interval_seconds", fallback="5") or "5"
            interval = float(interval_str.strip())
            start_health_monitor(
                config_manager,
                session_dir,
                hotkey_manager,
                worker,
                task_queue,
                interval_seconds=interval,
            )
    except Exception:
        pass


    # Optional UI demo task
    ui_demo = config_manager.get("ui_demo", fallback="False") == "True"
    if ui_demo:
        def demo_task(vision, input_ctrl):
            import time

            for i in range(5):
                overlay.set_status(f"Demo step {i + 1}/5")
                time.sleep(1)

            overlay.set_status("Demo complete")

        task_queue.put(demo_task)

    # Show overlay and start Qt event loop (blocks until closed)
    overlay.show()
    app.exec()


if __name__ == "__main__":
    main()
