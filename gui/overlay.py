"""
Overlay Window Module
User interface overlay using PyQt6.
"""

from PyQt6.QtWidgets import QApplication, QWidget, QLabel
from PyQt6.QtCore import Qt, QRect, QObject, pyqtSignal
from PyQt6.QtGui import QFont


class StatusSignaller(QObject):
    status = pyqtSignal(str)


class OverlayWindow:
    def __init__(self, calibration_mode=False, message=None):
        self.app = QApplication([])
        self.window = QWidget()
        self.window.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput
        )
        self.window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.window.setGeometry(self._get_top_right_geometry(360, 140))
        self.window.setStyleSheet("""
            background: rgba(20, 40, 60, 160);
            border: 2px solid #00eaff;
            border-radius: 12px;
        """)

        # Status label
        if calibration_mode:
            initial_text = message or "Calibration Mode Required:\nPlease complete initial setup."
            color = "#ff0055"
        else:
            initial_text = "GANGWARE AI\nStatus: Online"
            color = "#00eaff"

        self.label = QLabel(initial_text, self.window)
        self.label.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        self.label.setStyleSheet(f"""
            color: {color};
        """)
        self.label.setGeometry(QRect(16, 12, 328, 116))
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # Signaller for thread-safe status updates
        self.signaller = StatusSignaller()
        self.signaller.status.connect(self._update_status)

    def _update_status(self, text: str):
        # Update label text; runs in GUI thread because signal is connected
        self.label.setText(text)

    def set_status(self, text: str):
        # Public method for other threads to request a status update
        self.signaller.status.emit(text)

    def _get_top_right_geometry(self, width, height):
        screen = self.app.primaryScreen().geometry()
        x = screen.width() - width - 20
        y = 20
        return QRect(x, y, width, height)

    def show(self):
        self.window.show()
        self.app.exec()
