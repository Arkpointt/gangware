"""Medbrew Hot timing functionality for ARK: Survival Ascended.

Handles automatic medbrew timing and hot key press management.
"""
import time
import threading
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)


class MedbrewHotManager:
    """Manages automatic medbrew hot timing."""

    def __init__(self, input_controller: Optional[Any] = None, overlay: Optional[Any] = None):
        self.input_controller = input_controller
        self.overlay = overlay

        # Hot thread state
        self._hot_thread: Optional[threading.Thread] = None
        self._hot_stop_event = threading.Event()

        # Constants
        self.HOTKEY_SHIFT_E = "SHIFT_E"

    def start_hot_thread(self) -> None:
        """Start the hot thread for medbrew timing."""
        if self._hot_thread and self._hot_thread.is_alive():
            return  # Already running

        try:
            self._hot_stop_event.clear()
            start_time = time.perf_counter()
            self._hot_thread = threading.Thread(
                target=self._hot_thread_loop,
                args=(start_time,),
                daemon=True
            )
            self._hot_thread.start()
        except Exception as e:
            logger.error(f"Failed to start hot thread: {e}")

    def stop_hot_thread(self) -> None:
        """Stop the hot thread."""
        try:
            self._hot_stop_event.set()
            if self._hot_thread and self._hot_thread.is_alive():
                self._hot_thread.join(timeout=1.0)
        except Exception as e:
            logger.error(f"Error stopping hot thread: {e}")

    def _hot_thread_loop(self, start: float) -> None:
        """Main loop for hot thread timing."""
        total_duration = 22.5  # seconds
        interval = 1.5  # seconds between presses
        presses = int(total_duration / interval) + 1

        try:
            for i in range(presses):
                if self._hot_stop_event.is_set():
                    break

                target = start + i * interval
                self._hot_wait_until(target)

                if self._hot_stop_event.is_set():
                    break

                try:
                    if self.input_controller:
                        self.input_controller.press_key('0', presses=1)
                except Exception as e:
                    logger.error(f"Hot thread key press error: {e}")

        finally:
            self._hot_on_finish()

    def _hot_wait_until(self, deadline: float) -> None:
        """Wait until the specified deadline time."""
        while not self._hot_stop_event.is_set():
            now = time.perf_counter()
            remain = deadline - now
            if remain <= 0:
                break
            time.sleep(min(0.05, remain))

    def _hot_on_finish(self) -> None:
        """Called when hot thread finishes."""
        # Clear active line with smooth fade animation
        try:
            if self.overlay and hasattr(self.overlay, "clear_hotkey_line_active"):
                self.overlay.clear_hotkey_line_active(
                    self.HOTKEY_SHIFT_E,
                    fade_duration_ms=2400
                )
        except Exception as e:
            logger.error(f"Error clearing hotkey line: {e}")

    def is_hot_thread_active(self) -> bool:
        """Check if hot thread is currently active."""
        return (self._hot_thread is not None and
                self._hot_thread.is_alive() and
                not self._hot_stop_event.is_set())

    def toggle_hot_thread(self) -> None:
        """Toggle hot thread on/off."""
        if self.is_hot_thread_active():
            self.stop_hot_thread()
        else:
            self.start_hot_thread()
