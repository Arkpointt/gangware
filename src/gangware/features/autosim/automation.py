"""autosim.automation
AutoSim automation workflow that navigates ARK menus to join servers.

Implements the full automation sequence:
1. Main Menu -> Select Game Menu
2. Select Game Menu -> Server Browser
3. Search for server by number
4. Look for BattlEye symbol and join
5. Handle failures by going back and retrying
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from ...core.config import ConfigManager
from ...io.controls import InputController
from ...vision.controller import VisionController


class AutoSimWorkflow:
    """Handles the full automation workflow for joining ARK servers."""

    def __init__(self, config_manager: ConfigManager, overlay=None) -> None:
        self.config = config_manager
        self._overlay = overlay
        self._logger = logging.getLogger(__name__)
        self.vision = VisionController()
        self.input_ctrl = InputController()
        self.max_retries = 3  # Maximum number of retry attempts

    def execute_from_menu(self, current_menu: str, server_number: str, retry_count: int = 0) -> bool:
        """Execute automation workflow starting from the detected menu.

        Args:
            current_menu: The currently detected menu (MAIN_MENU, SELECT_GAME, etc.)
            server_number: Server number to search for
            retry_count: Current retry attempt (for recursive retries)

        Returns:
            True if workflow completed successfully, False otherwise
        """
        if not server_number:
            self._logger.warning("No server number provided for AutoSim workflow")
            return False

        self._logger.info("Starting AutoSim workflow from %s, server=%s (attempt %d/%d)",
                         current_menu, server_number, retry_count + 1, self.max_retries + 1)

        try:
            if current_menu == "MAIN_MENU":
                return self._from_main_menu(server_number, retry_count)
            elif current_menu == "SELECT_GAME":
                return self._from_select_game(server_number, retry_count)
            elif current_menu == "SERVER_BROWSER":
                return self._from_server_browser(server_number, retry_count)
            else:
                self._logger.warning("Unknown menu for AutoSim: %s", current_menu)
                return False
        except Exception as e:
            self._logger.error("AutoSim workflow failed: %s", e)
            return False

    def _from_main_menu(self, server_number: str, retry_count: int = 0) -> bool:
        """Navigate from Main Menu to server join."""
        self._logger.info("AutoSim: Clicking Main Menu button")
        if not self._click_coordinate("coord_main_menu"):
            return False

        # Wait for Select Game menu to appear
        time.sleep(0.3)
        return self._from_select_game(server_number, retry_count)

    def _from_select_game(self, server_number: str, retry_count: int = 0) -> bool:
        """Navigate from Select Game menu to server join."""
        self._logger.info("AutoSim: Clicking Select Game button")
        if not self._click_coordinate("coord_select_game"):
            return False

        # Wait for Server Browser to appear
        time.sleep(0.5)
        return self._from_server_browser(server_number, retry_count)

    def _from_server_browser(self, server_number: str, retry_count: int = 0) -> bool:
        """Search for server and join from Server Browser."""
        # Click search box
        self._logger.info("AutoSim: Clicking search box")
        if not self._click_coordinate("coord_search_box"):
            return False

        time.sleep(0.2)

        # Clear existing text and type server number
        self._logger.info("AutoSim: Typing server number: %s", server_number)
        self.input_ctrl.hotkey("ctrl", "a")  # Select all
        time.sleep(0.05)
        self.input_ctrl.type_text(server_number)
        time.sleep(0.2)
        self.input_ctrl.press_key("enter")  # Search

        # Give search results a moment to start loading
        time.sleep(0.3)

        # Wait for search results and look for BattlEye symbol
        return self._find_and_join_battleye_server(server_number, retry_count)

    def _find_and_join_battleye_server(self, server_number: str, retry_count: int = 0) -> bool:
        """Look for BattlEye symbol and join the server."""
        battleye_template = self._get_battleye_template_path()
        if not battleye_template.exists():
            self._logger.error("BattlEye template not found: %s", battleye_template)
            return False

        self._logger.info("AutoSim: Looking for BattlEye symbol")

        # Wait for search results to load and look for BattlEye symbol
        start_time = time.time()
        timeout = 4.0  # Increased back to 4.0 seconds but with better detection
        last_log_time = 0

        while time.time() - start_time < timeout:
            # Try multiple confidence levels for better detection
            for confidence in [0.8, 0.7, 0.6]:  # Start high, go lower if needed
                result = self.vision.find_template(str(battleye_template), confidence=confidence)
                if result and result[0]:  # Found BattlEye symbol
                    elapsed = time.time() - start_time
                    self._logger.info("AutoSim: Found BattlEye symbol after %.2fs (confidence=%.1f), clicking",
                                     elapsed, confidence)
                    if not self._click_coordinate("coord_battleye_symbol"):
                        return False

                    time.sleep(0.1)

                    # Click Join Game button
                    self._logger.info("AutoSim: Clicking Join Game button")
                    if not self._click_coordinate("coord_join_game"):
                        return False

                    # Monitor for success/failure after joining
                    return self._monitor_join_result(server_number, retry_count)

            # Log progress every 2 seconds to show it's working
            current_time = time.time()
            if current_time - last_log_time >= 2.0:
                self._logger.debug("AutoSim: Still searching for BattlEye symbol... (%.1fs elapsed)",
                                 current_time - start_time)
                last_log_time = current_time

            time.sleep(0.05)  # Check every 50ms for faster detection

        # BattlEye symbol not found within timeout - implement retry logic
        if retry_count < self.max_retries:
            self._logger.info("AutoSim: BattlEye symbol not found, going back to retry (%d/%d)",
                             retry_count + 1, self.max_retries)
            if not self._click_coordinate("coord_back"):
                return False

            time.sleep(1.0)

            # Should be back on Select Game menu, retry from there
            return self._from_select_game(server_number, retry_count + 1)
        else:
            self._logger.warning("AutoSim: Max retries reached (%d), giving up", self.max_retries)
            self._update_status("Max retries reached - server may be offline")
            return False

    def _click_coordinate(self, coord_key: str) -> bool:
        """Click a coordinate from the config."""
        coord_str = self.config.get(coord_key, "")
        if not coord_str:
            self._logger.error("Coordinate %s not found in config", coord_key)
            return False

        try:
            x, y = map(int, coord_str.split(","))
            self._logger.debug("AutoSim: Clicking %s at (%d, %d)", coord_key, x, y)
            self.input_ctrl.move_mouse(x, y)
            time.sleep(0.03)  # Reduced from 0.05 to 0.03
            self.input_ctrl.click()
            return True
        except (ValueError, AttributeError) as e:
            self._logger.error("Invalid coordinate format for %s: %s (%s)", coord_key, coord_str, e)
            return False

    def _monitor_join_result(self, server_number: str, retry_count: int = 0) -> bool:
        """Monitor for success/failure states after clicking Join Game.

        Success: 7 seconds of no menu or failure detections
        Failure: Still detecting menus or failure states after 15 seconds

        Args:
            server_number: Server number being joined
            retry_count: Current retry attempt

        Returns:
            True if successful join, False if failed and should retry
        """
        self._logger.info("AutoSim: Monitoring join result...")
        start_time = time.time()
        last_menu_detected = 0.0
        failure_detected = False

        # TODO: Add failure template detection when templates are provided
        # failure_templates = self._get_failure_templates()

        while time.time() - start_time < 15.0:  # Monitor for up to 15 seconds
            current_time = time.time()

            # Check for failure states (placeholder - implement when templates provided)
            # if self._detect_failure_states():
            #     self._logger.info("AutoSim: Failure state detected")
            #     failure_detected = True
            #     break

            # Check if we're still detecting menus (indicates join didn't work)
            if self._detect_any_menu():
                last_menu_detected = current_time
                self._logger.debug("AutoSim: Still detecting menu at %.1fs",
                                 current_time - start_time)

            # Success condition: 7 seconds without menu detection
            if current_time - last_menu_detected >= 7.0 and last_menu_detected > 0:
                self._logger.info("AutoSim: SUCCESS - No menu detected for 7 seconds, join successful!")
                self._update_status("Successfully joined server!")
                return True

            time.sleep(0.5)  # Check every 500ms

        # If we reach here, either failure detected or 15 seconds elapsed
        if failure_detected:
            self._logger.info("AutoSim: Join failed due to failure state")
        else:
            self._logger.info("AutoSim: Join failed - still detecting menus after 15 seconds")

        # Go back and retry if under max attempts
        if retry_count < self.max_retries:
            self._logger.info("AutoSim: Going back to retry (%d/%d)",
                             retry_count + 1, self.max_retries)
            if not self._click_coordinate("coord_back"):
                return False

            time.sleep(1.0)
            # Should be back on Select Game menu, retry from there
            return self._from_select_game(server_number, retry_count + 1)
        else:
            self._logger.warning("AutoSim: Max retries reached (%d), giving up", self.max_retries)
            self._update_status("Max retries reached - unable to join server")
            return False

    def _detect_any_menu(self) -> bool:
        """Check if any menu is currently being detected.

        Returns:
            True if any menu template is detected, False otherwise
        """
        # Use the same vision templates that MenuWatcher uses
        menu_templates = [
            "Main_Menu_2.png",
            "Select_Game_2.png",
            "Server_Browser_2.png"
        ]

        for template_name in menu_templates:
            template_path = self._get_menu_template_path(template_name)
            if template_path.exists():
                result = self.vision.find_template(str(template_path), confidence=0.6)
                if result and result[0]:  # Template found
                    return True

        return False

    def _get_menu_template_path(self, template_name: str) -> Path:
        """Get the path to a menu template."""
        base = Path(__file__).resolve().parents[4]  # Go up 4 levels to project root
        template_path = base / "assets" / "anchors" / template_name
        return template_path

    def _get_battleye_template_path(self) -> Path:
        """Get the path to the BattlEye symbol template."""
        # Look for battleye template in assets/templates
        base = Path(__file__).resolve().parents[4]  # Go up 4 levels to project root
        template_path = base / "assets" / "templates" / "battleye_symbol.png"
        return template_path

    def _update_status(self, message: str) -> None:
        """Update overlay status if available."""
        try:
            if self._overlay and hasattr(self._overlay, "set_status_safe"):
                self._overlay.set_status_safe(f"AutoSim: {message}")
        except Exception:
            pass
