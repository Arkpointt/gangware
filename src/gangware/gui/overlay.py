import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QMainWindow, QPushButton, QStackedWidget,
    QGraphicsDropShadowEffect, QFrame, QScrollArea, QSizePolicy, QLineEdit
)
from PyQt6.QtGui import QColor, QGuiApplication, QFontDatabase, QFont
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from .design_tokens import STATUS_OK, UI_SCALE

# Global UI scale comes from design tokens


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
    capture_roi = pyqtSignal()
    # Auto Sim signals
    sim_start = pyqtSignal(str)   # emits server code text
    sim_stop = pyqtSignal()
    sim_cal_start = pyqtSignal()  # begin SIM calibration flow (F7-driven)
    sim_cal_cancel = pyqtSignal() # cancel SIM calibration flow
    # Thread-safe UI control signals
    _set_visible_sig = pyqtSignal(bool)
    _set_status_sig = pyqtSignal(str)


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
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        glow(title, self.CYAN, 22, 140)
        root.addWidget(title)

        # Subtitle
        subtitle = QLabel("Made by Deacon")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        # Ensure full text is visible: no wrap and expand horizontally
        try:
            subtitle.setWordWrap(False)
            subtitle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        except Exception:
            pass
        try:
            f = subtitle.font()
            if f.pointSize() > 0:
                f.setPointSize(max(8, f.pointSize() - 2))
            else:
                f = QFont(f.family(), 9)
            subtitle.setFont(f)
        except Exception:
            pass
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

        # Default page
        self._switch_tab(1 if calibration_mode else 0)
        # Connect thread-safe UI control signals
        try:
            self.signals._set_visible_sig.connect(self.set_visible)
            self.signals._set_status_sig.connect(self.set_status)
        except Exception:
            pass

        # Load bundled fonts so QSS can use Orbitron even if not installed
        self._load_project_fonts()
        # Styles
        self._styles()

        # Size and initial position (scaled)
        self.resize(spx(520), spx(520))

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
        try:
            self.btn_sim_tab.setChecked(idx == 2)
        except Exception:
            pass

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
            ("Tek Punch", "Shift+R"),
            ("Medbrew", "Shift+Q"),
            ("Med HoT", "Shift+E"),
        ])

        # Right column: ARMOR
        armor = self._section("ARMOR", [
            ("Search Flak Helmet", "F2"),
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
        # Slightly larger margins/spacing to prevent button/label clipping
        vb.setContentsMargins(spx(10), spx(10), spx(10), spx(10))
        vb.setSpacing(spx(8))

        t1 = QLabel("KEYBIND SETUP")
        t1.setObjectName("sectionTitle")
        glow(t1, self.ORANGE, 18, 120)
        vb.addWidget(t1)

        vb.addWidget(self._cal_row("inventory", "Set Inventory Key", "[ SET ]",
                                   lambda: self.signals.capture_inventory.emit()))
        vb.addWidget(self._cal_row("tek_cancel", "Set Tek Punch Cancel Key", "[ SET ]",
                                   lambda: self.signals.capture_tek.emit()))
        lay.addWidget(kb)

        # VISUAL SETUP section
        vs = QFrame()
        vs.setObjectName("section")
        glow(vs, self.CYAN, 22, 70)
        v2 = QVBoxLayout(vs)
        # Larger bottom margin to prevent clipping at the bottom border
        v2.setContentsMargins(spx(10), spx(10), spx(10), spx(10))
        v2.setSpacing(spx(8))

        t2 = QLabel("VISUAL SETUP")
        t2.setObjectName("sectionTitle")
        glow(t2, self.ORANGE, 18, 120)
        v2.addWidget(t2)

        v2.addWidget(self._cal_row("template", "Capture Search Bar (F8)", "[ CAPTURE ]",
                                   lambda: self.signals.capture_template.emit()))
        v2.addWidget(self._cal_row("roi", "Capture Manual ROI (F6)", "[ CAPTURE ]",
                                   lambda: self.signals.capture_roi.emit()))
        # Bottom spacer to ensure text stays inside the rounded border
        v2.addSpacing(spx(4))
        lay.addWidget(vs)

        # Fit calibration content without a scroll area
        return inner

    def _page_sim(self):
        """SIM page with server code input and Start/Stop controls."""
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
        try:
            self.sim_input.setPlaceholderText("e.g. 2133")
            self.sim_input.setMaxLength(12)
        except Exception:
            pass
        self.sim_input.setObjectName("input")
        h.addWidget(self.sim_input, 1)

        btn_start = QPushButton("Start")
        btn_start.setObjectName("smallBtn")
        btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        glow(btn_start, self.CYAN, 20, 100)
        h.addWidget(btn_start)

        btn_stop = QPushButton("Stop")
        btn_stop.setObjectName("smallBtn")
        btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        glow(btn_stop, self.CYAN, 20, 100)
        h.addWidget(btn_stop)

        v.addWidget(row)

        # Calibration controls
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

        # Wire buttons
        btn_start.clicked.connect(lambda: self._emit_sim_start())
        btn_stop.clicked.connect(lambda: self._emit_sim_stop())
        btn_cal.clicked.connect(lambda: self._emit_sim_cal_start())
        btn_cancel.clicked.connect(lambda: self._emit_sim_cal_cancel())

        return page

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
        h.setContentsMargins(spx(6), spx(4), spx(6), spx(4))
        h.setSpacing(spx(10))
        try:
            row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            row.setMinimumHeight(spx(60))
        except Exception:
            pass
        # Slightly increase vertical margins only for the template row to avoid glyph clipping
        if key == "template":
            try:
                l, t, r, b = spx(6), spx(6), spx(6), spx(6)
                h.setContentsMargins(l, t, r, b)
            except Exception:
                pass

        name_lbl = QLabel(label)
        name_lbl.setObjectName("item")
        try:
            name_lbl.setWordWrap(True)
            name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            # Give multi-line labels a bit more breathing room
            name_lbl.setMinimumHeight(spx(24))
            # Add tiny inner margins to avoid top/bottom glyph clipping on some DPIs
            try:
                name_lbl.setContentsMargins(0, 0, 0, 0)
            except Exception:
                pass
            # Specific fix: avoid vertical clipping for the "Capture Search Bar (F8)" row
            if key == "template":
                try:
                    fm = name_lbl.fontMetrics()
                    mh = max(spx(28), fm.height() + spx(6))
                    name_lbl.setMinimumHeight(mh)
                    name_lbl.setWordWrap(False)
                    name_lbl.setMargin(spx(1))
                    name_lbl.setContentsMargins(0, spx(2), 0, spx(2))
                    name_lbl.setStyleSheet("padding-top: 3px; padding-bottom: 3px;")
                except Exception:
                    pass
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        except Exception:
            pass

        btn = QPushButton(btn_text)
        btn.setObjectName("smallBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(on_click)
        try:
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            btn.setFixedHeight(spx(36))
        except Exception:
            pass
        glow(btn, self.CYAN, 20, 100)

        box = QLabel(self.NONE_DISPLAY)
        box.setObjectName("statusBox")
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.setFixedWidth(spx(140))
        box.setFixedHeight(spx(36))
        box.setProperty("state", "pending")
        box.style().unpolish(box); box.style().polish(box)

        self._cal_boxes[key] = box

        h.addWidget(name_lbl, 1)
        h.addWidget(btn, 0)
        h.addSpacing(spx(12))
        h.addWidget(box, 0)
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

    def _load_project_fonts(self) -> None:
        """
        Register bundled fonts from assets/fonts (or Assets/Fonts) so that the QSS
        can use 'Orbitron' regardless of OS installation.
        """
        try:
            base = Path(__file__).resolve().parents[3]
            candidates = [
                base / "assets" / "fonts",
                base / "Assets" / "Fonts",
            ]
            font_dir = next((p for p in candidates if p.exists()), None)
            if not font_dir:
                return
            # Add all TTF/OTF fonts in that directory
            for p in font_dir.iterdir():
                if p.suffix.lower() in {".ttf", ".otf"}:
                    try:
                        QFontDatabase.addApplicationFont(str(p))
                    except Exception:
                        pass
        except Exception:
            pass

    # ------ StyleSheet ------
    def _styles(self):
        try:
            # In a frozen executable, do not attempt to rebuild theme; load the packaged QSS
            if getattr(sys, 'frozen', False):
                qss_path = Path(__file__).with_name("theme.qss")
                qss = qss_path.read_text(encoding="utf-8")
            else:
                # Build and apply generated QSS from tokens in dev mode
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

    def on_capture_roi(self, slot):
        self.signals.capture_roi.connect(slot)

    # SIM wiring
    def on_sim_start(self, slot):
        self.signals.sim_start.connect(slot)

    def on_sim_stop(self, slot):
        self.signals.sim_stop.connect(slot)

    def on_sim_cal_start(self, slot):
        self.signals.sim_cal_start.connect(slot)

    def on_sim_cal_cancel(self, slot):
        self.signals.sim_cal_cancel.connect(slot)

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
        try:
            box.style().unpolish(box); box.style().polish(box)
        except Exception:
            pass

    # ------ Compatibility API used by HotkeyManager ------
    def set_status(self, text: str) -> None:
        try:
            t = text or ""
            if "calibration complete" in t.lower():
                t = "STATUS: OPERATIONAL"
                try:
                    self.status_label.setProperty("variant", "operational")
                    self.status_label.style().unpolish(self.status_label)
                    self.status_label.style().polish(self.status_label)
                except Exception:
                    pass
            self.status_label.setText(t)
            self.status_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        except Exception:
            pass

    # Thread-safe wrappers for background threads
    def set_status_safe(self, text: str) -> None:
        try:
            self.signals._set_status_sig.emit(str(text))
        except Exception:
            pass

    def prompt_key_capture(self, prompt: str) -> None:
        self.set_status(prompt)

    def set_visible(self, visible: bool) -> None:
        try:
            self.setVisible(bool(visible))
        except Exception:
            pass

    def set_visible_safe(self, visible: bool) -> None:
        try:
            self.signals._set_visible_sig.emit(bool(visible))
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

    def toggle_visibility(self) -> None:
        """Toggle overlay visibility between shown and hidden."""
        try:
            self.setVisible(not self.isVisible())
        except Exception:
            pass

    # ------ SIM helpers ------
    def _emit_sim_start(self):
        try:
            code = self.sim_input.text().strip() if hasattr(self, 'sim_input') else ''
        except Exception:
            code = ''
        # Immediate UI feedback for diagnostics
        try:
            self.set_status(f"SIM: Start clicked with code '{code or '?'}'")
        except Exception:
            pass
        try:
            self.signals.sim_start.emit(code)
        except Exception:
            pass

    def _emit_sim_stop(self):
        try:
            self.set_status("SIM: Stop clicked")
        except Exception:
            pass
        try:
            self.signals.sim_stop.emit()
        except Exception:
            pass

    def _emit_sim_cal_start(self):
        try:
            self.set_status("SIM F7 Capture: Press F7 to log coords; double-press F7 to finish. Cancel to abort.")
        except Exception:
            pass
        try:
            self.signals.sim_cal_start.emit()
        except Exception:
            pass

    def _emit_sim_cal_cancel(self):
        try:
            self.set_status("SIM Calibration: cancelled.")
        except Exception:
            pass
        try:
            self.signals.sim_cal_cancel.emit()
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