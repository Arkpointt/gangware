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
        self.window.setStyleSheet(
            """
            background: qlineargradient(
                spread:pad, x1:0, y1:0, x2:1, y2:1,
                stop:0 rgba(8,18,28,200), stop:1 rgba(18,38,58,180)
            );
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
