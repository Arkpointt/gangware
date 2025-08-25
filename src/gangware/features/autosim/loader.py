from __future__ import annotations

import time

from .menu_watch import MenuWatcher
from .automation import AutoSimWorkflow


class AutoSim:
    def __init__(self, state_manager, config_manager, overlay=None) -> None:
        self.state = state_manager
        self.config = config_manager
        self._overlay = overlay
        self._watch = None  # type: MenuWatcher | None
        self._workflow = None  # type: AutoSimWorkflow | None
        self._automation_active = False
        self._server_number = ""

    def start(self, server_number: str = "") -> None:
        """Start AutoSim with optional server automation."""
        if self._watch is None:
            self._watch = MenuWatcher(self.state, overlay=self._overlay)

        if self._workflow is None:
            self._workflow = AutoSimWorkflow(self.config, overlay=self._overlay, state_manager=self.state)

        self._watch.start()

        # Reset shared autosim state to avoid stale resumes/windows from previous runs
        try:
            self.state.set("autosim_resume_from", None)
            self.state.set("autosim_join_window_until", 0.0)
            self.state.set("autosim_cf_suppress_until", 0.0)
        except Exception:
            pass

        # If server number provided, start automation after menu detection stabilizes
        if server_number.strip():
            self._automation_active = True
            self._server_number = server_number.strip()
            # Wait a moment for menu detection to stabilize, then start automation
            self._schedule_automation(self._server_number)
        else:
            # Even without initial server number, keep empty for resume logic
            self._server_number = ""

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
                # Show overlay when automation finishes
                self._show_overlay_when_done()
            else:
                self._update_status("No menu detected for automation")
                self._show_overlay_when_done()

        # Run automation in a separate thread-like manner (using QTimer in practice)
        import threading
        automation_thread = threading.Thread(target=run_automation, daemon=True)
        automation_thread.start()

    def tick(self) -> None:
        """Lightweight poll to resume automation if watcher signaled a resume point."""
        if not self._workflow:
            return
        try:
            resume_from = self.state.get("autosim_resume_from", None)
            if resume_from and self._server_number:
                # Clear the flag to avoid duplicate resumes
                try:
                    self.state.set("autosim_resume_from", None)
                except Exception:
                    pass
                # Kick the workflow from the indicated menu
                menu_name = str(resume_from)
                self._automation_active = True
                success = self._workflow.execute_from_menu(menu_name, self._server_number)
                self._automation_active = False
                if success:
                    self._update_status("Automation resumed and completed")
                else:
                    self._update_status("Automation resume failed")
                # Show overlay when automation finishes
                self._show_overlay_when_done()
        except Exception:
            pass

    def stop(self) -> None:
        """Stop AutoSim menu watching and automation."""
        self._automation_active = False
        if self._watch:
            self._watch.stop()
            self._watch = None

        # Clear shared autosim state flags on stop
        try:
            self.state.set("autosim_resume_from", None)
            self.state.set("autosim_join_window_until", 0.0)
            self.state.set("autosim_cf_suppress_until", 0.0)
        except Exception:
            pass

    def _update_status(self, message: str) -> None:
        """Update overlay status if available."""
        try:
            if self._overlay and hasattr(self._overlay, "set_status_safe"):
                self._overlay.set_status_safe(f"AutoSim: {message}")
        except Exception:
            pass

    def _show_overlay_when_done(self) -> None:
        """Show overlay when automation finishes."""
        try:
            if self._overlay and hasattr(self._overlay, "set_visible"):
                self._overlay.set_visible(True)
        except Exception:
            pass
