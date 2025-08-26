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

    def __init__(self, config_manager: ConfigManager, overlay=None, state_manager=None) -> None:
        self.config = config_manager
        self._overlay = overlay
        self._logger = logging.getLogger(__name__)
        self.vision = VisionController()
        self.input_ctrl = InputController()
        self.max_retries = 3  # Maximum number of retry attempts
        self.state = state_manager

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

                    # Start the post-Join detection window for watcher (20s)
                    try:
                        if self.state is not None and hasattr(self.state, "set"):
                            self.state.set("autosim_join_window_until", time.time() + 20.0)
                    except Exception:
                        pass

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

        Success: 2 seconds of no menu or failure detections
        Failure: Still detecting menus or failure states after 15 seconds

        Args:
            server_number: Server number being joined
            retry_count: Current retry attempt

        Returns:
            True if successful join, False if failed and should retry
        """
        self._logger.info("AutoSim: Monitoring join result...")
        start_time = time.time()
        consecutive_no_menu_time = 0.0  # Track continuous time without menu detection

        while time.time() - start_time < 15.0:  # Monitor for up to 15 seconds
            current_time = time.time()

            # Check for Connection_Failed popup
            if self._detect_connection_failed():
                self._logger.info("AutoSim: Connection_Failed popup detected - handling failure state")
                # Handle the popup but don't immediately retry - respect retry limits
                if self._handle_connection_failed_popup():
                    # Popup handled, now check retry count and navigate back if needed
                    if retry_count >= self.max_retries:
                        self._logger.warning("AutoSim: Max retries reached (%d), giving up", self.max_retries)
                        self._update_status("Max retries reached - unable to join server")
                        return False

                    # Navigate back and retry
                    self._logger.info("AutoSim: Going back to retry (%d/%d)", retry_count + 1, self.max_retries)
                    if self._navigate_back_to_select_game(server_number, retry_count + 1):
                        return self._from_select_game(server_number, retry_count + 1)
                    else:
                        return False
                else:
                    return False  # Failed to handle popup

            # Check if we're still detecting menus (indicates join didn't work)
            if self._detect_any_menu():
                consecutive_no_menu_time = 0.0  # Reset consecutive timer
                self._logger.debug("AutoSim: Still detecting menu at %.1fs",
                                 current_time - start_time)
            else:
                # No menu detected - update consecutive timer
                if consecutive_no_menu_time == 0.0:
                    consecutive_no_menu_time = current_time
                    self._logger.debug("AutoSim: Started tracking no-menu time at %.1fs",
                                     current_time - start_time)

                # Success condition: 2 seconds of consecutive no menu detection
                if current_time - consecutive_no_menu_time >= 2.0:
                    self._logger.info("AutoSim: SUCCESS - No menu detected for 2 seconds, join successful!")
                    self._update_status("Successfully joined server!")
                    return True
                else:
                    # Log progress every 2 seconds
                    no_menu_duration = current_time - consecutive_no_menu_time
                    if no_menu_duration >= 1.0 and int(no_menu_duration) % 1 == 0:
                        self._logger.debug("AutoSim: No menu for %.1fs (need 2.0s for success)",
                                         no_menu_duration)

            time.sleep(0.25)  # Check every 250ms for faster failure detection

        # 15 seconds elapsed without success or Connection_Failed popup
        self._logger.info("AutoSim: Join timeout - no success or failure detected after 15 seconds")

        # Check retry count before going back
        if retry_count >= self.max_retries:
            self._logger.warning("AutoSim: Max retries reached (%d), giving up", self.max_retries)
            self._update_status("Max retries reached - unable to join server")
            return False

        # Navigate back and retry
        self._logger.info("AutoSim: Going back to retry (%d/%d)", retry_count + 1, self.max_retries)
        if self._navigate_back_to_select_game(server_number, retry_count + 1):
            return self._from_select_game(server_number, retry_count + 1)
        else:
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

    def _detect_connection_failed(self) -> bool:
        """Detect if Connection_Failed popup is visible.

        Returns:
            True if Connection_Failed popup is detected
        """
        try:
            # Respect global suppression window if recently dismissed
            try:
                suppress_until = float(self.state.get("autosim_cf_suppress_until", 0.0)) if self.state else 0.0
            except Exception:
                suppress_until = 0.0
            if time.time() < suppress_until:
                return False

            base = Path(__file__).resolve().parents[4]  # Go up 4 levels to project root
            template_path = base / "assets" / "menus" / "connection_failed.jpg"

            if not template_path.exists():
                self._logger.debug("Connection_Failed template not found: %s", template_path)
                return False

            result = self.vision.find_template(str(template_path), confidence=0.7)
            return result is not None
        except Exception as e:
            self._logger.error("Error detecting Connection_Failed popup: %s", e)
            return False

    def _handle_connection_failed(self, server_number: str, retry_count: int) -> bool:
        """Handle Connection_Failed popup by closing it and restarting from detected menu.

        Respects the maximum retry limit and does not increment retry count inappropriately.

        Args:
            server_number: Server number to search for
            retry_count: Current retry attempt

        Returns:
            True if successfully handled and restarted, False otherwise
        """
        self._logger.info("AutoSim: Handling Connection_Failed popup...")

        # Check if we've exceeded max retries before proceeding
        if retry_count >= self.max_retries:
            self._logger.warning(
                "AutoSim: Max retries (%d) reached while handling connection failure. Aborting.",
                self.max_retries
            )
            return False

        # Close the popup
        if not self._handle_connection_failed_popup():
            return False

        # Navigate back to SELECT_GAME menu to retry
        return self._navigate_back_to_select_game(server_number, retry_count)

    def _handle_connection_failed_popup(self) -> bool:
        """Close the Connection_Failed popup.

        Returns:
            True if popup was successfully closed, False otherwise
        """
        # Try to ensure Ark has focus before pressing Enter
        try:
            from ...core.win32.utils import ensure_ark_foreground  # lazy import
            ensure_ark_foreground(timeout=0.7)
        except Exception:
            pass

        # Press Enter to close the popup
        self.input_ctrl.press_key("enter")
        self._logger.info("AutoSim: Pressed Enter to close Connection_Failed popup")

        # Set a shared suppression window to avoid re-detecting the same popup
        try:
            if self.state is not None and hasattr(self.state, "set"):
                self.state.set("autosim_cf_suppress_until", time.time() + 2.5)
        except Exception:
            pass

        # Wait a moment for popup to close
        time.sleep(1.0)
        return True

    def _navigate_back_to_select_game(self, server_number: str, retry_count: int) -> bool:
        """Navigate back to SELECT_GAME menu after connection failure.

        Args:
            server_number: Server number to search for
            retry_count: Current retry attempt

        Returns:
            True if successfully navigated and restarted, False otherwise
        """
        # Prefer watcher-provided menu (with hysteresis), wait briefly for it to stabilize
        detected_menu = self._wait_watcher_menu(timeout=0.9)
        if not detected_menu:
            # Fallback to direct template detection (prefer SELECT_GAME to avoid false MAIN_MENU)
            detected_menu = self._detect_current_menu_prefer_select_game()

        if detected_menu:
            self._logger.info("AutoSim: After closing popup, detected menu: %s", detected_menu)

            # If we're already at SELECT_GAME, restart workflow directly
            if detected_menu == "SELECT_GAME":
                return self.execute_from_menu(detected_menu, server_number, retry_count)

            # If we're at SERVER_BROWSER, navigate back to SELECT_GAME first
            elif detected_menu == "SERVER_BROWSER":
                self._logger.info("AutoSim: At SERVER_BROWSER, clicking Back to return to SELECT_GAME")
                if self._click_coordinate("coord_back"):
                    time.sleep(1.0)
                    # Check if we made it to SELECT_GAME
                    final_menu = self._detect_current_menu()
                    if final_menu == "SELECT_GAME":
                        self._logger.info("AutoSim: Successfully navigated back to SELECT_GAME")
                        return self.execute_from_menu(final_menu, server_number, retry_count)
                    else:
                        self._logger.warning("AutoSim: Expected SELECT_GAME after Back click, got: %s", final_menu)
                        return False
                else:
                    self._logger.error("AutoSim: Failed to click Back button from SERVER_BROWSER")
                    return False

            # For any other menu, try to restart from there
            else:
                self._logger.info("AutoSim: Restarting workflow from %s", detected_menu)
                return self.execute_from_menu(detected_menu, server_number, retry_count)

        else:
            self._logger.warning("AutoSim: Could not detect menu after closing Connection_Failed popup")
            # If we can't detect the menu, assume we're back at server browser and click back
            self._logger.info("AutoSim: Clicking Back button as fallback")
            if self._click_coordinate("coord_back"):
                time.sleep(1.0)
                # Try to detect menu again
                detected_menu = self._detect_current_menu()
                if detected_menu == "SELECT_GAME":
                    self._logger.info("AutoSim: After Back button, detected menu: %s", detected_menu)
                    return self.execute_from_menu(detected_menu, server_number, retry_count)

            self._logger.error("AutoSim: Failed to recover from Connection_Failed state")
            return False

    def _wait_watcher_menu(self, timeout: float = 0.9) -> str | None:
        """Wait briefly for MenuWatcher to report a stable menu, then return its name.

        Uses the state manager's 'autosim_menu' entry if available and ok.
        """
        if not self.state:
            return None
        deadline = time.time() + max(0.1, timeout)
        last_name: str | None = None
        stable_reads = 0
        while time.time() < deadline:
            try:
                st = self.state.get("autosim_menu")
            except Exception:
                st = None
            name = getattr(st, "name", None)
            ok = bool(getattr(st, "ok", False))
            if ok and name:
                if name == last_name:
                    stable_reads += 1
                else:
                    last_name = name
                    stable_reads = 1
                if stable_reads >= 2:
                    return name
            time.sleep(0.12)
        return last_name if stable_reads >= 1 else None

    def _detect_current_menu_prefer_select_game(self) -> str | None:
        """Detect current menu, preferring SELECT_GAME over MAIN_MENU to avoid false positives."""
        # Check for Select Game first
        if self._detect_menu("SELECT_GAME"):
            return "SELECT_GAME"
        # Then check for Main Menu
        if self._detect_menu("MAIN_MENU"):
            return "MAIN_MENU"
        # Finally check for Server Browser
        if self._detect_menu("SERVER_BROWSER"):
            return "SERVER_BROWSER"
        return None

    def _detect_menu(self, menu_type: str) -> bool:
        """Detect if a specific menu is currently visible.

        Args:
            menu_type: Menu type to detect (MAIN_MENU, SELECT_GAME, SERVER_BROWSER)

        Returns:
            True if the specified menu is detected
        """
        # Map menu types to template names
        template_map = {
            "MAIN_MENU": "Main_Menu_2.png",
            "SELECT_GAME": "Select_Game_2.png",
            "SERVER_BROWSER": "Server_Browser_2.png"
        }

        template_name = template_map.get(menu_type)
        if not template_name:
            self._logger.warning("Unknown menu type: %s", menu_type)
            return False

        template_path = self._get_menu_template_path(template_name)
        if not template_path.exists():
            self._logger.debug("Template not found: %s", template_path)
            return False

        try:
            result = self.vision.find_template(str(template_path), confidence=0.6)
            return result is not None and bool(result[0])  # Template found
        except Exception as e:
            self._logger.error("Error detecting menu %s: %s", menu_type, e)
            return False

    def _detect_current_menu(self) -> str | None:
        """Detect which menu is currently displayed.

        Returns:
            Menu name string or None if no menu detected
        """
        # Check for Main Menu first
        if self._detect_menu("MAIN_MENU"):
            return "MAIN_MENU"
        # Then check for Select Game
        elif self._detect_menu("SELECT_GAME"):
            return "SELECT_GAME"
        # Finally check for Server Browser
        elif self._detect_menu("SERVER_BROWSER"):
            return "SERVER_BROWSER"
        else:
            return None

    def _update_status(self, message: str) -> None:
        """Update overlay status if available."""
        try:
            if self._overlay and hasattr(self._overlay, "set_status_safe"):
                self._overlay.set_status_safe(f"AutoSim: {message}")
        except Exception:
            pass
