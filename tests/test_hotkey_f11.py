import types
import pytest

from gangware.core.hotkey_manager import HotkeyManager


class DummySignal:
    def __init__(self):
        self.emitted = False

    def emit(self):
        self.emitted = True


class DummyOverlay:
    def __init__(self, visible=True):
        # signals object with autosim_start / autosim_stop
        self.signals = types.SimpleNamespace(autosim_start=DummySignal(), autosim_stop=DummySignal())
        self._visible = visible

    def isVisible(self):
        return self._visible

    def trigger_autosim_start(self):
        # mimic overlay trigger method
        self.signals.autosim_start.emit()

    def trigger_autosim_stop(self):
        self.signals.autosim_stop.emit()


@pytest.mark.parametrize("visible,expect_start,expect_stop", [
    (True, True, False),   # overlay visible -> start emitted
    (False, False, True),  # overlay hidden -> stop emitted
])
def test_on_hotkey_f11_emits_correct_signal(visible, expect_start, expect_stop):
    # Create HotkeyManager with minimal dependencies (pass None where allowed)
    hk = HotkeyManager(config_manager=None, overlay=None)

    # Attach dummy overlay
    overlay = DummyOverlay(visible=visible)
    hk.overlay = overlay

    # Call handler
    hk._on_hotkey_f11()

    assert overlay.signals.autosim_start.emitted == expect_start
    assert overlay.signals.autosim_stop.emitted == expect_stop
