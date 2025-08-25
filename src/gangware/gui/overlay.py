import sys
from pathlib import Path
from typing import Optional, List, Tuple

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QMainWindow, QPushButton, QStackedWidget,
    QGraphicsDropShadowEffect, QFrame, QSizePolicy, QScrollArea,
    QComboBox, QLineEdit
)
from PyQt6.QtGui import QColor, QGuiApplication, QFontDatabase, QFont
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject

from .design_tokens import STATUS_OK, UI_SCALE


class FocusComboBox(QComboBox):
    """Custom ComboBox that only responds to wheel events when focused."""

    def wheelEvent(self, e):
        if self.hasFocus():
            super().wheelEvent(e)
        elif e is not None:
            e.ignore()


class ScrollingLabel(QLabel):
    """Custom QLabel that scrolls horizontally when text is too wide."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._full_text = text
        self._scroll_timer = QTimer(self)
        self._scroll_timer.timeout.connect(self._scroll_text)
        self._scroll_position = 0
        self._scroll_speed = 100  # milliseconds between scroll steps
        self._pause_duration = 2000  # pause at start/end in milliseconds
        self._is_paused = False
        self._pause_timer = QTimer(self)
        self._pause_timer.timeout.connect(self._resume_scroll)
        self._direction = 1  # 1 for right, -1 for left
        self._max_width = 200  # Maximum width before scrolling

    def setText(self, text: str) -> None:
        """Override setText to handle scrolling setup."""
        self._full_text = str(text)
        self._scroll_position = 0
        self._direction = 1
        self._is_paused = False
        self._scroll_timer.stop()
        self._pause_timer.stop()

        # Check if text needs scrolling
        metrics = self.fontMetrics()
        text_width = metrics.horizontalAdvance(self._full_text)

        if text_width > self._max_width:
            # Start with truncated text to prevent stretching
            visible_chars = min(25, len(self._full_text))
            initial_text = self._full_text[:visible_chars]
            if len(self._full_text) > visible_chars:
                initial_text += "..."
            super().setText(initial_text)
            self._start_scroll_cycle()
        else:
            # No scrolling needed
            super().setText(self._full_text)

    def _start_scroll_cycle(self) -> None:
        """Start the scrolling cycle with initial pause."""
        self._is_paused = True
        QTimer.singleShot(0, lambda: self._pause_timer.start(self._pause_duration))

    def _resume_scroll(self) -> None:
        """Resume scrolling after pause."""
        self._is_paused = False
        self._pause_timer.stop()
        QTimer.singleShot(0, lambda: self._scroll_timer.start(self._scroll_speed))

    def _scroll_text(self) -> None:
        """Scroll the text by one character."""
        if not self._full_text or self._is_paused:
            return

        metrics = self.fontMetrics()
        text_width = metrics.horizontalAdvance(self._full_text)

        if text_width <= self._max_width:
            return

        # Calculate visible portion
        if self._direction == 1:  # Moving right (showing left part)
            self._scroll_position += 1
            if self._scroll_position >= len(self._full_text) - 20:  # Near end
                self._direction = -1
                self._pause_at_end()
                return
        else:  # Moving left (showing right part)
            self._scroll_position -= 1
            if self._scroll_position <= 0:  # Back to start
                self._direction = 1
                self._pause_at_start()
                return

        # Update visible text
        visible_chars = min(25, len(self._full_text))  # Show up to 25 characters
        if self._direction == 1:
            visible_text = self._full_text[self._scroll_position:self._scroll_position + visible_chars]
        else:
            start_pos = max(0, len(self._full_text) - visible_chars - self._scroll_position)
            visible_text = self._full_text[start_pos:start_pos + visible_chars]

        super().setText(visible_text + "..." if len(visible_text) < len(self._full_text) else visible_text)

    def _pause_at_end(self) -> None:
        """Pause at the end of text."""
        self._is_paused = True
        self._scroll_timer.stop()
        QTimer.singleShot(0, lambda: self._pause_timer.start(self._pause_duration))

    def _pause_at_start(self) -> None:
        """Pause at the start of text."""
        self._is_paused = True
        self._scroll_timer.stop()
        super().setText(self._full_text[:25] + "..." if len(self._full_text) > 25 else self._full_text)
        QTimer.singleShot(0, lambda: self._pause_timer.start(self._pause_duration))



def spx(n: int) -> int:
    try:
        return int(round(n * UI_SCALE))
    except Exception:
        return int(n)


def glow(widget, color: str = "#00DDFF", radius: int = 28, opacity: int = 150) -> None:
    eff = QGraphicsDropShadowEffect(widget)
    c = QColor(color)
    c.setAlpha(opacity)
    eff.setBlurRadius(radius)
    eff.setColor(c)
    eff.setOffset(0, 0)
    widget.setGraphicsEffect(eff)


class OverlaySignals(QObject):
    recalibrate = pyqtSignal()
    start = pyqtSignal()
    autosim_start = pyqtSignal()
    autosim_stop = pyqtSignal()
    capture_inventory = pyqtSignal()
    capture_tek = pyqtSignal()
    capture_template = pyqtSignal()
    capture_roi = pyqtSignal()
    # New coordinate capture signals
    capture_coordinates = pyqtSignal(str)  # Takes element name as parameter
    # ROI capture signals
    capture_roi_enhanced = pyqtSignal(str)  # Takes ROI type as parameter
    # Hotkey line feedback signals (GUI-thread safe)
    flash_hotkey_line = pyqtSignal(str)
    set_hotkey_line_active = pyqtSignal(str)
    clear_hotkey_line_active = pyqtSignal(str, int)
    # Enhanced success feedback signals
    show_success_feedback = pyqtSignal(str, str)  # hotkey, message
    # Thread-safe UI control signals
    _set_visible_sig = pyqtSignal(bool)
    _set_status_sig = pyqtSignal(str)
    # Thread-safe toggle visibility
    _toggle_visible_sig = pyqtSignal()
    # Thread-safe timer operations
    _delayed_call_sig = pyqtSignal(int, object)  # delay_ms, callable


class OverlayWindow(QMainWindow):
    CYAN = "#00DDFF"
    ORANGE = "#FFB800"
    NONE_DISPLAY = "[ None ]"

    def __init__(self, calibration_mode: bool = False, message: Optional[str] = None):
        super().__init__()
        # State
        self._cal_boxes = {}
        self._hotkey_btns = {}
        self._start_emitted = False
        self._coordinate_dropdown = None
        self._roi_dropdown = None

        # Animation tracking for proper cancellation
        self._active_animations = {}  # hotkey -> list of timer IDs

        # Resolution monitoring
        self._last_resolution = self._get_current_resolution()
        self._resolution_timer = QTimer(self)
        self._resolution_timer.timeout.connect(self._check_resolution_change)
        self._resolution_timer.start(5000)  # Check every 5 seconds

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
        self.signals._set_visible_sig.connect(self.set_visible)
        self.signals._set_status_sig.connect(self._set_status_deferred)
        self.signals._toggle_visible_sig.connect(self.toggle_visibility)
        self.signals._delayed_call_sig.connect(self._handle_delayed_call)
        # GUI-thread safe hotkey feedback wiring
        self.signals.flash_hotkey_line.connect(self._flash_hotkey_line_ui)
        self.signals.set_hotkey_line_active.connect(self._set_hotkey_line_active_ui)
        self.signals.clear_hotkey_line_active.connect(self._clear_hotkey_line_active_ui)
        # Enhanced success feedback wiring
        self.signals.show_success_feedback.connect(self._show_success_feedback_ui)

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
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        glow(title, self.CYAN, 22, 140)
        root.addWidget(title)

        # Subtitle
        subtitle = QLabel("Made by Deacon")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        subtitle.setWordWrap(False)
        subtitle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        f = subtitle.font()
        subtitle.setFont(QFont(f.family(), max(8, f.pointSize() - 2 if f.pointSize() > 0 else 9)))
        root.addWidget(subtitle)

        root.addWidget(self._divider())

        # Tabs
        tabs_row = QWidget()
        tabs = QHBoxLayout(tabs_row)
        tabs.setContentsMargins(0, 0, 0, 0)
        tabs.setSpacing(spx(8))
        self.btn_main_tab = self._nav_button("COMBAT", True)
        self.btn_utils_tab = self._nav_button("UTILITIES", False)
        self.btn_cal_tab = self._nav_button("DEBUG", False)
        tabs.addWidget(self.btn_main_tab)
        tabs.addWidget(self.btn_utils_tab)
        tabs.addWidget(self.btn_cal_tab)
        tabs.addStretch(1)
        root.addWidget(tabs_row)

        # Pages
        self.stack = QStackedWidget()
        self.page_main = self._page_main()
        self.page_utils = self._page_utilities()
        self.page_cal = self._page_calibration()
        self.stack.addWidget(self.page_main)   # index 0
        self.stack.addWidget(self.page_utils)  # index 1
        self.stack.addWidget(self.page_cal)    # index 2
        root.addWidget(self.stack)

        # Footer
        root.addWidget(self._divider())
        self.status_label = ScrollingLabel(message or "")
        self.status_label.setObjectName("status")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(self.status_label)

        # Wire tab switching
        self.btn_main_tab.clicked.connect(lambda: self._switch_tab(0))
        self.btn_utils_tab.clicked.connect(lambda: self._switch_tab(1))
        self.btn_cal_tab.clicked.connect(lambda: self._switch_tab(2))
        self._switch_tab(2 if calibration_mode else 0)

        # Fonts and styles
        self._load_project_fonts()
        self._styles()

        # Size and initial position
        self.resize(spx(520), spx(520))
        wh = self.windowHandle()
        if wh is not None:
            wh.screenChanged.connect(lambda _s: QTimer.singleShot(0, self._anchor_top_right))

    # ------ UI builders ------
    def _switch_tab(self, idx: int):
        self.stack.setCurrentIndex(idx)
        self.btn_main_tab.setChecked(idx == 0)
        self.btn_utils_tab.setChecked(idx == 1)
        self.btn_cal_tab.setChecked(idx == 2)

    def _page_main(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(spx(14))

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(spx(14))
        grid.setVerticalSpacing(spx(14))

        combat = self._section("COMBAT", [
            ("Tek Boost", "Shift+R"),
            ("Medbrew", "Shift+Q"),
            ("Med HoT", "Shift+E"),
        ])
        armor = self._section("ARMOR", [
            ("Flak", "F2"),
            ("Tek", "F3"),
            ("Mixed", "F4"),
        ])
        grid.addWidget(combat, 0, 0)
        grid.addWidget(armor, 0, 1)

        core = self._section("CORE", [
            ("Toggle UI", "F1"),
            ("Exit App", "F10"),
        ])
        outer.addLayout(grid)
        outer.addWidget(core)
        return page

    def _page_utilities(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(spx(14))

        # AUTOSIM section with server input and Start button
        sec = QFrame()
        sec.setObjectName("section")
        glow(sec, self.CYAN, 22, 70)
        v = QVBoxLayout(sec)
        v.setContentsMargins(spx(12), spx(10), spx(12), spx(10))
        v.setSpacing(spx(10))

        t = QLabel("AUTOSIM")
        t.setObjectName("sectionTitle")
        glow(t, self.ORANGE, 18, 130)
        v.addWidget(t)

        # Server number input row
        server_row = QWidget()
        server_h = QHBoxLayout(server_row)
        server_h.setContentsMargins(0, 0, 0, 0)

        server_lbl = QLabel("Server Number (F11):")
        server_lbl.setObjectName("item")
        server_h.addWidget(server_lbl)
        server_h.addStretch(1)

        self._server_input = QLineEdit()
        self._server_input.setObjectName("textInput")
        self._server_input.setPlaceholderText("e.g. 123")
        self._server_input.setFixedWidth(spx(80))
        self._server_input.setFixedHeight(spx(30))
        glow(self._server_input, self.CYAN, 12, 50)
        server_h.addWidget(self._server_input)

        v.addWidget(server_row)

        # Start button row
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)

        name_lbl = QLabel("Start Autosim (menu automation)")
        name_lbl.setObjectName("item")
        h.addWidget(name_lbl)
        h.addStretch(1)

        btn = QPushButton("Start")
        btn.setObjectName("smallBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(spx(36))
        glow(btn, self.CYAN, 20, 100)
        btn.clicked.connect(lambda: self.signals.autosim_start.emit())
        h.addWidget(btn)

        v.addWidget(row)
        outer.addWidget(sec)
        return page

    def _page_calibration(self) -> QWidget:
        # Create scroll area wrapper
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setObjectName("scrollArea")
        scroll_area.setMaximumHeight(spx(400))  # Constrain height to prevent clipping

        # Create scrollable content widget
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setSpacing(spx(12))
        lay.setContentsMargins(spx(6), spx(6), spx(6), spx(6))

        # KEYBIND SETUP section
        kb = QFrame()
        kb.setObjectName("section")
        glow(kb, self.CYAN, 22, 70)
        vb = QVBoxLayout(kb)
        vb.setContentsMargins(spx(10), spx(10), spx(10), spx(10))
        vb.setSpacing(spx(8))

        t1 = QLabel("KEYBIND SETUP")
        t1.setObjectName("sectionTitle")
        glow(t1, self.ORANGE, 18, 120)
        vb.addWidget(t1)

        vb.addWidget(self._cal_row("inventory", "Set Inventory Key", "[ SET ]",
                                  self.signals.capture_inventory.emit))
        vb.addWidget(self._cal_row("tek_cancel", "Set Tek Punch Cancel Key", "[ SET ]",
                                  self.signals.capture_tek.emit))
        lay.addWidget(kb)

        # VISUAL SETUP section
        vs = QFrame()
        vs.setObjectName("section")
        glow(vs, self.CYAN, 22, 70)
        v2 = QVBoxLayout(vs)
        v2.setContentsMargins(spx(10), spx(10), spx(10), spx(10))
        v2.setSpacing(spx(8))

        t2 = QLabel("VISUAL SETUP")
        t2.setObjectName("sectionTitle")
        glow(t2, self.ORANGE, 18, 120)
        v2.addWidget(t2)

        # Dropdown for ROI capture selection
        roi_dropdown_row = QWidget()
        roi_dropdown_layout = QHBoxLayout(roi_dropdown_row)
        roi_dropdown_layout.setContentsMargins(spx(6), spx(4), spx(6), spx(4))
        roi_dropdown_layout.setSpacing(spx(10))

        roi_dropdown_label = QLabel("ROI Capture (F6):")
        roi_dropdown_label.setObjectName("item")
        roi_dropdown_layout.addWidget(roi_dropdown_label)

        self._roi_dropdown = FocusComboBox()
        self._roi_dropdown.setObjectName("dropdown")
        self._roi_dropdown.addItems([
            "DEBUG",
            "Search Bar ROI",
            "Inventory Items ROI"
        ])
        self._roi_dropdown.setMinimumWidth(spx(140))
        self._roi_dropdown.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        roi_dropdown_layout.addWidget(self._roi_dropdown)
        roi_dropdown_layout.addStretch(1)

        v2.addWidget(roi_dropdown_row)
        v2.addSpacing(spx(4))
        lay.addWidget(vs)

        # COORDINATE CAPTURE section
        cs = QFrame()
        cs.setObjectName("section")
        glow(cs, self.CYAN, 22, 70)
        v3 = QVBoxLayout(cs)
        v3.setContentsMargins(spx(10), spx(10), spx(10), spx(10))
        v3.setSpacing(spx(8))

        t3 = QLabel("COORDINATE CAPTURE")
        t3.setObjectName("sectionTitle")
        glow(t3, self.ORANGE, 18, 120)
        v3.addWidget(t3)

        # Dropdown for coordinate element selection
        dropdown_row = QWidget()
        dropdown_layout = QHBoxLayout(dropdown_row)
        dropdown_layout.setContentsMargins(spx(6), spx(4), spx(6), spx(4))
        dropdown_layout.setSpacing(spx(10))

        dropdown_label = QLabel("Select Element (F7):")
        dropdown_label.setObjectName("item")
        dropdown_layout.addWidget(dropdown_label)

        self._coordinate_dropdown = FocusComboBox()
        self._coordinate_dropdown.setObjectName("dropdown")
        self._coordinate_dropdown.addItems([
            "DEBUG",
            "Inv Search",
            "Main Menu",
            "Select Game",
            "Search Box",
            "Join Game",
            "Back",
            "Battleye Symbol"
        ])
        self._coordinate_dropdown.setMinimumWidth(spx(140))
        # Prevent scroll wheel events unless dropdown has focus
        self._coordinate_dropdown.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        dropdown_layout.addWidget(self._coordinate_dropdown)
        dropdown_layout.addStretch(1)

        v3.addWidget(dropdown_row)

        lay.addWidget(cs)

        # Add some bottom spacing for scrolling
        lay.addSpacing(spx(20))

        # Set the scrollable widget
        scroll_area.setWidget(inner)
        return scroll_area

    # ------ Building blocks ------
    def _section(self, title: str, items: List[Tuple[str, str]]):
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
            btn = QPushButton(key)
            btn.setObjectName("smallBtn")
            btn.setEnabled(False)
            btn.setCursor(Qt.CursorShape.ArrowCursor)
            glow(btn, self.CYAN, 20, 100)
            # Store original style for proper reset after animations
            btn.setProperty("originalStyle", btn.styleSheet())
            # Track buttons by hotkey label for feedback effects
            try:
                self._hotkey_btns[key] = btn
            except Exception:
                pass
            h.addWidget(btn)
            v.addWidget(row)
        return frame

    def _cal_row(self, key: str, label: str, btn_text: str, on_click):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(spx(6), spx(4), spx(6), spx(4))
        h.setSpacing(spx(10))
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.setMinimumHeight(spx(60))
        if key == "template":
            h.setContentsMargins(spx(6), spx(6), spx(6), spx(6))

        name_lbl = QLabel(label)
        name_lbl.setObjectName("item")
        name_lbl.setWordWrap(True)
        name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        name_lbl.setMinimumHeight(spx(24))
        name_lbl.setContentsMargins(0, 0, 0, 0)
        if key == "template":
            fm = name_lbl.fontMetrics()
            mh = max(spx(28), fm.height() + spx(6))
            name_lbl.setMinimumHeight(mh)
            name_lbl.setWordWrap(False)
            name_lbl.setMargin(spx(1))
            name_lbl.setContentsMargins(0, spx(2), 0, spx(2))
            name_lbl.setStyleSheet("padding-top: 3px; padding-bottom: 3px;")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        btn = QPushButton(btn_text)
        btn.setObjectName("smallBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(on_click)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn.setFixedHeight(spx(36))
        glow(btn, self.CYAN, 20, 100)

        box = QLabel(self.NONE_DISPLAY)
        box.setObjectName("statusBox")
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.setFixedWidth(spx(140))
        box.setFixedHeight(spx(36))
        box.setProperty("state", "pending")
        _st = box.style()
        if _st is not None:
            _st.unpolish(box)
            _st.polish(box)
        self._cal_boxes[key] = box

        h.addWidget(name_lbl, 1)
        h.addWidget(btn, 0)
        h.addSpacing(spx(12))
        h.addWidget(box, 0)
        return row

    def _nav_button(self, text: str, active: bool) -> QPushButton:
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setChecked(active)
        btn.setObjectName("tab")
        glow(btn, self.CYAN, 24, 90)
        return btn

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(2)
        line.setObjectName("divider")
        return line

    def _load_project_fonts(self) -> None:
        try:
            base = Path(__file__).resolve().parents[3]
            font_dir = next((p for p in [base / "assets" / "fonts", base / "Assets" / "Fonts"] if p.exists()), None)
            if not font_dir:
                return
            for p in font_dir.iterdir():
                if p.suffix.lower() in {".ttf", ".otf"}:
                    QFontDatabase.addApplicationFont(str(p))
        except Exception:
            pass

    def _styles(self) -> None:
        try:
            if getattr(sys, 'frozen', False):
                qss_path = Path(__file__).with_name("theme.qss")
                qss = qss_path.read_text(encoding="utf-8")
            else:
                from . import build_theme as theme_builder
                out_path = theme_builder.build()
                qss = Path(out_path).read_text(encoding="utf-8")
            self.setStyleSheet(qss)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Failed to apply themed stylesheet")

    # ------ Public API (signals wiring expected by main/hotkey manager) ------
    def on_recalibrate(self, slot): self.signals.recalibrate.connect(slot)
    def on_start(self, slot): self.signals.start.connect(slot)
    def on_capture_inventory(self, slot): self.signals.capture_inventory.connect(slot)
    def on_capture_tek(self, slot): self.signals.capture_tek.connect(slot)
    def on_capture_template(self, slot): self.signals.capture_template.connect(slot)
    def on_capture_roi(self, slot): self.signals.capture_roi.connect(slot)
    def on_capture_coordinates(self, slot): self.signals.capture_coordinates.connect(slot)

    def on_capture_roi_enhanced(self, slot): self.signals.capture_roi_enhanced.connect(slot)

    # Utilities / Autosim
    def on_autosim_start(self, slot): self.signals.autosim_start.connect(slot)
    def on_autosim_stop(self, slot): self.signals.autosim_stop.connect(slot)
    def trigger_autosim_start(self) -> None: self.signals.autosim_start.emit()
    def trigger_autosim_stop(self) -> None: self.signals.autosim_stop.emit()

    def toggle_autosim(self) -> None:
        """Toggle autosim start/stop and show overlay accordingly."""
        # Check if autosim is currently running by checking if overlay is hidden
        if not self.isVisible():
            # Autosim is running, stop it
            self.trigger_autosim_stop()
            self.set_visible(True)  # Show overlay
        else:
            # Autosim is not running, start it
            self.trigger_autosim_start()
            self.set_visible(False)  # Hide overlay

    def get_server_number(self) -> str:
        """Get the server number from the autosim input field."""
        if hasattr(self, '_server_input'):
            return self._server_input.text().strip()
        return ""

    def get_selected_coordinate_element(self) -> str:
        """Get the currently selected element from the coordinate dropdown."""
        if self._coordinate_dropdown:
            return self._coordinate_dropdown.currentText()
        return "DEBUG"

    def trigger_coordinate_capture(self) -> None:
        """Trigger coordinate capture for the currently selected element."""
        if self._coordinate_dropdown:
            element_name = self._coordinate_dropdown.currentText()
            if element_name == "DEBUG":
                # DEBUG mode: only log coordinates, don't save to INI
                self.signals.capture_coordinates.emit(f"debug:{element_name}")
            else:
                # Save mode: save coordinates to INI file
                self.signals.capture_coordinates.emit(f"save:{element_name}")

    def get_selected_roi_element(self) -> str:
        """Get the currently selected ROI element from the dropdown."""
        if self._roi_dropdown:
            return self._roi_dropdown.currentText()
        return "DEBUG"

    def trigger_roi_capture(self) -> None:
        """Trigger ROI capture for the currently selected element."""
        if self._roi_dropdown:
            roi_type = self._roi_dropdown.currentText()
            if roi_type == "DEBUG":
                # DEBUG mode: only log and screenshot, don't save to INI
                self.signals.capture_roi_enhanced.emit(f"debug:{roi_type}")
            else:
                # Save mode: save ROI to INI file
                self.signals.capture_roi_enhanced.emit(f"save:{roi_type}")

    # ------ External UI updates ------
    def set_captured_inventory(self, token: str) -> None:
        box = self._cal_boxes.get("inventory")
        if box:
            box.setText(f"[ {self._friendly_token(token)} ]")
            box.setProperty("state", "done")
            box.style().unpolish(box)
            box.style().polish(box)
        self._update_start_enabled()

    def set_captured_tek(self, token: str) -> None:
        box = self._cal_boxes.get("tek_cancel")
        if box:
            box.setText(f"[ {self._friendly_token(token)} ]")
            box.setProperty("state", "done")
            box.style().unpolish(box)
            box.style().polish(box)
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
        _st2 = box.style()
        if _st2 is not None:
            _st2.unpolish(box)
            _st2.polish(box)
        self._update_start_enabled()

    def set_roi_status(self, ok: bool, roi_text: Optional[str] = None) -> None:
        box = self._cal_boxes.get("roi")
        if not box:
            return
        if ok:
            box.setText("[ Set ]")
            box.setToolTip(roi_text or "")
            box.setProperty("state", "done")
        else:
            box.setText(self.NONE_DISPLAY)
            box.setToolTip("")
            box.setProperty("state", "pending")
        box.style().unpolish(box)
        box.style().polish(box)

    # ------ Compatibility API used by HotkeyManager ------
    def set_status(self, text: str) -> None:
        t = text or ""
        if "calibration complete" in t.lower():
            t = "STATUS: OPERATIONAL"
            self.status_label.setProperty("variant", "operational")
            _st3 = self.status_label.style()
            if _st3 is not None:
                _st3.unpolish(self.status_label)
                _st3.polish(self.status_label)
        self.status_label.setText(t)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)

    def set_status_safe(self, text: str) -> None:
        self.signals._set_status_sig.emit(str(text))

    def __call__(self, text: str) -> None:
        """Callable interface for StatusCallbackProtocol compatibility."""
        self.set_status_safe(text)

    def prompt_key_capture(self, prompt: str) -> None:
        self.set_status(prompt)

    def set_visible(self, visible: bool) -> None:
        self.setVisible(bool(visible))

    def set_visible_safe(self, visible: bool) -> None:
        self.signals._set_visible_sig.emit(bool(visible))

    def toggle_visibility_safe(self) -> None:
        try:
            self.signals._toggle_visible_sig.emit()
        except Exception:
            pass

    def switch_to_debug(self) -> None:
        self._start_emitted = False
        self._switch_tab(2)
        self._update_start_enabled()

    # Backward-compatible alias for existing callers
    def switch_to_calibration(self) -> None:
        self.switch_to_debug()

    def switch_to_main(self) -> None:
        self._switch_tab(0)

    def success_flash(self, message: str, duration_ms: int = 1200) -> None:
        prev_text = self.status_label.text()
        prev_style = self.status_label.styleSheet()
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {STATUS_OK};")

        def _restore():
            self.status_label.setText(prev_text)
            self.status_label.setStyleSheet(prev_style)

        self.delayed_call(int(max(0, duration_ms)), _restore)

    def toggle_visibility(self) -> None:
        self.setVisible(not self.isVisible())

    # ------ Hotkey line feedback API ------
    def flash_hotkey_line(self, hotkey: str) -> None:
        """Thread-safe: briefly flash the row button for the given hotkey label.
        Expected labels include: 'Shift+R', 'Shift+E', 'F2', 'F3', 'F4'.
        """
        try:
            self.signals.flash_hotkey_line.emit(str(hotkey))
        except Exception:
            pass

    def set_hotkey_line_active(self, hotkey: str) -> None:
        """Thread-safe: mark the hotkey line as active (e.g., for long-running toggles)."""
        try:
            self.signals.set_hotkey_line_active.emit(str(hotkey))
        except Exception:
            pass

    def clear_hotkey_line_active(self, hotkey: str, fade_duration_ms: int = 400) -> None:
        """Clear active state from hotkey button with fade effect (thread-safe)."""
        self.signals.clear_hotkey_line_active.emit(str(hotkey), fade_duration_ms)

    def show_success_feedback(self, hotkey: str, message: str) -> None:
        """Show success feedback with blue fade and status message (thread-safe)."""
        self.signals.show_success_feedback.emit(str(hotkey), str(message))

    # UI-slot implementations for feedback
    def _flash_hotkey_line_ui(self, hotkey: str) -> None:
        btn = self._hotkey_btns.get(str(hotkey))
        if not btn:
            return
        prev = btn.styleSheet()
        try:
            btn.setStyleSheet("background-color: rgba(0, 150, 255, 0.4);")
        except Exception:
            pass
        self.delayed_call(220, lambda: btn.setStyleSheet(prev))

    def _set_hotkey_line_active_ui(self, hotkey: str) -> None:
        btn = self._hotkey_btns.get(str(hotkey))
        if not btn:
            return
        try:
            btn.setProperty("active", True)
            btn.setStyleSheet("background-color: rgba(0, 150, 255, 0.5);")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        except Exception:
            pass

    def _clear_hotkey_line_active_ui(self, hotkey: str, fade_duration_ms: int = 400) -> None:
        btn = self._hotkey_btns.get(str(hotkey))
        if not btn:
            return

        # Cancel any pending success feedback animations for this button
        self._cancel_button_animations(str(hotkey))

        # Get the original style (before any animations)
        original_style = ""
        try:
            # Try to get the stored original button style
            original_style = btn.property("originalStyle") or ""
        except Exception:
            original_style = ""

        # Immediately start fade to clear state
        try:
            btn.setStyleSheet("background-color: rgba(0, 150, 255, 0.25);")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        except Exception:
            pass

        def _reset():
            try:
                btn.setProperty("active", False)
                btn.setStyleSheet(original_style)
                btn.style().unpolish(btn)
                btn.style().polish(btn)
                # Clear the cancellation flag after reset
                self._clear_cancelled_flag(str(hotkey))
            except Exception:
                pass

        self.delayed_call(int(max(0, fade_duration_ms)), _reset)

    def _handle_delayed_call(self, delay_ms: int, func: object) -> None:
        """Handle delayed function calls on the main GUI thread."""
        try:
            QTimer.singleShot(delay_ms, func)
        except Exception:
            # Fallback: if the function is not callable, ignore silently
            pass

    def delayed_call(self, delay_ms: int, func: object) -> None:
        """Thread-safe delayed function call - can be called from any thread."""
        self.signals._delayed_call_sig.emit(delay_ms, func)

    def _cancel_button_animations(self, hotkey: str) -> None:
        """Cancel any pending animations for a specific button."""
        # Note: QTimer.singleShot timers can't be canceled after creation
        # So we'll use a flag-based approach to prevent execution
        if hasattr(self, '_cancelled_buttons'):
            self._cancelled_buttons.add(str(hotkey))
        else:
            self._cancelled_buttons = {str(hotkey)}

    def _is_animation_cancelled(self, hotkey: str) -> bool:
        """Check if animations for this button have been cancelled."""
        return hasattr(self, '_cancelled_buttons') and str(hotkey) in self._cancelled_buttons

    def _clear_cancelled_flag(self, hotkey: str) -> None:
        """Clear the cancelled flag for a button."""
        if hasattr(self, '_cancelled_buttons'):
            self._cancelled_buttons.discard(str(hotkey))

    def _set_status_deferred(self, text: str) -> None:
        """Thread-safe status update - defers actual update to next event loop iteration."""
        QTimer.singleShot(0, lambda: self.set_status(text))

    def _show_success_feedback_ui(self, hotkey: str, message: str) -> None:
        """Show enhanced success feedback with smooth blue fade and status message."""
        btn = self._hotkey_btns.get(str(hotkey))
        if btn:
            # Clear any previous cancellation flags for this button
            self._clear_cancelled_flag(str(hotkey))

            # Store original style and clear any active states
            prev_style = btn.property("originalStyle") or btn.styleSheet()

            # Clear any active properties that might interfere
            try:
                btn.setProperty("active", False)
                btn.style().unpolish(btn)
                btn.style().polish(btn)
            except Exception:
                pass

            # Start with bright blue highlight (immediate)
            try:
                btn.setStyleSheet(
                    "background-color: rgba(0, 150, 255, 0.8); "
                    "border-color: rgba(0, 150, 255, 1.0);"
                )
                btn.style().unpolish(btn)
                btn.style().polish(btn)
            except Exception:
                pass

            # Create pulse effect - multiple intensity waves
            def _pulse_phase_1():  # 150ms - first pulse peak
                if self._is_animation_cancelled(str(hotkey)):
                    return
                try:
                    btn.setStyleSheet(
                        "background-color: rgba(0, 150, 255, 0.9); "
                        "border-color: rgba(0, 150, 255, 1.0); "
                        "border-width: 2px;"
                    )
                    btn.style().unpolish(btn)
                    btn.style().polish(btn)
                except Exception:
                    pass

            def _pulse_phase_2():  # 300ms - first dip
                if self._is_animation_cancelled(str(hotkey)):
                    return
                try:
                    btn.setStyleSheet(
                        "background-color: rgba(0, 150, 255, 0.4); "
                        "border-color: rgba(0, 150, 255, 0.6); "
                        "border-width: 1px;"
                    )
                    btn.style().unpolish(btn)
                    btn.style().polish(btn)
                except Exception:
                    pass

            def _pulse_phase_3():  # 450ms - second pulse peak (smaller)
                if self._is_animation_cancelled(str(hotkey)):
                    return
                try:
                    btn.setStyleSheet(
                        "background-color: rgba(0, 150, 255, 0.7); "
                        "border-color: rgba(0, 150, 255, 0.85); "
                        "border-width: 2px;"
                    )
                    btn.style().unpolish(btn)
                    btn.style().polish(btn)
                except Exception:
                    pass

            def _pulse_phase_4():  # 600ms - second dip
                if self._is_animation_cancelled(str(hotkey)):
                    return
                try:
                    btn.setStyleSheet(
                        "background-color: rgba(0, 150, 255, 0.3); "
                        "border-color: rgba(0, 150, 255, 0.5); "
                        "border-width: 1px;"
                    )
                    btn.style().unpolish(btn)
                    btn.style().polish(btn)
                except Exception:
                    pass

            def _pulse_phase_5():  # 750ms - third pulse peak (smallest)
                if self._is_animation_cancelled(str(hotkey)):
                    return
                try:
                    btn.setStyleSheet(
                        "background-color: rgba(0, 150, 255, 0.5); "
                        "border-color: rgba(0, 150, 255, 0.7); "
                        "border-width: 1px;"
                    )
                    btn.style().unpolish(btn)
                    btn.style().polish(btn)
                except Exception:
                    pass

            def _pulse_phase_6():  # 900ms - final fade
                if self._is_animation_cancelled(str(hotkey)):
                    return
                try:
                    btn.setStyleSheet(
                        "background-color: rgba(0, 150, 255, 0.15); "
                        "border-color: rgba(0, 150, 255, 0.3); "
                        "border-width: 1px;"
                    )
                    btn.style().unpolish(btn)
                    btn.style().polish(btn)
                except Exception:
                    pass

            def _reset_style():  # 1200ms - back to original
                if self._is_animation_cancelled(str(hotkey)):
                    self._clear_cancelled_flag(str(hotkey))  # Clean up flag
                    return
                try:
                    btn.setStyleSheet(prev_style)
                    btn.setProperty("active", False)  # Ensure clean state
                    btn.style().unpolish(btn)
                    btn.style().polish(btn)
                except Exception:
                    pass

            # Schedule the pulse phases - faster, more dynamic timing
            self.delayed_call(150, _pulse_phase_1)
            self.delayed_call(300, _pulse_phase_2)
            self.delayed_call(450, _pulse_phase_3)
            self.delayed_call(600, _pulse_phase_4)
            self.delayed_call(750, _pulse_phase_5)
            self.delayed_call(900, _pulse_phase_6)
            self.delayed_call(1200, _reset_style)

        # Show success message and auto-reset to operational
        if message:
            self.set_status(message)
            # Auto-reset to operational after pulse completes
            self.delayed_call(1500, lambda: self.set_status("STATUS: OPERATIONAL"))

    def show_window(self):
        self.show()
        QTimer.singleShot(0, self._anchor_top_right)

    def _anchor_top_right(self):
        screen = self.screen() or QGuiApplication.primaryScreen()
        if not screen:
            return
        g = screen.availableGeometry()
        margin = spx(16)
        fw = self.frameGeometry().width() or self.width()
        x = g.x() + g.width() - fw - margin
        y = g.y() + margin
        self.move(max(g.x(), x), max(g.y(), y))

    def resizeEvent(self, event):  # type: ignore
        super().resizeEvent(event)
        self._anchor_top_right()

    # ------ Helpers ------
    def _update_start_enabled(self):
        inv_ok = self._cal_boxes.get("inventory") and self._cal_boxes["inventory"].property("state") == "done"
        tek_ok = self._cal_boxes.get("tek_cancel") and self._cal_boxes["tek_cancel"].property("state") == "done"
        tmpl_ok = (self._cal_boxes.get("template") and
                   str(self._cal_boxes["template"].text()).lower().startswith("[ captured"))
        ready = bool(inv_ok and tek_ok and tmpl_ok)
        if ready and not self._start_emitted:
            self._start_emitted = True
            self.signals.start.emit()

    @staticmethod
    def _friendly_token(token: str) -> str:
        t = (token or "").strip()
        tl = t.lower()
        if tl.startswith("key_"):
            return t[4:]
        if tl.startswith("mouse_"):
            return t[6:]
        return t or "?"

    # ------ Resolution change detection ------
    def _get_current_resolution(self) -> Tuple[int, int]:
        """Get current screen resolution."""
        try:
            screen = QGuiApplication.primaryScreen()
            if screen:
                geometry = screen.geometry()
                return (geometry.width(), geometry.height())
        except Exception:
            pass
        return (1920, 1080)  # Default fallback

    def _check_resolution_change(self) -> None:
        """Check for resolution changes and warn user if detected."""
        try:
            current_resolution = self._get_current_resolution()
            if current_resolution != self._last_resolution:
                self._last_resolution = current_resolution
                warning_msg = (f"⚠️ RESOLUTION CHANGED to {current_resolution[0]}x{current_resolution[1]} - "
                             f"Please restart ARK and Gangware!")
                self.set_status(warning_msg)
                # Set warning color
                try:
                    self.status_label.setStyleSheet("color: #FF6B6B; background-color: rgba(255, 107, 107, 0.1);")
                except Exception:
                    pass
        except Exception:
            pass

    def closeEvent(self, event):
        """Handle window close event with proper timer cleanup."""
        try:
            # Stop resolution monitoring timer safely
            if hasattr(self, '_resolution_timer') and self._resolution_timer.isActive():
                self._resolution_timer.stop()

            # Stop status scrolling timers safely
            if hasattr(self, 'status_label'):
                try:
                    if hasattr(self.status_label, '_scroll_timer'):
                        self.status_label._scroll_timer.stop()
                    if hasattr(self.status_label, '_pause_timer'):
                        self.status_label._pause_timer.stop()
                except Exception:
                    pass
        except Exception:
            # If cleanup fails, continue with close anyway
            pass

        # Call parent closeEvent
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = OverlayWindow()
    w.show_window()
    sys.exit(app.exec())

