from __future__ import annotations

import time
from typing import Optional

from .menu_watch import MenuWatcher
from .automation import AutoSimWorkflow


class AutoSim:
    def __init__(self, state_manager, config_manager, overlay=None) -> None:
        self.state = state_manager
        self.config = config_manager
        self._overlay = overlay
        self._watch: Optional[MenuWatcher] = None
        self._workflow: Optional[AutoSimWorkflow] = None
        self._automation_active = False

    def start(self, server_number: str = "") -> None:
        """Start AutoSim with optional server automation."""
        if self._watch is None:
            self._watch = MenuWatcher(self.state, overlay=self._overlay)

        if self._workflow is None:
            self._workflow = AutoSimWorkflow(self.config, overlay=self._overlay)

        self._watch.start()

        # If server number provided, start automation after menu detection stabilizes
        if server_number.strip():
            self._automation_active = True
            # Wait a moment for menu detection to stabilize, then start automation
            self._schedule_automation(server_number.strip())

    def _schedule_automation(self, server_number: str) -> None:
        """Schedule automation to start after menu detection stabilizes."""
        def run_automation():
            # First, ensure ARK is in foreground before waiting for menu detection
            from ...core.win32.utils import ensure_ark_foreground, foreground_executable_name

            current_foreground = foreground_executable_name()
            if current_foreground != "arkascended.exe":
                self._update_status("Bringing ARK to foreground...")
                if ensure_ark_foreground(timeout=2.0):
                    self._update_status("ARK focused, waiting for menu detection...")
                    time.sleep(1.0)  # Brief pause for window to stabilize
                else:
                    self._update_status("Could not focus ARK window")

            # Wait for menu detection to be stable
            time.sleep(2.0)  # Reduced from 3.0 since we handled focusing above

            # Get current menu state
            menu_state = self.state.get("autosim_menu")
            if menu_state and menu_state.name and self._automation_active and self._workflow:
                success = self._workflow.execute_from_menu(menu_state.name, server_number)
                if success:
                    self._update_status("Automation completed successfully")
                else:
                    self._update_status("Automation failed")
                self._automation_active = False
            else:
                self._update_status("No menu detected for automation")

        # Run automation in a separate thread-like manner (using QTimer in practice)
        import threading
        automation_thread = threading.Thread(target=run_automation, daemon=True)
        automation_thread.start()

    def stop(self) -> None:
        """Stop AutoSim menu watching and automation."""
        self._automation_active = False
        if self._watch:
            self._watch.stop()
            self._watch = None

    def _update_status(self, message: str) -> None:
        """Update overlay status if available."""
        try:
            if self._overlay and hasattr(self._overlay, "set_status_safe"):
                self._overlay.set_status_safe(f"AutoSim: {message}")
        except Exception:
            pass
