"""
Gangware Overlay (PyQt6)

Clean, professional overlay UI:
- Frameless, translucent, always-on-top, anchored top-right.
- Navigation: Main and Calibration pages via QStackedWidget.
- Main: Macro hotkeys in two columns with stylized key boxes and flash feedback.
- Calibration: Set Inventory Key, Set Tek Cancel Key, Capture Template, Start button, Back to Main.

Public API (used by other components):
- set_status(text), set_visible(bool), toggle_visibility()
- switch_to_main(), switch_to_calibration()
- on_recalibrate(slot), on_start(slot)
- on_capture_inventory(slot), on_capture_tek(slot), on_capture_template(slot)
- set_captured_inventory(token), set_captured_tek(token), set_template_status(ok, path)
- success_flash(text=None, duration_ms=1200)
- flash_hotkey_line(hotkey, duration_ms=2000)
- set_hotkey_line_active(hotkey), clear_hotkey_line_active(hotkey, fade_duration_ms=2000)
"""

from __future__ import annotations

import os
from typing import Callable, Dict, Optional

from PyQt6.QtCore import QObject, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class _Signals(QObject):
    status = pyqtSignal(str)
    visibility = pyqtSignal(bool)
    toggle = pyqtSignal()
    switch_to_main = pyqtSignal()
    switch_to_calib = pyqtSignal()
    start = pyqtSignal()
    recalibrate = pyqtSignal()
    capture_inventory = pyqtSignal()
    capture_tek = pyqtSignal()
    capture_template = pyqtSignal()
    inv_value = pyqtSignal(str)
    tek_value = pyqtSignal(str)
    tmpl_status = pyqtSignal(bool, str)
    success = pyqtSignal(str, int)
    flash_line = pyqtSignal(str, int)
    hold_line = pyqtSignal(str)
    clear_line = pyqtSignal(str, int)


class OverlayWindow:
    CYAN = "#00D8FF"
    ORANGE = "#FFB800"
    GRAY = "#E0E0E0"
    MAX_WIDTH = 520
    NONE_DISPLAY = "[ None ]"

    def __init__(self, calibration_mode: bool = False, message: Optional[str] = None) -> None:
        self.calibration_mode = bool(calibration_mode)
        self.initial_message = message or ""

        self.app = QApplication.instance() or QApplication([])
        self.window = QWidget()
        self.window.setMaximumWidth(self.MAX_WIDTH)
        self.window.setObjectName("gw-root")
        self.window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._set_flags(click_through=not self.calibration_mode)

        # Root styled frame
        self.root = QVBoxLayout(self.window)
        self.root.setContentsMargins(14, 12, 14, 12)
        self.root.setSpacing(10)

        self.chrome = QFrame(self.window)
        self.chrome.setObjectName("gw-chrome")
        self.chrome.setStyleSheet(
            f"""
            #gw-chrome {{
                background-color: rgba(20,20,24,210);
                border: 1px solid {self.CYAN};
                border-radius: 12px;
            }}
            QWidget {{ font-family: Consolas; color: {self.GRAY}; }}
            QPushButton {{
                background-color: rgba(0,216,255,0.18);
                border: 1px solid {self.CYAN};
                border-radius: 6px;
                padding: 6px 10px;
                color: {self.GRAY};
            }}
            QPushButton:hover {{ background-color: rgba(0,216,255,0.32); }}
            QPushButton:pressed {{ background-color: rgba(0,216,255,0.22); }}
            QLabel.keybox {{
                border: 1px solid rgba(0,216,255,0.45);
                border-radius: 4px; padding: 3px 8px; color: {self.GRAY};
            }}
            QLabel.title {{ color: {self.CYAN}; font-weight: 700; }}
            QLabel.section {{ color: {self.ORANGE}; font-weight: 700; }}
            """
        )
        self.root.addWidget(self.chrome)

        self.vbox = QVBoxLayout(self.chrome)
        self.vbox.setContentsMargins(12, 10, 12, 10)
        self.vbox.setSpacing(8)

        # Header
        self.header = QLabel("GANGWARE", self.chrome)
        self.header.setProperty("class", "title")
        self.header.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        self.vbox.addWidget(self.header)

        # Navigation
        nav = QHBoxLayout()
        self.btn_main = QPushButton("Main", self.chrome)
        self.btn_calib = QPushButton("Calibration", self.chrome)
        for b in (self.btn_main, self.btn_calib):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_main.clicked.connect(lambda: self._show_page(0))
        self.btn_calib.clicked.connect(lambda: self._show_page(1))
        nav.addWidget(self.btn_main)
        nav.addWidget(self.btn_calib)
        self.vbox.addLayout(nav)

        # Stack
        self.stack = QStackedWidget(self.chrome)
        self.vbox.addWidget(self.stack, 1)

        # Footer status line
        self.status = QLabel(self.initial_message or "Status: Online", self.chrome)
        self.status.setWordWrap(True)
        self.vbox.addWidget(self.status)

        # Pages
        self._hotkey_labels: Dict[str, QLabel] = {}
        self.page_main = self._build_main()
        self.page_calib = self._build_calibration()
        self.stack.addWidget(self.page_main)
        self.stack.addWidget(self.page_calib)

        # Signals (queued)
        self.signals = _Signals()
        q = Qt.ConnectionType.QueuedConnection
        self.signals.status.connect(self._set_status_ui, q)
        self.signals.visibility.connect(self._set_visible_ui, q)
        self.signals.toggle.connect(self._toggle_visible_ui, q)
        self.signals.switch_to_main.connect(lambda: self._show_page(0), q)
        self.signals.switch_to_calib.connect(lambda: self._show_page(1), q)
        self.signals.inv_value.connect(self._set_captured_inventory_ui, q)
        self.signals.tek_value.connect(self._set_captured_tek_ui, q)
        self.signals.tmpl_status.connect(self._set_template_status_ui, q)
        self.signals.success.connect(self._success_flash_ui, q)
        self.signals.flash_line.connect(self._flash_line_ui, q)
        self.signals.hold_line.connect(self._hold_line_ui, q)
        self.signals.clear_line.connect(self._clear_line_ui, q)

        # Shortcuts
        sc_toggle = QShortcut(QKeySequence("F1"), self.window)
        sc_toggle.setContext(Qt.ShortcutContext.ApplicationShortcut)
        sc_toggle.activated.connect(lambda: self.signals.toggle.emit())
        sc_recal = QShortcut(QKeySequence("F7"), self.window)
        sc_recal.setContext(Qt.ShortcutContext.ApplicationShortcut)
        sc_recal.activated.connect(lambda: self.signals.recalibrate.emit())
        sc_exit = QShortcut(QKeySequence("F10"), self.window)
        sc_exit.setContext(Qt.ShortcutContext.ApplicationShortcut)
        sc_exit.activated.connect(lambda: os._exit(0))

        # Geometry and start page
        self._anchor_top_right(self.MAX_WIDTH, 360)
        self._show_page(1 if self.calibration_mode else 0)
        self.window.setWindowTitle("Gangware")
        self.window.setWindowOpacity(0.98)
        self.window.show()

        # Internal timers
        self._status_flash_timer: Optional[QTimer] = None
        self._value_flash_timers: Dict[QLabel, QTimer] = {}

        QTimer.singleShot(0, lambda: self._anchor_top_right(self.MAX_WIDTH, 360))

    # ---- Window flags / placement ----
    def _set_flags(self, click_through: bool) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        if click_through:
            flags |= Qt.WindowType.WindowTransparentForInput
        self.window.setWindowFlags(flags)

    def _anchor_top_right(self, width: int, height: int) -> None:
        screen = self.app.primaryScreen()
        rect = screen.availableGeometry()
        x = rect.x() + rect.width() - width - 20
        y = rect.y() + 20
        self.window.setGeometry(QRect(x, y, width, height))

    # ---- Build pages ----
    def _build_main(self) -> QWidget:
        page = QWidget(self.chrome)
        grid = QGridLayout(page)
        grid.setContentsMargins(6, 6, 6, 6)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(10)

        title = QLabel("Macro Hotkeys (Ark window only)", page)
        title.setProperty("class", "section")
        title.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        title.setWordWrap(True)
        grid.addWidget(title, 0, 0, 1, 4)

        entries = [
            ("Equip Flak Armor", "F2"),
            ("Equip Tek Armor", "F3"),
            ("Equip Mixed Armor", "F4"),
            ("Medbrew Burst", "Shift+Q"),
            ("Medbrew Heal-over-Time (Toggle)", "Shift+E"),
            ("Tek Punch", "Shift+R"),
        ]

        def add_row(r: int, desc: str, key: str, c: int) -> None:
            d = QLabel(desc, page)
            d.setFont(QFont("Consolas", 10))
            d.setWordWrap(True)
            k = QLabel(key, page)
            k.setAlignment(Qt.AlignmentFlag.AlignCenter)
            k.setProperty("class", "keybox")
            k.setMinimumWidth(72)
            self._hotkey_labels[key] = k
            grid.addWidget(d, r, c)
            grid.addWidget(k, r, c + 1)

        row = 1
        for i, (desc, key) in enumerate(entries):
            col = 0 if i % 2 == 0 else 2
            if i % 2 == 0 and i > 0:
                row += 1
            add_row(row, desc, key, col)

        return page

    def _build_calibration(self) -> QWidget:
        page = QWidget(self.chrome)
        # Ensure calibration page inherits chrome background (transparent) and not white
        try:
            page.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        except Exception:
            pass
        page.setStyleSheet("background: transparent;")
        v = QVBoxLayout(page)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(10)

        # Rich descriptions
        desc = QLabel(page)
        desc.setWordWrap(True)
        desc.setText(
            "<b>Calibration</b><br><br>"
            "<b>Inventory Key Button</b><br>"
            "<i>Function</i>: One-time setup key.<br>"
            "<i>Description</i>: When prompted by the GUI, press the key or mouse button you personally use to open your inventory (e.g., 'I' or 'Mouse4'). The application saves this so the AI knows how to open your inventory during macros." \
            "<br><br>"
            "<b>Tek Dash Button</b><br>"
            "<i>Function</i>: In-game macro hotkey (Shift+R).<br>"
            "<i>Description</i>: When you press Shift+R, it triggers the AI to execute the Tek Dash (Tek Boost) macro: a rapid, animation-canceling punch sequence for high-speed movement. The <b>Tek Cancel</b> key you set here is used inside this macro to cleanly cancel the punch animation." \
            "<br><br>"
            "<b>Inventory Image Button</b><br>"
            "<i>Function</i>: One-time setup capture.<br>"
            "<i>Description</i>: When prompted, hover your mouse over the inventory search bar and press F8. This captures a small screenshot to create a visual template that computer vision uses to locate where to click and type in your UI." \
            "<br><br>"
            "Complete all three, then click <b>Start</b> to return to the main overlay."
        )
        v.addWidget(desc)

        # Rows
        k_title = QLabel("Keybinds", page)
        k_title.setProperty("class", "section")
        k_title.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        v.addWidget(k_title)

        self.inv_row = self._task_row(page, "Set Inventory Key", "[SET]", lambda: self.signals.capture_inventory.emit())
        v.addLayout(self.inv_row)
        self.tek_row = self._task_row(page, "Set Tek Cancel Key", "[SET]", lambda: self.signals.capture_tek.emit())
        v.addLayout(self.tek_row)

        t_title = QLabel("Visual Templates", page)
        t_title.setProperty("class", "section")
        t_title.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        v.addWidget(t_title)

        self.tmpl_row = self._task_row(
            page,
            "Capture Inventory Template (hover search bar, press F8)",
            "Capture",
            lambda: self.signals.capture_template.emit(),
        )
        v.addLayout(self.tmpl_row)

        # Action buttons
        hb = QHBoxLayout()
        self.btn_back = QPushButton("Back to Main", page)
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.clicked.connect(lambda: self.signals.switch_to_main.emit())
        hb.addWidget(self.btn_back)
        hb.addStretch(1)
        self.btn_start = QPushButton("Start", page)
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(lambda: self.signals.start.emit())
        hb.addWidget(self.btn_start)
        v.addLayout(hb)

        scroll = QScrollArea(self.chrome)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Make scroll area and viewport transparent to show chrome background
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        try:
            scroll.viewport().setStyleSheet("background: transparent;")
        except Exception:
            pass
        scroll.setWidget(page)
        return scroll

    def _task_row(self, parent: QWidget, text: str, btn_text: str, on_click: Callable[[], None]) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        lbl = QLabel(text, parent)
        lbl.setFont(QFont("Consolas", 10))
        lbl.setWordWrap(True)
        btn = QPushButton(btn_text, parent)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(on_click)
        box = QLabel(self.NONE_DISPLAY, parent)
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.setProperty("class", "keybox")
        box.setMinimumWidth(120)
        row.addWidget(lbl, 1)
        row.addWidget(btn, 0)
        row.addWidget(box, 0)
        row._gw_display_box = box  # type: ignore[attr-defined]
        row._gw_button = btn       # type: ignore[attr-defined]
        return row

    # ---- Public API ----
    def set_status(self, text: str) -> None:
        self.signals.status.emit(text)

    def prompt_key_capture(self, prompt: str) -> None:
        # Display a prompt in the status line during key capture
        try:
            self.signals.status.emit(str(prompt))
        except Exception:
            pass

    def toggle_visibility(self) -> None:
        self.signals.toggle.emit()

    def set_visible(self, visible: bool) -> None:
        self.signals.visibility.emit(bool(visible))

    def switch_to_main(self) -> None:
        self.signals.switch_to_main.emit()

    def switch_to_calibration(self) -> None:
        self.signals.switch_to_calib.emit()

    def on_recalibrate(self, slot: Callable[[], None]):
        self.signals.recalibrate.connect(slot)

    def on_start(self, slot: Callable[[], None]):
        self.signals.start.connect(slot)

    def on_capture_inventory(self, slot: Callable[[], None]):
        self.signals.capture_inventory.connect(slot)

    def on_capture_tek(self, slot: Callable[[], None]):
        self.signals.capture_tek.connect(slot)

    def on_capture_template(self, slot: Callable[[], None]):
        self.signals.capture_template.connect(slot)

    def set_captured_inventory(self, token: str) -> None:
        self.signals.inv_value.emit(token)

    def set_captured_tek(self, token: str) -> None:
        self.signals.tek_value.emit(token)

    def set_template_status(self, ok: bool, path: Optional[str] = None) -> None:
        self.signals.tmpl_status.emit(bool(ok), path or "")

    def show(self) -> None:
        self.app.exec()

    def success_flash(self, text: Optional[str] = None, duration_ms: int = 1200) -> None:
        self.signals.success.emit(text or "", int(duration_ms))

    def flash_hotkey_line(self, hotkey: str, duration_ms: int = 2000) -> None:
        self.signals.flash_line.emit(hotkey, int(duration_ms))

    def set_hotkey_line_active(self, hotkey: str) -> None:
        self.signals.hold_line.emit(hotkey)

    def clear_hotkey_line_active(self, hotkey: str, fade_duration_ms: int = 2000) -> None:
        self.signals.clear_line.emit(hotkey, int(fade_duration_ms))

    # ---- UI slots ----
    def _set_status_ui(self, text: str) -> None:
        self.status.setText(text)

    def _set_visible_ui(self, visible: bool) -> None:
        if visible:
            self.window.show()
        else:
            self.window.hide()

    def _toggle_visible_ui(self) -> None:
        self._set_visible_ui(not self.window.isVisible())

    def _show_page(self, index: int) -> None:
        index = 0 if index <= 0 else 1
        self.stack.setCurrentIndex(index)
        self._set_flags(click_through=(index == 0))
        self.window.show()  # apply flags
        # Bold the active nav button
        if index == 0:
            self.btn_main.setStyleSheet(self.btn_main.styleSheet() + "\nfont-weight: 700;")
            self.btn_calib.setStyleSheet(self.btn_calib.styleSheet())
        else:
            self.btn_calib.setStyleSheet(self.btn_calib.styleSheet() + "\nfont-weight: 700;")
            self.btn_main.setStyleSheet(self.btn_main.styleSheet())

    def _set_captured_inventory_ui(self, token: str) -> None:
        box: QLabel = getattr(self.inv_row, "_gw_display_box")  # type: ignore[attr-defined]
        btn: QPushButton = getattr(self.inv_row, "_gw_button")  # type: ignore[attr-defined]
        box.setText(f"[ {self._friendly_token(token)} ]")
        self._flash_value_label(box)
        self._flash_button_success(btn)
        self._update_start_enabled()

    def _set_captured_tek_ui(self, token: str) -> None:
        box: QLabel = getattr(self.tek_row, "_gw_display_box")  # type: ignore[attr-defined]
        btn: QPushButton = getattr(self.tek_row, "_gw_button")  # type: ignore[attr-defined]
        box.setText(f"[ {self._friendly_token(token)} ]")
        self._flash_value_label(box)
        self._flash_button_success(btn)
        self._update_start_enabled()

    def _set_template_status_ui(self, ok: bool, path: str) -> None:
        box: QLabel = getattr(self.tmpl_row, "_gw_display_box")  # type: ignore[attr-defined]
        btn: QPushButton = getattr(self.tmpl_row, "_gw_button")  # type: ignore[attr-defined]
        if ok:
            box.setText("[ Captured ]")
            box.setToolTip(path)
            self._flash_value_label(box)
            self._flash_button_success(btn)
        else:
            box.setText(self.NONE_DISPLAY)
            box.setToolTip("")
        self._update_start_enabled()

    # ---- Feedback animations ----
    def _success_flash_ui(self, text: str, duration_ms: int) -> None:
        if text:
            self.status.setText(text)
        if self._status_flash_timer:
            try:
                self._status_flash_timer.stop()
            except Exception:
                pass
        self._status_flash_timer = QTimer(self.window)
        base_css = f"color: {self.GRAY}"
        steps = max(8, min(40, duration_ms // 50))
        interval = max(16, duration_ms // steps)
        i = {"v": 0}

        def step():
            i["v"] += 1
            t = i["v"] / steps
            # neon green -> base
            r, g, b = 0, int(255 + (224 - 255) * t), int(170 + (224 - 170) * t)
            self.status.setStyleSheet(f"color: rgb({r},{g},{b})")
            if i["v"] >= steps:
                self._status_flash_timer.stop()
                self.status.setStyleSheet(base_css)

        self.status.setStyleSheet("color: #00ffaa")
        self._status_flash_timer.timeout.connect(step)
        self._status_flash_timer.start(interval)

    def _flash_value_label(self, label: QLabel, duration_ms: int = 1200) -> None:
        # Cancel prior timer for this label
        if label in self._value_flash_timers:
            try:
                self._value_flash_timers[label].stop()
            except Exception:
                pass
        timer = QTimer(self.window)
        self._value_flash_timers[label] = timer
        steps = max(10, min(50, duration_ms // 40))
        interval = max(16, duration_ms // steps)
        i = {"v": 0}

        def style_for(t: float) -> str:
            g = int(255 + (216 - 255) * t)
            b = int(170 + (255 - 170) * t)
            border = f"rgba(0,216,255,{0.75 - 0.45 * t:.2f})"
            return (
                f"border: 1px solid {border}; border-radius: 4px; padding: 3px 8px; "
                f"color: rgb(0,{g},{b});"
            )

        def step():
            i["v"] += 1
            t = i["v"] / steps
            label.setStyleSheet(style_for(t))
            if i["v"] >= steps:
                timer.stop()
                label.setStyleSheet("")
                label.setProperty("class", "keybox")

        label.setStyleSheet(style_for(0.0))
        timer.timeout.connect(step)
        timer.start(interval)

    def _flash_button_success(self, btn: QPushButton, duration_ms: int = 260) -> None:
        try:
            base = btn.styleSheet()
            btn.setStyleSheet(
                """
                QPushButton {
                    color: #0a0a0a;
                    background-color: #00ffaa;
                    border: 1px solid rgba(0,255,170,1.0);
                    border-radius: 6px;
                    font-weight: bold;
                }
                """
            )
            QTimer.singleShot(duration_ms, lambda: btn.setStyleSheet(base))
        except Exception:
            pass

    # ---- Hotkey line highlight (main page) ----
    def _flash_line_ui(self, hotkey: str, duration_ms: int) -> None:
        lab = self._hotkey_labels.get(hotkey)
        if not lab:
            return
        self._highlight_key_label(lab, duration_ms)

    def _hold_line_ui(self, hotkey: str) -> None:
        lab = self._hotkey_labels.get(hotkey)
        if not lab:
            return
        lab.setStyleSheet("border: 1px solid #00ffaa; color: #00ffaa; border-radius: 4px; padding: 3px 8px;")

    def _clear_line_ui(self, hotkey: str, duration_ms: int) -> None:
        # Delegate to _flash_line_ui to avoid duplicate implementation
        self._flash_line_ui(hotkey, duration_ms)

    def _highlight_key_label(self, lab: QLabel, duration_ms: int) -> None:
        steps = max(12, min(60, duration_ms // 40))
        interval = max(16, duration_ms // steps)
        i = {"v": 0}

        def step():
            i["v"] += 1
            t = i["v"] / steps
            g = int(255 + (216 - 255) * t)
            b = int(170 + (255 - 170) * t)
            lab.setStyleSheet(
                f"border: 1px solid rgba(0,216,255,{0.75 - 0.45 * t:.2f}); "
                f"color: rgb(0,{g},{b}); border-radius: 4px; padding: 3px 8px;"
            )
            if i["v"] >= steps:
                lab.setStyleSheet("")
                timer.stop()

        timer = QTimer(self.window)
        timer.timeout.connect(step)
        timer.start(interval)

    # ---- Helpers ----
    def _update_start_enabled(self) -> None:
        inv_box: QLabel = getattr(self.inv_row, "_gw_display_box")  # type: ignore[attr-defined]
        tek_box: QLabel = getattr(self.tek_row, "_gw_display_box")  # type: ignore[attr-defined]
        tmpl_box: QLabel = getattr(self.tmpl_row, "_gw_display_box")  # type: ignore[attr-defined]
        inv_ok = inv_box.text().strip() not in (self.NONE_DISPLAY, "[None]", "")
        tek_ok = tek_box.text().strip() not in (self.NONE_DISPLAY, "[None]", "")
        tmpl_ok = tmpl_box.text().strip().lower().startswith("[ captured")
        self.btn_start.setEnabled(bool(inv_ok and tek_ok and tmpl_ok))

    @staticmethod
    def _friendly_token(token: str) -> str:
        t = (token or "").strip()
        tl = t.lower()
        if tl.startswith("key_"):
            return t[4:]
        if tl.startswith("mouse_"):
            return t[6:]
        return t or "?"
