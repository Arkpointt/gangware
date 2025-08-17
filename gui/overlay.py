
"""
Overlay Window Module
User interface overlay using PyQt6.
"""

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt

class OverlayWindow:
    """
    Frameless, on-top, themed overlay window.
    """
    def __init__(self):
        self.app = QApplication([])
        self.window = QWidget()
        self.window.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.window.setGeometry(100, 100, 800, 600)  # Example size and position
        self.window.setStyleSheet("background: rgba(30, 30, 30, 180);")

    def show(self):
        self.window.show()
        self.app.exec()
