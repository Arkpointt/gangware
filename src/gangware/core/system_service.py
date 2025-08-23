"""System Services for ARK: Survival Ascended.

Handles ARK window detection, foreground checking, and system environment detection.
"""
import logging
from typing import Optional

# Import Windows utilities
from ..io import win as w32

logger = logging.getLogger(__name__)


class ArkSystemService:
    """Provides system-level services for ARK: Survival Ascended detection."""

    def __init__(self):
        pass

    def is_ark_active(self) -> bool:
        """Check if ARK: Survival Ascended is the active foreground window.

        Returns:
            True if ARK is the foreground window, False otherwise
        """
        try:
            # Check if foreground executable is ARK
            exe_name = w32.get_foreground_executable_name_lower()
            return "arkascended" in exe_name.lower()

        except Exception as e:
            logger.error(f"Error checking if ARK is active: {e}")
            return False

    def ensure_ark_foreground(self, timeout: float = 3.0) -> bool:
        """Attempt to bring ARK to the foreground.

        Args:
            timeout: Maximum time to wait for ARK to become foreground

        Returns:
            True if ARK becomes foreground within timeout, False otherwise
        """
        try:
            # For now, just check if ARK is already active
            # This could be enhanced with actual window management
            return self.is_ark_active()
        except Exception as e:
            logger.error(f"Error ensuring ARK foreground: {e}")
            return False

    def get_ark_window_rect(self) -> Optional[tuple[int, int, int, int]]:
        """Get ARK window rectangle.

        Returns:
            Window rectangle as (left, top, right, bottom) or None if not found
        """
        try:
            # Get ARK window region from win module
            region = w32.get_ark_window_region()
            if region:
                # Convert from region dict to tuple
                return (region['left'], region['top'],
                       region['left'] + region['width'],
                       region['top'] + region['height'])
            return None

        except Exception as e:
            logger.error(f"Error getting ARK window rect: {e}")
            return None

    def wait_for_keyboard_idle(self, min_idle_seconds: float = 0.2) -> None:
        """Wait for keyboard to be idle for specified duration.

        This helps ensure input commands don't interfere with user typing.

        Args:
            min_idle_seconds: Minimum idle time required
        """
        try:
            # Simple implementation - just wait the specified time
            # This could be enhanced with actual keyboard state monitoring
            import time
            time.sleep(min_idle_seconds)
        except Exception as e:
            logger.error(f"Error waiting for keyboard idle: {e}")

    def log_system_environment(self) -> None:
        """Log system environment information for troubleshooting."""
        try:
            # Log basic system information
            import platform
            logger.info(f"System: {platform.system()} {platform.release()}")
            logger.info(f"Python: {platform.python_version()}")

            # Log ARK window information if available
            ark_region = w32.get_ark_window_region()
            if ark_region:
                logger.info(f"ARK window region: {ark_region}")
            else:
                logger.info("ARK window not found")

        except Exception as e:
            logger.error(f"Error logging system environment: {e}")

    def create_message_queue(self) -> Optional[int]:
        """Create a Windows message queue for the current thread.

        Returns:
            Queue ID if successful, None otherwise
        """
        try:
            # Placeholder implementation
            # This would typically create a Windows message queue
            return 1  # Return a dummy queue ID
        except Exception as e:
            logger.error(f"Error creating message queue: {e}")
            return None
