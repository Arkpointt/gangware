import sys
from pathlib import Path
from typing import Optional, List, Tuple

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QMainWindow, QPushButton, QStackedWidget,
    QGraphicsDropShadowEffect, QFrame, QSizePolicy, QLineEdit
)
from PyQt6.QtGui import QColor, QGuiApplication, QFontDatabase, QFont
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject

from .design_tokens import STATUS_OK, UI_SCALE


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
    capture_inventory = pyqtSignal()
    capture_tek = pyqtSignal()
    capture_template = pyqtSignal()
    capture_roi = pyqtSignal()
    # Auto Sim signals
    sim_start = pyqtSignal(str)
    sim_stop = pyqtSignal()
    sim_cal_start = pyqtSignal()
    sim_cal_cancel = pyqtSignal()
    # Thread-safe UI control signals
    _set_visible_sig = pyqtSignal(bool)
    _set_status_sig = pyqtSignal(str)


class OverlayWindow(QMainWindow):
    CYAN = "#00DDFF"
    ORANGE = "#FFB800"
    NONE_DISPLAY = "[ None ]"

    def __init__(self, calibration_mode: bool = False, message: Optional[str] = None):
        super().__init__()
        # State
        self._cal_boxes: dict[str, QLabel] = {}
        self._start_emitted = False
        self._sim_running = False

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
        self.signals._set_status_sig.connect(self.set_status)

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
        self.btn_main_tab = self._nav_button("MAIN", True)
        self.btn_cal_tab = self._nav_button("CALIBRATION", False)
        self.btn_sim_tab = self._nav_button("SIM", False)
        tabs.addWidget(self.btn_main_tab)
        tabs.addWidget(self.btn_cal_tab)
        tabs.addWidget(self.btn_sim_tab)
        tabs.addStretch(1)
        root.addWidget(tabs_row)

        # Pages
        self.stack = QStackedWidget()
        self.page_main = self._page_main()
        self.page_cal = self._page_calibration()
        self.page_sim = self._page_sim()
        self.stack.addWidget(self.page_main)
        self.stack.addWidget(self.page_cal)
        self.stack.addWidget(self.page_sim)
        root.addWidget(self.stack)

        # Footer
        root.addWidget(self._divider())
        self.status_label = QLabel(message or "")
        self.status_label.setObjectName("status")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(self.status_label)

        # Wire tab switching
        self.btn_main_tab.clicked.connect(lambda: self._switch_tab(0))
        self.btn_cal_tab.clicked.connect(lambda: self._switch_tab(1))
        self.btn_sim_tab.clicked.connect(lambda: self._switch_tab(2))
        self._switch_tab(1 if calibration_mode else 0)

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
        self.btn_cal_tab.setChecked(idx == 1)
        self.btn_sim_tab.setChecked(idx == 2)

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
            ("Tek Punch", "Shift+R"),
            ("Medbrew", "Shift+Q"),
            ("Med HoT", "Shift+E"),
        ])
        armor = self._section("ARMOR", [
            ("Search Flak Helmet", "F2"),
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

    def _page_calibration(self) -> QWidget:
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setSpacing(spx(12))
        lay.setContentsMargins(0, 0, 0, 0)

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

        vb.addWidget(self._cal_row("inventory", "Set Inventory Key", "[ SET ]", self.signals.capture_inventory.emit))
        vb.addWidget(self._cal_row("tek_cancel", "Set Tek Punch Cancel Key", "[ SET ]", self.signals.capture_tek.emit))
        lay.addWidget(kb)

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

        v2.addWidget(self._cal_row("template", "Capture Search Bar (F8)", "[ CAPTURE ]", self.signals.capture_template.emit))
        v2.addWidget(self._cal_row("roi", "Capture Manual ROI (F6)", "[ CAPTURE ]", self.signals.capture_roi.emit))
        v2.addSpacing(spx(4))
        lay.addWidget(vs)
        return inner

    def _page_sim(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(spx(14))

        section = QFrame()
        section.setObjectName("section")
        glow(section, self.CYAN, 22, 70)
        v = QVBoxLayout(section)
        v.setContentsMargins(spx(12), spx(10), spx(12), spx(10))
        v.setSpacing(spx(10))

        t = QLabel("AUTO SIM")
        t.setObjectName("sectionTitle")
        glow(t, self.ORANGE, 18, 130)
        v.addWidget(t)

        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(spx(10))
        lbl = QLabel("Server code:")
        lbl.setObjectName("item")
        h.addWidget(lbl)

        self.sim_input = QLineEdit()
        self.sim_input.setPlaceholderText("e.g. 2133")
        self.sim_input.setMaxLength(12)
        self.sim_input.setObjectName("input")
        h.addWidget(self.sim_input, 1)

        btn_start = QPushButton("Start")
        btn_start.setObjectName("smallBtn")
        btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        glow(btn_start, self.CYAN, 20, 100)
        h.addWidget(btn_start)
        # Keep a handle and disable until input present
        self.btn_sim_start = btn_start
        self.btn_sim_start.setEnabled(False)

        btn_stop = QPushButton("Stop")
        btn_stop.setObjectName("smallBtn")
        btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        glow(btn_stop, self.CYAN, 20, 100)
        h.addWidget(btn_stop)
        v.addWidget(row)

        hint_row = QWidget()
        hint_layout = QHBoxLayout(hint_row)
        hint_layout.setContentsMargins(0, 0, 0, 0)
        hint_layout.setSpacing(spx(8))
        hint_label = QLabel("Hotkey: Press F11 to Start/Stop the Sim")
        hint_label.setObjectName("item")
        hint_layout.addWidget(hint_label)
        hint_layout.addStretch(1)
        v.addWidget(hint_row)

        row2 = QWidget()
        h2 = QHBoxLayout(row2)
        h2.setContentsMargins(0, 0, 0, 0)
        h2.setSpacing(spx(10))
        lbl2 = QLabel("SIM Calibration:")
        lbl2.setObjectName("item")
        h2.addWidget(lbl2)
        btn_cal = QPushButton("Start (use F7)")
        btn_cal.setObjectName("smallBtn")
        btn_cal.setCursor(Qt.CursorShape.PointingHandCursor)
        glow(btn_cal, self.CYAN, 20, 100)
        h2.addWidget(btn_cal)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("smallBtn")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        glow(btn_cancel, self.CYAN, 20, 100)
        h2.addWidget(btn_cancel)
        h2.addStretch(1)
        v.addWidget(row2)

        outer.addWidget(section)

        # Wire events
        btn_start.clicked.connect(self._emit_sim_start)
        btn_stop.clicked.connect(self._emit_sim_stop)
        btn_cal.clicked.connect(self._emit_sim_cal_start)
        btn_cancel.clicked.connect(self._emit_sim_cal_cancel)
        # Enable Start only when input present
        self.sim_input.textChanged.connect(self._update_sim_controls)
        self._update_sim_controls()
        return page

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
        box.style().unpolish(box)
        box.style().polish(box)
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
        except Exception as e:
            print(f"Failed to apply themed stylesheet: {e}")

    # ------ Public API (signals wiring expected by main/hotkey manager) ------
    def on_recalibrate(self, slot): self.signals.recalibrate.connect(slot)
    def on_start(self, slot): self.signals.start.connect(slot)
    def on_capture_inventory(self, slot): self.signals.capture_inventory.connect(slot)
    def on_capture_tek(self, slot): self.signals.capture_tek.connect(slot)
    def on_capture_template(self, slot): self.signals.capture_template.connect(slot)
    def on_capture_roi(self, slot): self.signals.capture_roi.connect(slot)
    def on_sim_start(self, slot): self.signals.sim_start.connect(slot)
    def on_sim_stop(self, slot): self.signals.sim_stop.connect(slot)
    def on_sim_cal_start(self, slot): self.signals.sim_cal_start.connect(slot)
    def on_sim_cal_cancel(self, slot): self.signals.sim_cal_cancel.connect(slot)

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
        box.style().unpolish(box)
        box.style().polish(box)
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
            self.status_label.style().unpolish(self.status_label)
            self.status_label.style().polish(self.status_label)
        self.status_label.setText(t)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)

    def set_status_safe(self, text: str) -> None:
        self.signals._set_status_sig.emit(str(text))

    def prompt_key_capture(self, prompt: str) -> None:
        self.set_status(prompt)

    def set_visible(self, visible: bool) -> None:
        self.setVisible(bool(visible))

    def set_visible_safe(self, visible: bool) -> None:
        self.signals._set_visible_sig.emit(bool(visible))

    def switch_to_calibration(self) -> None:
        self._start_emitted = False
        self._switch_tab(1)
        self._update_start_enabled()

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

        QTimer.singleShot(int(max(0, duration_ms)), _restore)

    def toggle_visibility(self) -> None:
        self.setVisible(not self.isVisible())

    # ------ SIM helpers ------
    def _get_server_code(self) -> str:
        return self.sim_input.text().strip() if hasattr(self, 'sim_input') and self.sim_input is not None else ''

    def _emit_sim_start(self):
        code = self._get_server_code()
        if not code:
            # Guard: do not start without a server code
            self.set_status("Enter a server number to start SIM.")
            # keep overlay visible for user to enter code
            self.set_visible(True)
            return
        self.set_status(f"SIM: Start clicked with code '{code}'")
        self.signals.sim_start.emit(code)
        self._sim_running = True

    def _emit_sim_stop(self):
        self.set_status("SIM: Stop clicked")
        self.signals.sim_stop.emit()
        self._sim_running = False

    def request_sim_start_hotkey(self) -> None:
        def _ui():
            code = self._get_server_code()
            if not code:
                # Bring user to SIM tab and prompt for input
                self._switch_tab(2)
                self.set_visible(True)
                self.set_status("Enter server number on SIM tab, then press F11.")
                try:
                    self.sim_input.setFocus()
                except Exception:
                    pass
                return
            # Hide overlay and start
            self.set_visible(False)
            self._emit_sim_start()
        QTimer.singleShot(0, _ui)

    def request_sim_stop_hotkey(self) -> None:
        QTimer.singleShot(0, self._emit_sim_stop)
        self.set_visible_safe(True)

    def is_sim_running(self) -> bool:
        return bool(self._sim_running)

    def _emit_sim_cal_start(self):
        self.set_status("SIM F7 Capture: Press F7 to log coords; press F9 to finish. Cancel to abort.")
        self.signals.sim_cal_start.emit()

    def _emit_sim_cal_cancel(self):
        self.set_status("SIM Calibration: cancelled.")
        self.signals.sim_cal_cancel.emit()

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
        tmpl_ok = self._cal_boxes.get("template") and str(self._cal_boxes["template"].text()).lower().startswith("[ captured")
        ready = bool(inv_ok and tek_ok and tmpl_ok)
        if ready and not self._start_emitted:
            self._start_emitted = True
            self.signals.start.emit()

    def _update_sim_controls(self):
        try:
            has_code = bool(self._get_server_code())
            if hasattr(self, 'btn_sim_start') and self.btn_sim_start is not None:
                self.btn_sim_start.setEnabled(has_code)
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