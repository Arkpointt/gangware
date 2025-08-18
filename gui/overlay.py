
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

from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QShortcut
from PyQt6.QtCore import Qt, QRect, QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QKeySequence


class StatusSignaller(QObject):
    status = pyqtSignal(str)
    recalibrate = pyqtSignal()
    visibility = pyqtSignal(bool)
    toggle = pyqtSignal()


class OverlayWindow:
    def __init__(self, calibration_mode: bool = False, message: str | None = None):
        # App and window
        self.app = QApplication([])
        self.window = QWidget()
        self.window.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.window.setGeometry(self._get_top_right_geometry(360, 140))
        self.window.setStyleSheet(
            """
            background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 rgba(8,18,28,200), stop:1 rgba(18,38,58,180));
            border: 1px solid rgba(0,234,255,0.9);
            border-radius: 12px;
            font-family: 'Consolas', 'Courier New', monospace;
            """
        )

        # Status layout: header + status line
        if calibration_mode:
            header = "GANGWARE AI - CALIBRATION"
            status_text = message or "Calibration required: please complete initial setup."
            status_color = "#ff7a7a"
        else:
            header = "GANGWARE AI"
            status_text = "Status: Online"
            status_color = "#00eaff"

        # Header label (small, neon)
        self.header_label = QLabel(f"<b>{header}</b>", self.window)
        self.header_label.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        self.header_label.setStyleSheet("color: rgba(200,220,255,0.95);")
        self.header_label.setGeometry(QRect(18, 10, 320, 28))

        # Status label (dynamic)
        self.label = QLabel(status_text, self.window)
        self.label.setFont(QFont("Consolas", 12))
        self.label.setStyleSheet(f"color: {status_color};")
        self.label.setGeometry(QRect(18, 40, 320, 88))
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        # Signaller for thread-safe status and visibility updates
        self.signaller = StatusSignaller()
        self.signaller.status.connect(self._update_status)
        self.signaller.visibility.connect(self._set_visible)
        self.signaller.toggle.connect(self._toggle_visible)

        # Ensure initial anchor after show/layout and react to screen changes
        QTimer.singleShot(0, self.reposition)

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

        # Global shortcut: F7 triggers recalibration request
        self._shortcut_recal = QShortcut(QKeySequence("F7"), self.window)
        self._shortcut_recal.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._shortcut_recal.activated.connect(lambda: self.signaller.recalibrate.emit())

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

    def switch_to_main(self):
        """Switch the overlay visuals from calibration to main mode."""
        try:
            self.header_label.setText("<b>GANGWARE AI</b>")
            self.label.setStyleSheet("color: #00eaff;")
            self.set_status("Status: Online")
        except Exception:
            # Do not let UI errors crash the application
            pass

    def _set_visible(self, visible: bool):
        # Runs in GUI thread via signal; show/hide safely and re-anchor
        if visible:
            self.window.show()
            self.reposition()
        else:
            self.window.hide()

    def _toggle_visible(self):
        self._set_visible(not self.window.isVisible())

    def set_visible(self, visible: bool):
        # Thread-safe setter for visibility
        self.signaller.visibility.emit(visible)

    def toggle_visibility(self):
        # Thread-safe toggle
        self.signaller.toggle.emit()

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
        self.app.exec()
