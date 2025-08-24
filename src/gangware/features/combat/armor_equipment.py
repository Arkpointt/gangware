"""Armor Equipment Service for ARK: Survival Ascended.

Handles complex armor swapping tasks with vision-based template matching
and multi-step equipment sequences.
"""
import logging
import sys
import time
from typing import Callable, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class ArmorEquipmentService:
    """Service for creating complex armor equipment task functions."""

    def __init__(
        self,
        config_manager: Any,
        input_controller: Optional[Any] = None,
        search_service: Optional[Any] = None
    ):
        self.config_manager = config_manager
        self.input_controller = input_controller
        self.search_service = search_service

    def _resolve_asset_path(self, relative_path: str) -> str:
        """Resolve asset path relative to project root.

        Args:
            relative_path: Path relative to project root

        Returns:
            Absolute path to the asset
        """
        try:
            # When frozen, PyInstaller extracts data files under sys._MEIPASS
            if getattr(sys, 'frozen', False):
                base = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
            else:
                # Dev mode: find project root by looking for distinctive files
                # Start from current working directory and walk up to find project root
                current = Path.cwd()
                while current != current.parent:
                    # Look for distinctive project files to identify project root
                    if (current / "pyproject.toml").exists() and (current / "assets").exists():
                        base = current
                        break
                    current = current.parent
                else:
                    # Fallback: assume current working directory
                    base = Path.cwd()

            resolved_path = str((base / relative_path).resolve())
            logger.debug(f"Resolved asset path: {relative_path} -> {resolved_path}")
            return resolved_path
        except Exception:
            # Fallback to relative path
            return relative_path

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

                # Step 1: Equip armor pieces in sequence using search service
                # Search service handles all inventory open/close operations
                if not self.search_service:
                    logger.error("No search service available for flak armor equipment")
                    return

                armor_pieces = [
                    "Flak Helmet",
                    "Flak Chestpiece",
                    "Flak Leggings",
                    "Flak Gauntlets",
                    "Flak Boots"
                ]

                for i, search_term in enumerate(armor_pieces):
                    logger.info(f"Searching and equipping: {search_term}")
                    # Only open inventory for the first piece, only close for the last piece
                    is_first_piece = (i == 0)
                    is_last_piece = (i == len(armor_pieces) - 1)
                    search_task = self.search_service.create_search_and_type_task(
                        search_term,
                        close_inventory=is_last_piece,
                        open_inventory=is_first_piece
                    )
                    search_task(vision_controller, ic)
                    time.sleep(0.25)  # Faster pause between pieces (reduced from 0.5s)

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

                # Step 1: Equip tek armor pieces in sequence using search service
                # Search service handles all inventory open/close operations
                if not self.search_service:
                    logger.error("No search service available for tek armor equipment")
                    return

                armor_pieces = [
                    "Tek Helmet",
                    "Tek Chestpiece",
                    "Tek Leggings",
                    "Tek Gauntlets",
                    "Tek Boots"
                ]

                for i, search_term in enumerate(armor_pieces):
                    logger.info(f"Searching and equipping: {search_term}")
                    # Only open inventory for the first piece, only close for the last piece
                    is_first_piece = (i == 0)
                    is_last_piece = (i == len(armor_pieces) - 1)
                    search_task = self.search_service.create_search_and_type_task(
                        search_term,
                        close_inventory=is_last_piece,
                        open_inventory=is_first_piece
                    )
                    search_task(vision_controller, ic)
                    time.sleep(0.25)  # Faster pause between pieces (reduced from 0.5s)

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
                logger.info("Starting mixed armor equipment task (F4)")

                # Use provided input controller or fall back to service controller
                ic = input_controller or self.input_controller
                if not ic:
                    logger.error("No input controller available for mixed equipment")
                    return

                # Require search service to match F2/F3 logic
                if not self.search_service:
                    logger.error("No search service available for mixed armor equipment")
                    return

                # Requested order and types
                armor_pieces = [
                    "Flak Helmet",
                    "Tek Chestpiece",
                    "Tek Gauntlets",
                    "Flak Leggings",
                    "Flak Boots",
                ]

                for i, search_term in enumerate(armor_pieces):
                    logger.info(f"Searching and equipping (F4): {search_term}")
                    is_first_piece = (i == 0)
                    is_last_piece = (i == len(armor_pieces) - 1)
                    search_task = self.search_service.create_search_and_type_task(
                        search_term,
                        close_inventory=is_last_piece,
                        open_inventory=is_first_piece,
                    )
                    search_task(vision_controller, ic)
                    time.sleep(0.25)  # Faster pause between pieces (reduced from 0.5s)

                logger.info("Mixed armor equipment task (F4) completed")

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
            # Get the configured inventory key (must be set by user during calibration)
            inv_token = self.config_manager.get("inventory_key")
            if not inv_token:
                logger.error("No inventory key configured. Please run calibration first.")
                return False

            logger.info(f"Opening inventory using configured key: {inv_token}")

            # Use press_token if available (supports both keyboard and mouse)
            if hasattr(input_controller, 'press_token'):
                input_controller.press_token(inv_token)
            elif hasattr(input_controller, 'press_key'):
                # Fallback: convert token to key format for press_key
                if inv_token.startswith('key_'):
                    key = inv_token[4:]  # Remove 'key_' prefix
                else:
                    key = inv_token
                input_controller.press_key(key)
            else:
                logger.error("Input controller has no press_token or press_key method")
                return False

            # Add a delay to allow the inventory to open
            time.sleep(1.0)  # Wait 1 second for inventory to open
            logger.debug("Waited for inventory to open")
            return True

        except Exception as e:
            logger.error(f"Error opening inventory: {e}")
            return False

    def _equip_armor_piece_by_search(self, vision_controller: Any, input_controller: Any,
                                   search_term: str, piece_name: str) -> bool:
        """Equip a specific armor piece using search functionality.

        Args:
            vision_controller: Vision system for template matching
            input_controller: Input system for clicks
            search_term: Text to search for (e.g., "Ascendant Flak Helmet")
            piece_name: Name of the armor piece for logging

        Returns:
            True if piece equipped successfully, False otherwise
        """
        try:
            if not self.search_service:
                logger.error("No search service available for armor equipment")
                return False

            logger.info(f"Searching for {piece_name}: {search_term}")

            # Create and execute search task for this armor piece
            search_task = self.search_service.create_search_and_type_task(search_term)
            search_task(vision_controller, input_controller)

            # Add a small delay between pieces
            time.sleep(0.5)
            return True

        except Exception as e:
            logger.error(f"Error equipping {piece_name}: {e}")
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

            logger.debug(f"Found template for {piece_name}: {template_path}")

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
            # Use a dedicated close key if present; default to ESC
            close_token = self.config_manager.get("inventory_close_key") or "key_esc"
            if not close_token:
                logger.error("No inventory close key configured")
                return

            # Use press_token if available (supports both keyboard and mouse)
            if hasattr(input_controller, 'press_token'):
                input_controller.press_token(close_token)
            elif hasattr(input_controller, 'press_key'):
                # Fallback: convert token to key format for press_key
                if close_token.startswith('key_'):
                    key = close_token[4:]  # Remove 'key_' prefix
                else:
                    key = close_token
                input_controller.press_key(key)

            time.sleep(0.5)  # Brief delay to allow inventory to close
            logger.debug("Closed inventory")

        except Exception as e:
            logger.error(f"Error closing inventory: {e}")
