"""
Overlay Window Module
User interface overlay using PyQt6.

Features:
- Anchored to the top-right corner across resolution/monitor changes
- Click-through, always-on-top translucent window with neon-styled UI
- Thread-safe status updates via signals
- F7 recalibration signal dispatch
- Visibility controls: set_visible/toggle_visibility for F1 hotkey support
- Calibration helper prompts (prompt_key_capture and switch_to_main)
"""

import os
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QGraphicsOpacityEffect
from PyQt6.QtCore import Qt, QRect, QObject, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QKeySequence, QShortcut


class StatusSignaller(QObject):
    status = pyqtSignal(str)
    recalibrate = pyqtSignal()
    visibility = pyqtSignal(bool)
    toggle = pyqtSignal()
    start = pyqtSignal()
    toast = pyqtSignal(str, int)
    switch_to_calib = pyqtSignal()
    switch_to_main = pyqtSignal()
    success = pyqtSignal(str, int)


class OverlayWindow:
    def __init__(self, calibration_mode: bool = False, message: str | None = None):
        # Persist incoming state
        self.calibration_mode = calibration_mode
        self.initial_message = message
        # Track visibility independently of Qt's isVisible(), which can be affected by flags
        self._is_shown = True

        # Build application and base window
        self._init_app_window()
        # Compute DPI scale and apply geometry/style
        self.scale = self._compute_scale()
        self._apply_initial_geometry()
        self._apply_window_style()
        self._apply_tooltip_style()
        # Create labels with initial header/status
        header, status_text, status_color = self._initial_texts()
        self._create_labels(header, status_text, status_color)
        # Thread-safe signaller and toast UI
        self._init_signaller()
        self._init_toast()
        self._success_fade_timer = None
        # Ensure initial anchor after show/layout (scheduled on first show)
        # moved to show() to avoid QBasicTimer thread warnings before event loop
        # Optional Start button in calibration mode
        self._init_start_button()
        # Connect screen and window signals
        self._connect_screen_signals()
        # Shortcuts (F7, F1, F10)
        self._init_shortcuts()
        # Initial fade-in scheduled in show()

    # -------------------- Initialization helpers --------------------
    def _init_app_window(self) -> None:
        self.app = QApplication([])
        self.window = QWidget()
        self.window.setWindowTitle("Gangware")
        self._configure_window_flags(click_through=not self.calibration_mode)
        self.window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def _configure_window_flags(self, click_through: bool) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        if click_through:
            flags |= Qt.WindowType.WindowTransparentForInput
        self.window.setWindowFlags(flags)

    def _compute_scale(self) -> float:
        try:
            screen = self.app.primaryScreen()
            dpi = getattr(screen, "logicalDotsPerInch", lambda: 96)()
            return max(1.0, min(2.0, dpi / 96.0))
        except Exception:
            return 1.0

    def _apply_initial_geometry(self) -> None:
        geom = self._get_top_right_geometry(int(520 * self.scale), int(360 * self.scale))
        self.window.setGeometry(geom)

    def _apply_window_style(self) -> None:
        self.window.setStyleSheet(
            """
            background: qlineargradient(
                spread:pad, x1:0, y1:0, x2:1, y2:1,
                stop:0 rgba(8,18,28,200),
                stop:1 rgba(18,38,58,180)
            );
            border: 1px solid rgba(0,234,255,0.9);
            border-radius: 12px;
            font-family: 'Consolas', 'Courier New', monospace;
            """
        )

    def _apply_tooltip_style(self) -> None:
        try:
            self.app.setStyleSheet(
                """
                QToolTip {
                    color: #0a0a0a;
                    background-color: #00eaff;
                    border: 1px solid rgba(0,234,255,0.9);
                    padding: 4px 6px;
                    border-radius: 6px;
                    font: 9pt 'Consolas';
                }
                """
            )
        except Exception:
            pass

    def _initial_texts(self) -> tuple[str, str, str]:
        if self.calibration_mode:
            header = "Gangware - Calibration"
            status_text = (
                self.initial_message
                or "Calibration required: please complete initial setup."
            )
            status_color = "#ff7a7a"
        else:
            header = "Gangware"
            status_text = "Status: Online"
            status_color = "#00eaff"
        return header, status_text, status_color

    def _create_labels(self, header: str, status_text: str, status_color: str) -> None:
        # Header label (small, neon)
        self.header_label = QLabel(f"<b>{header}</b>", self.window)
        self.header_label.setFont(
            QFont("Consolas", int(11 * getattr(self, "scale", 1.0)), QFont.Weight.Bold)
        )
        self.header_label.setStyleSheet("color: rgba(200,220,255,0.95);")
        self.header_label.setGeometry(
            QRect(int(18 * self.scale), int(10 * self.scale), int(420 * self.scale), int(28 * self.scale))
        )
        # Status label (dynamic)
        self.label = QLabel(status_text, self.window)
        self.label.setFont(QFont("Consolas", int(10 * self.scale)))
        self.base_status_color = status_color
        self.label.setStyleSheet(f"color: {status_color};")
        self.label.setWordWrap(True)
        self.label.setGeometry(
            QRect(int(18 * self.scale), int(40 * self.scale), int(480 * self.scale), int(280 * self.scale))
        )
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

    def _init_signaller(self) -> None:
        self.signaller = StatusSignaller()
        self.signaller.status.connect(self._update_status)
        self.signaller.visibility.connect(self._set_visible)
        self.signaller.toggle.connect(self._toggle_visible)
        self.signaller.toast.connect(self._show_toast_ui)
        self.signaller.switch_to_calib.connect(self._switch_to_calibration_ui)
        self.signaller.switch_to_main.connect(self._switch_to_main_ui)
        self.signaller.success.connect(self._success_flash_ui)

    def _init_toast(self) -> None:
        # Toast notification (hidden by default)
        self.toast = QLabel("", self.window)
        self.toast.setStyleSheet(
            """
            color: #0a0a0a;
            background-color: rgba(0, 255, 170, 0.95);
            border: 1px solid rgba(0, 255, 170, 1.0);
            border-radius: 10px;
            padding: 6px 10px;
            """
        )
        self.toast.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.toast.hide()
        self.toast_effect = QGraphicsOpacityEffect(self.toast)
        self.toast.setGraphicsEffect(self.toast_effect)

    def _init_start_button(self) -> None:
        self.start_button = None
        if not self.calibration_mode:
            return
        self.start_button = QPushButton("Start", self.window)
        self.start_button.setToolTip(
            "Begin calibration flow (press F7 any time to recalibrate)"
        )
        self.start_button.setGeometry(
            QRect(
                int(400 * self.scale),
                int(320 * self.scale),
                int(100 * self.scale),
                int(28 * self.scale),
            )
        )
        self.start_button.setStyleSheet(
            """
            QPushButton {
                color: #0a0a0a;
                background-color: #00eaff;
                border: 1px solid rgba(0,234,255,0.9);
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #33f0ff; }
            QPushButton:pressed { background-color: #00c2d1; }
            """
        )
        self.start_button.clicked.connect(lambda: self.signaller.start.emit())

    def _connect_screen_signals(self) -> None:
        # React to monitor geometry/availability changes
        try:
            for screen in self.app.screens():
                try:
                    screen.geometryChanged.connect(self.reposition)
                except Exception:
                    pass
                try:
                    screen.availableGeometryChanged.connect(self.reposition)
                except Exception:
                    pass
        except Exception:
            pass
        # React when the window moves between screens or primary screen changes
        handle = self.window.windowHandle()
        if handle is not None:
            try:
                handle.screenChanged.connect(lambda *_: self.reposition())
            except Exception:
                pass
        try:
            self.app.primaryScreenChanged.connect(lambda *_: self.reposition())
            self.app.screenAdded.connect(self._on_screen_added)
            self.app.screenRemoved.connect(lambda *_: self.reposition())
        except Exception:
            pass

    def _init_shortcuts(self) -> None:
        # Global shortcut: F7 triggers recalibration request
        self._shortcut_recal = QShortcut(QKeySequence("F7"), self.window)
        self._shortcut_recal.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._shortcut_recal.activated.connect(
            lambda: self.signaller.recalibrate.emit()
        )
        # Local shortcut: F1 toggles visibility (useful during calibration mode)
        try:
            self._shortcut_toggle = QShortcut(QKeySequence("F1"), self.window)
            self._shortcut_toggle.setContext(Qt.ShortcutContext.ApplicationShortcut)
            self._shortcut_toggle.activated.connect(
                lambda: self.signaller.toggle.emit()
            )
        except Exception:
            pass
        # Local shortcut: F10 exits application from the GUI
        try:
            self._shortcut_exit = QShortcut(QKeySequence("F10"), self.window)
            self._shortcut_exit.setContext(Qt.ShortcutContext.ApplicationShortcut)
            self._shortcut_exit.activated.connect(lambda: os._exit(0))
        except Exception:
            pass

    # -------------------- Screen handling --------------------
    def _on_screen_added(self, screen):
        # When a new screen appears, hook its signals and re-anchor
        try:
            try:
                screen.geometryChanged.connect(self.reposition)
            except Exception:
                pass
            try:
                screen.availableGeometryChanged.connect(self.reposition)
            except Exception:
                pass
        finally:
            self.reposition()

    # -------------------- Status and visibility API --------------------
    def _update_status(self, text: str):
        # Update label text; runs in GUI thread because signal is connected
        self.label.setText(text)
        # Re-anchor in case the text change affected layout/width
        self.reposition()

    def set_status(self, text: str):
        # Public method for other threads to request a status update
        self.signaller.status.emit(text)

    def prompt_key_capture(self, prompt: str):
        """Update the overlay to prompt the user for a key press.

        This is non-blocking and simply updates the text shown on the
        overlay; the HotkeyManager is responsible for performing the
        actual global key capture.
        """
        self.set_status(f"{prompt}\nPress the desired key now...")

    def on_recalibrate(self, slot):
        """Connect a slot/callable to the F7 recalibration signal."""
        self.signaller.recalibrate.connect(slot)

    def on_start(self, slot):
        """Connect a slot/callable to the calibration start signal."""
        self.signaller.start.connect(slot)

    # -------------------- Mode switching --------------------
    def switch_to_main(self):
        # Thread-safe wrapper to switch to main mode
        self.signaller.switch_to_main.emit()

    def _switch_to_main_ui(self):
        """Switch the overlay visuals from calibration to main mode."""
        try:
            self.header_label.setText("<b>Gangware</b>")
            self.base_status_color = "#00eaff"
            self.label.setStyleSheet(f"color: {self.base_status_color};")
            self.set_status("Status: Online")
            # Hide start button if present
            if hasattr(self, "start_button") and self.start_button:
                self.start_button.hide()
            # Enable click-through for main mode
            self._configure_window_flags(click_through=True)
            self.window.show()  # ensure flags take effect
            self.reposition()
            self._is_shown = True
        except Exception:
            # Do not let UI errors crash the application
            pass

    def switch_to_calibration(self):
        # Thread-safe wrapper to switch to calibration mode
        self.signaller.switch_to_calib.emit()

    def _switch_to_calibration_ui(self):
        """Switch the overlay visuals to calibration mode (not click-through)."""
        try:
            self.header_label.setText("<b>Gangware - Calibration</b>")
            self.base_status_color = "#ff7a7a"
            self.label.setStyleSheet(f"color: {self.base_status_color};")
            # Disable click-through so shortcuts/UI remain responsive/visible
            self._configure_window_flags(click_through=False)
            self.window.show()
            # Ensure it's visible when entering calibration during runtime
            self.set_visible(True)
            self.reposition()
            self._is_shown = True
        except Exception:
            pass

    def _set_visible(self, visible: bool):
        # Runs in GUI thread via signal; immediate show/hide for reliability
        try:
            if visible:
                self.window.setWindowOpacity(1.0)
                self.window.show()
                self.reposition()
                self._is_shown = True
            else:
                self.window.hide()
                self._is_shown = False
        except Exception:
            # Fallback to immediate show/hide on error
            if visible:
                try:
                    self.window.show()
                    self.reposition()
                finally:
                    self._is_shown = True
            else:
                try:
                    self.window.hide()
                finally:
                    self._is_shown = False

    def _toggle_visible(self):
        self._set_visible(not self._is_shown)

    def set_visible(self, visible: bool):
        # Thread-safe setter for visibility
        self.signaller.visibility.emit(visible)
        # Update our local state optimistically; GUI thread will enforce
        self._is_shown = bool(visible)

    def toggle_visibility(self):
        # Thread-safe toggle
        self.signaller.toggle.emit()

    # -------------------- Geometry & anchoring --------------------
    def _get_top_right_geometry(self, width, height):
        # Use availableGeometry to respect taskbars/docks and multi-monitor origins
        screen = self.app.primaryScreen()
        rect = getattr(screen, "availableGeometry", screen.geometry)()
        x = rect.x() + rect.width() - width - 20
        y = rect.y() + 20
        return QRect(int(x), int(y), int(width), int(height))

    def reposition(self):
        """Anchor the window to the top-right of the current screen."""
        handle = self.window.windowHandle()
        screen = handle.screen() if handle is not None else self.app.primaryScreen()
        rect = getattr(screen, "availableGeometry", screen.geometry)()
        margin = 20
        x = rect.x() + rect.width() - self.window.width() - margin
        y = rect.y() + margin
        self.window.move(int(x), int(y))

    def show(self):
        self.window.show()
        # Schedule initial repositioning and fade-in after the event loop starts
        QTimer.singleShot(0, self.reposition)
        QTimer.singleShot(0, self._animate_fade_in)
        self.app.exec()

    # -------------------- Effects and feedback helpers --------------------
    def _animate_fade_in(self, duration: int = 220):
        try:
            anim = QPropertyAnimation(self.window, b"windowOpacity")
            anim.setDuration(duration)
            anim.setStartValue(self.window.windowOpacity())
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
            anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        except Exception:
            pass

    def _animate_fade_out(self, duration: int = 180):
        try:
            anim = QPropertyAnimation(self.window, b"windowOpacity")
            anim.setDuration(duration)
            anim.setStartValue(self.window.windowOpacity())
            anim.setEndValue(0.0)
            anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

            def _hide():
                try:
                    self.window.hide()
                    self.window.setWindowOpacity(1.0)
                except Exception:
                    pass

            anim.finished.connect(_hide)
            anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        except Exception:
            self.window.hide()

    def _position_toast(self):
        # Anchor toast near bottom within window margins
        margin = 16
        w = self.window.width() - margin * 2
        self.toast.setGeometry(QRect(margin, self.window.height() - 48 - margin, w, 32))

    def show_toast(self, text: str, duration_ms: int = 1800):
        # Thread-safe wrapper
        try:
            self.signaller.toast.emit(text, duration_ms)
        except Exception:
            pass

    def _show_toast_ui(self, text: str, duration_ms: int = 1800):
        try:
            self.toast.setText(text)
            self._position_toast()
            self.toast_effect.setOpacity(0.0)
            self.toast.show()
            # Fade in
            fade_in = QPropertyAnimation(self.toast_effect, b"opacity")
            fade_in.setDuration(180)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)
            fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
            # Fade out
            fade_out = QPropertyAnimation(self.toast_effect, b"opacity")
            fade_out.setDuration(300)
            fade_out.setStartValue(1.0)
            fade_out.setEndValue(0.0)
            fade_out.setEasingCurve(QEasingCurve.Type.InCubic)

            def _hide():
                try:
                    self.toast.hide()
                except Exception:
                    pass
            fade_out.finished.connect(_hide)
            # Chain animations via timers
            fade_in.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
            QTimer.singleShot(duration_ms, lambda: fade_out.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped))
        except Exception:
            pass

    def show_success(self, text: str = "Success"):
        # Flash border neon-green and show toast
        try:
            original = self.window.styleSheet()
            self.window.setStyleSheet(
                original + "\n border: 1px solid rgba(0,255,170,1.0);"
            )
            self.show_toast(text)
            QTimer.singleShot(400, lambda: self.window.setStyleSheet(original))
        except Exception:
            pass

    # -------------------- Success status flash --------------------
    def success_flash(self, text: str | None = None, duration_ms: int = 1400):
        """Public API: flash the status text green and fade back to base color.

        Args:
            text: Optional text to set during the flash; if None, keep current text.
            duration_ms: Total fade duration back to the base color.
        """
        try:
            self.signaller.success.emit(text or "", duration_ms)
        except Exception:
            pass

    def _success_flash_ui(self, text: str, duration_ms: int):
        try:
            if text:
                self.label.setText(text)
            # Stop any ongoing fade
            try:
                if self._success_fade_timer is not None:
                    self._success_fade_timer.stop()
                    self._success_fade_timer.deleteLater()
            except Exception:
                pass
            self._success_fade_timer = QTimer(self.window)

            start_rgb = (0, 255, 170)  # neon green
            end_rgb = self._hex_to_rgb(getattr(self, "base_status_color", "#00eaff"))
            steps = max(8, min(40, int(duration_ms / 50)))
            interval = max(16, int(duration_ms / steps))
            idx = {"i": 0}

            # Immediately set to green
            self._set_label_color_rgb(*start_rgb)

            def step():
                i = idx["i"] + 1
                t = i / steps
                r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * t)
                g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * t)
                b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * t)
                self._set_label_color_rgb(r, g, b)
                idx["i"] = i
                if i >= steps:
                    try:
                        self._success_fade_timer.stop()
                        self._success_fade_timer.deleteLater()
                    finally:
                        self._success_fade_timer = None

            self._success_fade_timer.timeout.connect(step)
            self._success_fade_timer.start(interval)
        except Exception:
            # On failure, just set base color
            try:
                self.label.setStyleSheet(f"color: {getattr(self, 'base_status_color', '#00eaff')};")
            except Exception:
                pass

    def _set_label_color_rgb(self, r: int, g: int, b: int):
        self.label.setStyleSheet(f"color: {self._rgb_to_hex(r, g, b)};")

    @staticmethod
    def _hex_to_rgb(h: str) -> tuple[int, int, int]:
        h = h.lstrip('#')
        if len(h) == 3:
            h = ''.join([c*2 for c in h])
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    @staticmethod
    def _rgb_to_hex(r: int, g: int, b: int) -> str:
        return f"#{r:02x}{g:02x}{b:02x}"
