"""Tek Dash functionality for ARK: Survival Ascended.

Handles timing and state management for Tek Dash input buffering.
"""
import time
import logging
from typing import Optional, Any, Callable

logger = logging.getLogger(__name__)


class TekDashManager:
    """Manages Tek Dash input buffering and timing."""

    def __init__(self, task_queue: Any, input_controller: Optional[Any] = None, overlay: Optional[Any] = None):
        self.task_queue = task_queue
        self.input_controller = input_controller
        self.overlay = overlay

        # Tek dash state
        self._tek_dash_last_press_time: float = 0.0
        self._tek_dash_is_busy: bool = False

    def record_press_timestamp(self) -> None:
        """Record the timestamp when Shift+R was pressed."""
        self._tek_dash_last_press_time = time.perf_counter()

    def get_busy_state(self) -> bool:
        """Check if tek dash is currently busy (within timing window)."""
        if not self._tek_dash_is_busy:
            return False

        elapsed = time.perf_counter() - self._tek_dash_last_press_time
        if elapsed >= 0.2:  # 200ms window
            self._tek_dash_is_busy = False
            return False
        return True

    def start_new_dash(self) -> None:
        """Initialize state for a new tek dash sequence."""
        self._initialize_state()
        self._queue_task()
        self._flash_overlay()

    def _initialize_state(self) -> None:
        """Initialize tek dash state variables."""
        self._tek_dash_is_busy = True
        self._tek_dash_last_press_time = time.perf_counter()

    def _queue_task(self) -> None:
        """Queue tek dash task with task queue."""
        if self.task_queue:
            try:
                task = self._create_task()
                self.task_queue.put_nowait(task)
            except Exception as e:
                logger.error(f"Failed to queue tek dash task: {e}")

    def _flash_overlay(self) -> None:
        """Flash the tek dash overlay indicator."""
        if self.overlay and hasattr(self.overlay, "flash_hotkey_line"):
            try:
                self.overlay.flash_hotkey_line("SHIFT_R", fade_duration_ms=200)
            except Exception as e:
                logger.error(f"Failed to flash tek dash overlay: {e}")

    def _create_task(self) -> Callable[[Any, Any], None]:
        """Create tek dash task function."""
        def task(vision_controller: Any, input_controller: Any) -> None:
            try:
                # Wait for stabilization (input buffer window)
                time.sleep(0.01)

                # Tek dash sequence: Ctrl+V (3 times with timing)
                if self.input_controller:
                    for _ in range(3):
                        try:
                            self.input_controller.key_combo(['ctrl', 'v'], presses=1)
                            time.sleep(0.001)  # 1ms between presses
                        except Exception as e:
                            logger.error(f"Tek dash input error: {e}")

            except Exception as e:
                logger.error(f"Tek dash task error: {e}")

        # Tag the task for identification
        task._gw_task_id = "tek_punch"  # type: ignore
        return task
