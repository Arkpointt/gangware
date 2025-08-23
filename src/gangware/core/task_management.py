"""Task Management Service for Gangware.

Handles task queue operations, task creation, and pending task detection.
"""
import logging
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)


class TaskManager:
    """Manages task queue operations and task creation."""

    def __init__(self, task_queue: Any, overlay: Optional[Any] = None):
        self.task_queue = task_queue
        self.overlay = overlay

    def handle_macro_hotkey(self, task_callable: Callable[[object, object], None],
                           hotkey_label: Optional[str]) -> None:
        """Handle macro hotkey by queuing task and providing visual feedback.

        Args:
            task_callable: The task function to execute
            hotkey_label: Label for overlay feedback (e.g., "F2", "SHIFT_Q")
        """
        try:
            # Queue the task
            self.task_queue.put_nowait(task_callable)

            # Provide visual feedback
            if self.overlay and hotkey_label:
                try:
                    if hasattr(self.overlay, "flash_hotkey_line"):
                        self.overlay.flash_hotkey_line(hotkey_label)
                except Exception as e:
                    logger.error(f"Error flashing hotkey line for {hotkey_label}: {e}")

        except Exception as e:
            logger.error(f"Error handling macro hotkey {hotkey_label}: {e}")

    def is_task_pending(self, predicate: Callable[[object], bool]) -> bool:
        """Check if any task matching the predicate is pending in the queue.

        Args:
            predicate: Function to test each task in queue

        Returns:
            True if matching task found, False otherwise
        """
        try:
            q = self.task_queue
            if not q or not hasattr(q, 'queue'):
                return False

            # Check all items in queue without removing them
            for item in list(q.queue):
                if predicate(item):
                    return True
            return False
        except Exception as e:
            logger.error(f"Error checking pending tasks: {e}")
            return False

    def queue_task(self, task: Callable[[object, object], None]) -> None:
        """Queue a task for execution.

        Args:
            task: Task function to queue
        """
        try:
            self.task_queue.put_nowait(task)
        except Exception as e:
            logger.error(f"Error queuing task: {e}")

    def queue_tek_dash_task(self, tek_task: Callable[[object, object], None]) -> None:
        """Queue the tek punch task and flash the overlay if available."""
        try:
            self.task_queue.put_nowait(tek_task)
            self.flash_tek_dash_overlay("SHIFT_R")
        except Exception as e:
            logger.error(f"Error queuing tek dash task: {e}")

    def flash_tek_dash_overlay(self, hotkey_label: str) -> None:
        """Flash the hotkey line in the overlay for tek dash feedback."""
        if self.overlay and hasattr(self.overlay, "flash_hotkey_line"):
            try:
                self.overlay.flash_hotkey_line(hotkey_label)
            except Exception as e:
                logger.error(f"Error flashing overlay for {hotkey_label}: {e}")

    @staticmethod
    def is_tek_punch_task(task_obj: object) -> bool:
        """Check if a task object is a Tek Punch task."""
        try:
            if callable(task_obj) and getattr(task_obj, "_gw_task_id", "") == "tek_punch":
                return True
            if isinstance(task_obj, dict):
                label = str(task_obj.get("label", "")).lower()
                name = str(task_obj.get("name", "")).lower()
                if "tek" in label and "punch" in label:
                    return True
                if "tek" in name and "punch" in name:
                    return True
        except Exception:
            pass
        return False

    def create_search_and_type_task(self, text: str) -> Callable[[object, object], None]:
        """Create a task for searching and typing text.

        Args:
            text: Text to search for and type

        Returns:
            Task function that can be queued
        """
        def task(vision_controller: object, input_controller: object) -> None:
            try:
                # This would implement search and type functionality
                # For now, just log the action
                logger.info(f"Search and type task: {text}")

                # Example implementation would:
                # 1. Use vision_controller to find search field
                # 2. Use input_controller to click and type
                # 3. Handle any errors gracefully

            except Exception as e:
                logger.error(f"Search and type task failed for '{text}': {e}")

        # Tag the task for identification
        task._gw_task_id = f"search_and_type_{text}"  # type: ignore
        return task
