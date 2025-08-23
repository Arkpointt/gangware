"""Armor swapping task factory for ARK: Survival Ascended.

Creates task functions for different armor swapping operations.
"""
import logging
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)


class ArmorTaskFactory:
    """Factory for creating armor swapping task functions."""

    def __init__(self, input_controller: Optional[Any] = None):
        self.input_controller = input_controller

    def create_equip_armor_task(self, armor_set: str) -> Callable[[Any, Any], None]:
        """Create a task function for equipping a specific armor set.

        Args:
            armor_set: The armor set identifier (e.g., 'flak', 'tek', 'riot')

        Returns:
            Task function that can be queued for execution
        """
        def task(vision_controller: Any, input_controller: Any) -> None:
            try:
                # Use the provided input controller or fall back to instance controller
                ic = input_controller or self.input_controller
                if not ic:
                    logger.error("No input controller available for armor task")
                    return

                # Import and execute armor swapping
                from .macros import armor_swapper
                armor_swapper.execute(vision_controller, ic, armor_set)

            except Exception as e:
                logger.error(f"Armor equip task failed for {armor_set}: {e}")

        # Tag the task for identification
        task._gw_task_id = f"equip_armor_{armor_set}"  # type: ignore
        return task

    def create_medbrew_hot_toggle_task(self, medbrew_hot_manager: Any) -> Callable[[Any, Any], None]:
        """Create a task function for toggling medbrew hot timing.

        Args:
            medbrew_hot_manager: The MedbrewHotManager instance

        Returns:
            Task function that can be queued for execution
        """
        def task(vision_controller: Any, input_controller: Any) -> None:
            try:
                if medbrew_hot_manager and hasattr(medbrew_hot_manager, 'toggle_hot_thread'):
                    medbrew_hot_manager.toggle_hot_thread()
                else:
                    logger.error("Invalid medbrew hot manager provided")

            except Exception as e:
                logger.error(f"Medbrew hot toggle task failed: {e}")

        # Tag the task for identification
        task._gw_task_id = "medbrew_hot_toggle"  # type: ignore
        return task

    @staticmethod
    def create_general_combat_task(combat_action: str, config_manager: Any) -> Callable[[Any, Any], None]:
        """Create a general combat task function.

        Args:
            combat_action: The combat action to execute
            config_manager: Configuration manager instance

        Returns:
            Task function that can be queued for execution
        """
        def task(vision_controller: Any, input_controller: Any) -> None:
            try:
                # Import and execute combat action
                from .macros import combat

                if combat_action == "tek_punch":
                    combat.execute_tek_punch(input_controller, config_manager)
                elif combat_action == "medbrew_burst":
                    combat.execute_medbrew_burst(input_controller)
                elif combat_action == "medbrew_hot_toggle":
                    combat.execute_medbrew_hot_toggle(input_controller)
                else:
                    logger.warning(f"Unknown combat action: {combat_action}")

            except Exception as e:
                logger.error(f"Combat task failed for {combat_action}: {e}")

        # Tag the task for identification
        task._gw_task_id = f"combat_{combat_action}"  # type: ignore
        return task
