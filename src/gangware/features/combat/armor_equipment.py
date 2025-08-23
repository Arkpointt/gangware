"""Armor Equipment Service for ARK: Survival Ascended.

Handles complex armor swapping tasks with vision-based template matching
and multi-step equipment sequences.
"""
import logging
from typing import Callable, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class ArmorEquipmentService:
    """Service for creating complex armor equipment task functions."""

    def __init__(self, config_manager: Any, input_controller: Optional[Any] = None):
        self.config_manager = config_manager
        self.input_controller = input_controller

    def create_flak_fullset_task(self) -> Callable[[object, object], None]:
        """Create task function for equipping full flak armor set.

        This is a complex multi-step process that:
        1. Opens inventory using vision template matching
        2. Locates each armor piece using templates
        3. Equips pieces in proper sequence
        4. Handles errors and retries

        Returns:
            Task function that can be queued for execution
        """
        def task(vision_controller: Any, input_controller: Any) -> None:
            try:
                logger.info("Starting flak armor equipment task")

                # Use provided input controller or fall back to service controller
                ic = input_controller or self.input_controller
                if not ic:
                    logger.error("No input controller available for flak equipment")
                    return

                # Step 1: Open inventory
                if not self._open_inventory(vision_controller, ic):
                    logger.error("Failed to open inventory for flak equipment")
                    return

                # Step 2: Equip armor pieces in sequence
                armor_pieces = ["helmet", "chestpiece", "leggings", "gauntlets", "boots"]
                for piece in armor_pieces:
                    template_path = f"assets/flak_{piece}_template.png"
                    if not self._equip_armor_piece(vision_controller, ic, template_path, piece):
                        logger.warning(f"Failed to equip flak {piece}, continuing...")

                # Step 3: Close inventory
                self._close_inventory(ic)

                logger.info("Flak armor equipment task completed")

            except Exception as e:
                logger.error(f"Flak armor equipment task failed: {e}")

        # Tag the task for identification
        task._gw_task_id = "equip_flak_fullset"  # type: ignore
        return task

    def create_tek_fullset_task(self) -> Callable[[object, object], None]:
        """Create task function for equipping full tek armor set.

        Similar to flak but with tek-specific templates and sequence.

        Returns:
            Task function that can be queued for execution
        """
        def task(vision_controller: Any, input_controller: Any) -> None:
            try:
                logger.info("Starting tek armor equipment task")

                # Use provided input controller or fall back to service controller
                ic = input_controller or self.input_controller
                if not ic:
                    logger.error("No input controller available for tek equipment")
                    return

                # Step 1: Open inventory
                if not self._open_inventory(vision_controller, ic):
                    logger.error("Failed to open inventory for tek equipment")
                    return

                # Step 2: Equip tek armor pieces in sequence
                armor_pieces = ["helmet", "chestpiece", "leggings", "gauntlets", "boots"]
                for piece in armor_pieces:
                    template_path = f"assets/tek_{piece}_template.png"
                    if not self._equip_armor_piece(vision_controller, ic, template_path, piece):
                        logger.warning(f"Failed to equip tek {piece}, continuing...")

                # Step 3: Close inventory
                self._close_inventory(ic)

                logger.info("Tek armor equipment task completed")

            except Exception as e:
                logger.error(f"Tek armor equipment task failed: {e}")

        # Tag the task for identification
        task._gw_task_id = "equip_tek_fullset"  # type: ignore
        return task

    def create_mixed_fullset_task(self) -> Callable[[object, object], None]:
        """Create task function for equipping mixed armor set.

        Combines different armor types for optimal protection/utility.

        Returns:
            Task function that can be queued for execution
        """
        def task(vision_controller: Any, input_controller: Any) -> None:
            try:
                logger.info("Starting mixed armor equipment task")

                # Use provided input controller or fall back to service controller
                ic = input_controller or self.input_controller
                if not ic:
                    logger.error("No input controller available for mixed equipment")
                    return

                # Step 1: Open inventory
                if not self._open_inventory(vision_controller, ic):
                    logger.error("Failed to open inventory for mixed equipment")
                    return

                # Step 2: Equip mixed armor pieces (example configuration)
                mixed_config = [
                    ("tek_helmet_template.png", "helmet"),
                    ("flak_chestpiece_template.png", "chestpiece"),
                    ("tek_leggings_template.png", "leggings"),
                    ("flak_gauntlets_template.png", "gauntlets"),
                    ("tek_boots_template.png", "boots")
                ]

                for template_name, piece in mixed_config:
                    template_path = f"assets/{template_name}"
                    if not self._equip_armor_piece(vision_controller, ic, template_path, piece):
                        logger.warning(f"Failed to equip mixed {piece}, continuing...")

                # Step 3: Close inventory
                self._close_inventory(ic)

                logger.info("Mixed armor equipment task completed")

            except Exception as e:
                logger.error(f"Mixed armor equipment task failed: {e}")

        # Tag the task for identification
        task._gw_task_id = "equip_mixed_fullset"  # type: ignore
        return task

    def _open_inventory(self, vision_controller: Any, input_controller: Any) -> bool:
        """Open game inventory using vision template matching.

        Returns:
            True if inventory opened successfully, False otherwise
        """
        try:
            # Look for inventory button template
            inventory_template = "assets/inventory_button_template.png"
            if not Path(inventory_template).exists():
                logger.error(f"Inventory template not found: {inventory_template}")
                return False

            # Use vision controller to find and click inventory button
            if hasattr(vision_controller, 'find_and_click_template'):
                result = vision_controller.find_and_click_template(inventory_template)
                return bool(result)
            else:
                # Fallback: use configured inventory key
                inv_key = self.config_manager.get("inventory_key", "i")
                if hasattr(input_controller, 'press_key'):
                    input_controller.press_key(inv_key)
                    return True

            return False

        except Exception as e:
            logger.error(f"Error opening inventory: {e}")
            return False

    def _equip_armor_piece(self, vision_controller: Any, input_controller: Any,
                          template_path: str, piece_name: str) -> bool:
        """Equip a specific armor piece using template matching.

        Args:
            vision_controller: Vision system for template matching
            input_controller: Input system for clicks
            template_path: Path to armor piece template image
            piece_name: Name of the armor piece for logging

        Returns:
            True if piece equipped successfully, False otherwise
        """
        try:
            if not Path(template_path).exists():
                logger.warning(f"Template not found for {piece_name}: {template_path}")
                return False

            # Use vision controller to find and click armor piece
            if hasattr(vision_controller, 'find_and_click_template'):
                success = vision_controller.find_and_click_template(template_path)
                success_bool = bool(success)
                if success_bool:
                    logger.info(f"Successfully equipped {piece_name}")
                else:
                    logger.warning(f"Could not find {piece_name} in inventory")
                return success_bool

            return False

        except Exception as e:
            logger.error(f"Error equipping {piece_name}: {e}")
            return False

    def _close_inventory(self, input_controller: Any) -> None:
        """Close the game inventory.

        Args:
            input_controller: Input system for key presses
        """
        try:
            # Use configured inventory key or ESC to close
            inv_key = self.config_manager.get("inventory_key", "i")
            if hasattr(input_controller, 'press_key'):
                input_controller.press_key(inv_key)

        except Exception as e:
            logger.error(f"Error closing inventory: {e}")
