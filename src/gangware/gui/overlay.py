import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QMainWindow, QPushButton, QStackedWidget,
    QGraphicsDropShadowEffect, QFrame, QScrollArea
)
from PyQt6.QtGui import QColor, QGuiApplication
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from .design_tokens import STATUS_OK

# Global UI scale (~34% reduction)
UI_SCALE = 0.66


def spx(n: int) -> int:
    """Scale integer pixel values by UI_SCALE."""
    try:
        return int(round(n * UI_SCALE))
    except Exception:
        return int(n)


# ---------- Neon helpers ----------

def glow(widget, color="#00DDFF", radius=28, opacity=150):
    eff = QGraphicsDropShadowEffect(widget)
    c = QColor(color)
    c.setAlpha(opacity)
    eff.setBlurRadius(radius)
    eff.setColor(c)
    eff.setOffset(0, 0)
    widget.setGraphicsEffect(eff)


class Keycap(QWidget):
    """Rounded cyan 'key' cap like Shift+R, F2, etc."""

    def __init__(self, text: str, minw: int = 120, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(spx(minw))
        self.setFixedHeight(spx(28))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        btn = QPushButton(text)
        btn.setEnabled(False)
        btn.setCursor(Qt.CursorShape.ArrowCursor)
        btn.setObjectName("keycap")
        btn.setMinimumWidth(spx(minw))
        lay.addWidget(btn)
        glow(btn, "#00DDFF", 26, 120)


class OverlaySignals(QObject):
    recalibrate = pyqtSignal()
    start = pyqtSignal()
    capture_inventory = pyqtSignal()
    capture_tek = pyqtSignal()
    capture_template = pyqtSignal()


class OverlayWindow(QMainWindow):
    CYAN = "#00DDFF"
    ORANGE = "#FFB800"
    NONE_DISPLAY = "[ None ]"

    def __init__(self, calibration_mode: bool = False, message: Optional[str] = None):
        super().__init__()

        # Window flags and transparency
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Signals
        self.signals = OverlaySignals(self)

        # Calibration state containers
        self._cal_boxes = {}
        self._start_emitted = False  # auto-start gate

        # Root card container
        card = QWidget()
        card.setObjectName("card")
        self.setCentralWidget(card)

        root = QVBoxLayout(card)
        root.setContentsMargins(spx(12), spx(12), spx(12), spx(12))
        root.setSpacing(spx(12))

        # Header title
        title = QLabel("GANGWARE")
        title.setObjectName("title")
        glow(title, self.CYAN, 22, 140)
        root.addWidget(title)
        root.addWidget(self._divider())

        # Tabs
        tabs_row = QWidget()
        tabs = QHBoxLayout(tabs_row)
        tabs.setContentsMargins(0, 0, 0, 0)
        tabs.setSpacing(spx(8))
        self.btn_main_tab = self._nav_button("MAIN", True)
        self.btn_cal_tab = self._nav_button("CALIBRATION", False)
        tabs.addWidget(self.btn_main_tab)
        tabs.addWidget(self.btn_cal_tab)
        tabs.addStretch(1)
        root.addWidget(tabs_row)

        # Pages
        self.stack = QStackedWidget()
        self.page_main = self._page_main()
        self.page_cal = self._page_calibration()
        self.stack.addWidget(self.page_main)
        self.stack.addWidget(self.page_cal)
        root.addWidget(self.stack)

        # Footer
        root.addWidget(self._divider())
        self.status_label = QLabel(message or "")
        self.status_label.setObjectName("status")
        root.addWidget(self.status_label)

        # Wire tab switching
        self.btn_main_tab.clicked.connect(lambda: self._switch_tab(0))
        self.btn_cal_tab.clicked.connect(lambda: self._switch_tab(1))

        # Default page
        self._switch_tab(1 if calibration_mode else 0)

        # Styles
        self._styles()

        # Size and initial position (scaled)
        self.resize(spx(500), spx(520))

        # Re-anchor if the window's screen changes (multi-monitor support)
        try:
            wh = self.windowHandle()
            if wh is not None:
                wh.screenChanged.connect(lambda _s: QTimer.singleShot(0, self._anchor_top_right))
        except Exception:
            pass

    # ------ UI builders ------
    def _switch_tab(self, idx: int):
        self.stack.setCurrentIndex(idx)
        self.btn_main_tab.setChecked(idx == 0)
        self.btn_cal_tab.setChecked(idx == 1)

    def _page_main(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(spx(14))

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(spx(14))
        grid.setVerticalSpacing(spx(14))

        # Left column: COMBAT
        combat = self._section("COMBAT", [
            ("Tek Dash", "Shift+R"),
            ("Medbrew", "Shift+Q"),
            ("Med HoT", "Shift+E"),
        ])

        # Right column: ARMOR
        armor = self._section("ARMOR", [
            ("Flak", "F2"),
            ("Tek", "F3"),
            ("Mixed", "F4"),
        ])

        grid.addWidget(combat, 0, 0)
        grid.addWidget(armor, 0, 1)

        # Core (full width)
        core = self._section("CORE", [
            ("Toggle UI", "F1"),
            ("Exit App",  "F10"),
        ])
        outer.addLayout(grid)
        outer.addWidget(core)
        return page

    def _page_calibration(self):
        """
        Keeps your simple page structure, but implements the
        HTML-like rows: [ SET ] / [ CAPTURE ] + a status box.
        """
        # Inner page with content
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setSpacing(spx(12))
        lay.setContentsMargins(0, 0, 0, 0)

        # KEYBIND SETUP section
        kb = QFrame()
        kb.setObjectName("section")
        glow(kb, self.CYAN, 22, 70)
        vb = QVBoxLayout(kb)
        vb.setContentsMargins(spx(12), spx(10), spx(12), spx(10))
        vb.setSpacing(spx(10))

        t1 = QLabel("KEYBIND SETUP")
        t1.setObjectName("sectionTitle")
        glow(t1, self.ORANGE, 18, 120)
        vb.addWidget(t1)

        vb.addWidget(self._cal_row("inventory", "Set Inventory Key", "[ SET ]",
                                   lambda: self.signals.capture_inventory.emit()))
        vb.addWidget(self._cal_row("tek_cancel", "Set Tek Dash Cancel Key", "[ SET ]",
                                   lambda: self.signals.capture_tek.emit()))
        lay.addWidget(kb)

        # VISUAL SETUP section
        vs = QFrame()
        vs.setObjectName("section")
        glow(vs, self.CYAN, 22, 70)
        v2 = QVBoxLayout(vs)
        v2.setContentsMargins(spx(12), spx(10), spx(12), spx(10))
        v2.setSpacing(spx(10))

        t2 = QLabel("VISUAL SETUP")
        t2.setObjectName("sectionTitle")
        glow(t2, self.ORANGE, 18, 120)
        v2.addWidget(t2)

        v2.addWidget(self._cal_row("template", "Capture Search Bar (F8)", "[ CAPTURE ]",
                                   lambda: self.signals.capture_template.emit()))
        lay.addWidget(vs)

        # Footer divider only (no Start button)
        footer = QWidget()
        fl = QVBoxLayout(footer)
        fl.setContentsMargins(0, spx(8), 0, 0)
        fl.addWidget(self._divider())
        lay.addWidget(footer)

        # Make whole calibration page scrollable (safety)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(inner)
        return scroll

    # ------ Building blocks ------
    def _section(self, title: str, items: list[tuple[str, str]]):
        frame = QFrame()
        frame.setObjectName("section")
        glow(frame, self.CYAN, 22, 70)

        v = QVBoxLayout(frame)
        v.setContentsMargins(spx(12), spx(10), spx(12), spx(10))
        v.setSpacing(spx(10))

        t = QLabel(title)
        t.setObjectName("sectionTitle")
        glow(t, self.ORANGE, 18, 130)
        v.addWidget(t)

        for name, key in items:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            name_lbl = QLabel(name)
            name_lbl.setObjectName("item")
            h.addWidget(name_lbl)
            h.addStretch(1)
            h.addWidget(self._hotkey_button(key))
            v.addWidget(row)

        return frame

    def _cal_row(self, key: str, label: str, btn_text: str, on_click):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(spx(8))

        name_lbl = QLabel(label)
        name_lbl.setObjectName("item")

        btn = QPushButton(btn_text)
        btn.setObjectName("smallBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(on_click)
        glow(btn, self.CYAN, 20, 100)

        box = QLabel(self.NONE_DISPLAY)
        box.setObjectName("statusBox")
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.setMinimumWidth(spx(120))
        box.setFixedHeight(spx(36))
        box.setProperty("state", "pending")
        box.style().unpolish(box); box.style().polish(box)

        self._cal_boxes[key] = box

        h.addWidget(name_lbl)
        h.addStretch(1)
        h.addWidget(btn)
        h.addSpacing(spx(8))
        h.addWidget(box)
        return row

    def _nav_button(self, text: str, active: bool):
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setChecked(active)
        btn.setObjectName("tab")
        glow(btn, self.CYAN, 24, 90)
        return btn

    def _hotkey_button(self, text: str) -> QPushButton:
        """Create a small-style disabled button to display hotkey text on Main page."""
        btn = QPushButton(text)
        btn.setObjectName("smallBtn")
        btn.setEnabled(False)
        btn.setCursor(Qt.CursorShape.ArrowCursor)
        glow(btn, self.CYAN, 20, 100)
        return btn

    def _divider(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(2)
        line.setObjectName("divider")
        return line

    # ------ StyleSheet ------
    def _styles(self):
        try:
            # Build and apply generated QSS from tokens
            from . import build_theme as theme_builder
            out_path = theme_builder.build()
            qss = Path(out_path).read_text(encoding="utf-8")
            self.setStyleSheet(qss)
        except Exception as e:
            # Fallback: leave default styles if build fails
            print(f"Failed to apply themed stylesheet: {e}")

    # ------ Public API (signals wiring expected by main/hotkey manager) ------
    def on_recalibrate(self, slot):
        self.signals.recalibrate.connect(slot)

    def on_start(self, slot):
        self.signals.start.connect(slot)

    def on_capture_inventory(self, slot):
        self.signals.capture_inventory.connect(slot)

    def on_capture_tek(self, slot):
        self.signals.capture_tek.connect(slot)

    def on_capture_template(self, slot):
        self.signals.capture_template.connect(slot)

    # For external callers to push results back into the UI
    def set_captured_inventory(self, token: str) -> None:
        box = self._cal_boxes.get("inventory")
        if box:
            box.setText(f"[ {self._friendly_token(token)} ]")
            box.setProperty("state", "done")
            box.style().unpolish(box); box.style().polish(box)
        self._update_start_enabled()

    def set_captured_tek(self, token: str) -> None:
        box = self._cal_boxes.get("tek_cancel")
        if box:
            box.setText(f"[ {self._friendly_token(token)} ]")
            box.setProperty("state", "done")
            box.style().unpolish(box); box.style().polish(box)
        self._update_start_enabled()

    def set_template_status(self, ok: bool, path: Optional[str] = None) -> None:
        box = self._cal_boxes.get("template")
        if not box:
            return
        if ok:
            box.setText("[ Captured ]")
            box.setToolTip(path or "")
            box.setProperty("state", "done")
        else:
            box.setText(self.NONE_DISPLAY)
            box.setToolTip("")
            box.setProperty("state", "pending")
        box.style().unpolish(box); box.style().polish(box)
        self._update_start_enabled()

    # ------ Compatibility API used by HotkeyManager ------
    def set_status(self, text: str) -> None:
        try:
            self.status_label.setText(text or "")
        except Exception:
            pass

    def prompt_key_capture(self, prompt: str) -> None:
        self.set_status(prompt)

    def set_visible(self, visible: bool) -> None:
        try:
            self.setVisible(bool(visible))
        except Exception:
            pass

    def switch_to_calibration(self) -> None:
        try:
            # Reset auto-start state on entering calibration
            self._start_emitted = False
            self._switch_tab(1)
            # In case values were prefilled, this can auto-start immediately
            self._update_start_enabled()
        except Exception:
            pass

    def switch_to_main(self) -> None:
        try:
            self._switch_tab(0)
        except Exception:
            pass

    def success_flash(self, message: str, duration_ms: int = 1200) -> None:
        """Temporarily show a success message in green, then restore previous."""
        try:
            prev_text = self.status_label.text()
            prev_style = self.status_label.styleSheet()
            self.status_label.setText(message)
            self.status_label.setStyleSheet(f"color: {STATUS_OK};")

            def _restore():
                try:
                    self.status_label.setText(prev_text)
                    self.status_label.setStyleSheet(prev_style)
                except Exception:
                    pass

            QTimer.singleShot(int(max(0, duration_ms)), _restore)
        except Exception:
            pass

    def show_window(self):
        self.show()
        QTimer.singleShot(0, self._anchor_top_right)

    def _anchor_top_right(self):
        # Determine target screen: prefer current window screen, fallback to primary
        screen = self.screen() or QGuiApplication.primaryScreen()
        if not screen:
            return
        g = screen.availableGeometry()
        margin = spx(16)
        fw = self.frameGeometry().width() or self.width()
        x = g.x() + g.width() - fw - margin
        y = g.y() + margin
        self.move(max(g.x(), x), max(g.y(), y))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep anchored top-right on resize
        self._anchor_top_right()

    # ------ Helpers ------
    def _update_start_enabled(self):
        inv_ok = self._cal_boxes.get("inventory") and self._cal_boxes["inventory"].property("state") == "done"
        tek_ok = self._cal_boxes.get("tek_cancel") and self._cal_boxes["tek_cancel"].property("state") == "done"
        tmpl_ok = self._cal_boxes.get("template") and self._cal_boxes["template"].text().lower().startswith("[ captured")
        ready = bool(inv_ok and tek_ok and tmpl_ok)
        # Auto-emit start once when all three are ready
        if ready and not self._start_emitted:
            self._start_emitted = True
            try:
                self.signals.start.emit()
            except Exception:
                pass

    @staticmethod
    def _friendly_token(token: str) -> str:
        t = (token or "").strip()
        tl = t.lower()
        if tl.startswith("key_"):
            return t[4:]
        if tl.startswith("mouse_"):
            return t[6:]
        return t or "?"


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = OverlayWindow()
    w.show_window()
    sys.exit(app.exec())