"""Control System Module
Handles all input automation tasks.
"""

import sys
import time
import logging
import pydirectinput
import os

try:  # Windows-specific for XBUTTON support
    import ctypes  # type: ignore
    _user32 = ctypes.windll.user32 if sys.platform == "win32" else None
except Exception:  # pragma: no cover - platform dependent
    _user32 = None


class InputController:
    """Main class for mouse, keyboard, and input automation."""

    def __init__(self):
        # Configure pydirectinput for immediate actions and no edge failsafe
        try:
            import pydirectinput as _pdi
            _pdi.FAILSAFE = False
            _pdi.PAUSE = 0.0
        except Exception:
            pass
        # Movement behavior (tunable via env)
        try:
            # Default to a short smooth move; override via GW_MOUSE_MOVE_DURATION
            self._move_duration = float(os.getenv("GW_MOUSE_MOVE_DURATION", "0.08") or 0.08)  # seconds
        except Exception:
            self._move_duration = 0.08
        try:
            # Default to skipping verify to avoid micro-corrections during visual automation
            self._skip_verify = str(os.getenv("GW_MOUSE_SKIP_VERIFY", "1")).lower() in ("1", "true", "yes")
        except Exception:
            self._skip_verify = True
        try:
            self._verify_tol = int(os.getenv("GW_MOUSE_VERIFY_TOL", "2") or 2)
        except Exception:
            self._verify_tol = 2

    # ---- internal helpers to keep cognitive complexity low ----
    @staticmethod
    def _sleep(seconds: float) -> None:
        try:
            import time as _t
            if seconds > 0:
                _t.sleep(seconds)
        except Exception:
            pass

    @staticmethod
    def _near(a: int, b: int, tol: int = 2) -> bool:
        try:
            return abs(int(a) - int(b)) <= int(tol)
        except Exception:
            return False

    @staticmethod
    def _get_mouse_pos() -> tuple[int | None, int | None]:
        try:
            pos = pydirectinput.position()
            return int(pos[0]), int(pos[1])
        except Exception:
            return None, None

    @staticmethod
    def _set_cursor_win32(x: int, y: int) -> bool:
        if _user32 is None:
            return False
        try:
            _user32.SetCursorPos(int(x), int(y))
            return True
        except Exception:
            return False

    def _ensure_position(self, x: int, y: int, tol: int = 2) -> bool:
        """Verify cursor is near (x,y); if not, try Win32 SetCursorPos once and re-check."""
        logger = logging.getLogger(__name__)
        cx, cy = self._get_mouse_pos()
        if cx is not None and cy is not None and self._near(cx, x, tol) and self._near(cy, y, tol):
            logger.debug("mouse: moved to (%d,%d)", x, y)
            return True
        if self._set_cursor_win32(x, y):
            self._sleep(0.01)
            cx, cy = self._get_mouse_pos()
            logger.info("mouse: fallback SetCursorPos to (%d,%d); now at (%s,%s)", x, y, str(cx), str(cy))
            return cx is not None and cy is not None and self._near(cx, x, tol) and self._near(cy, y, tol)
        logger.warning("mouse: moveTo did not reach target (%d,%d); current=%s", x, y, str((cx, cy)))
        return False

    def move_mouse(self, x, y):
        """
        Moves mouse to (x, y) with verification and minimal branching.
        """
        logger = logging.getLogger(__name__)
        try:
            xi, yi = int(x), int(y)
        except Exception:
            xi, yi = x, y

        # Debug: Log mouse movement attempt
        current_x, current_y = self._get_mouse_pos()
        logger.info("mouse: attempting move from (%s,%s) to (%d,%d)", current_x, current_y, xi, yi)
        try:
            logger.debug(
                "mouse: move cfg duration=%.3f verify=%s tol=%d",
                float(self._move_duration or 0.0),
                str(self._skip_verify is False),
                int(self._verify_tol or 0),
            )
        except Exception:
            pass

        try:
            if self._move_duration and float(self._move_duration) > 0.0:
                pydirectinput.moveTo(xi, yi, duration=float(self._move_duration))
            else:
                pydirectinput.moveTo(xi, yi)
            logger.info("mouse: pydirectinput.moveTo completed")
        except Exception as e:
            logger.exception("mouse: moveTo failed: %s", e)
            # Best-effort fallback
            logger.info("mouse: trying SetCursorPos fallback")
            self._set_cursor_win32(xi, yi)
            return
        self._sleep(0.002)  # Reduced from 20ms to 2ms for speed

        # Debug: Check final position
        final_x, final_y = self._get_mouse_pos()
        logger.info("mouse: final position (%s,%s)", final_x, final_y)
        if not getattr(self, "_skip_verify", False):
            self._ensure_position(xi, yi, tol=int(getattr(self, "_verify_tol", 2)))
        else:
            logger.debug("mouse: skipped verify step")

    def click(self):
        """
        Performs a left mouse click with robust fallback.
        """
        # Reuse the robust click_button path for consistency
        try:
            self.click_button('left', presses=1, interval=0.0)
        except Exception:
            try:
                pydirectinput.click(button='left')
            except Exception:
                pass

    def click_button(self, button: str, presses: int = 1, interval: float = 0.05):
        """Click a specific mouse button one or more times with low branching.

        Args:
            button: 'left', 'right', 'middle', or extended ('xbutton1'/'xbutton2').
            presses: Number of clicks.
            interval: Delay between clicks.
        """
        logger = logging.getLogger(__name__)
        btn = (button or "").lower()

        # Debug: Log click attempt
        current_x, current_y = self._get_mouse_pos()
        logger.info(
            "mouse: attempting click %s button %d times at position (%s,%s)",
            btn,
            presses,
            current_x,
            current_y,
        )

        def _loop(n: int, fn):
            for _ in range(max(1, int(n))):
                try:
                    fn()
                except Exception:
                    # continue to next attempt
                    pass
                if interval and interval > 0:
                    self._sleep(interval)

        def _click_win32_xbutton() -> bool:
            if sys.platform != "win32" or _user32 is None or btn not in ("xbutton1", "xbutton2"):
                return False
            MOUSEEVENTF_XDOWN = 0x0080
            MOUSEEVENTF_XUP = 0x0100
            XBUTTON1 = 0x0001
            XBUTTON2 = 0x0002
            data = XBUTTON1 if btn == "xbutton1" else XBUTTON2
            try:
                u32 = _user32
                if u32 is None:
                    return False
                _loop(presses, lambda: (u32.mouse_event(MOUSEEVENTF_XDOWN, 0, 0, data, 0),
                                        u32.mouse_event(MOUSEEVENTF_XUP, 0, 0, data, 0)))
                return True
            except Exception:
                return False

        def _click_win32_standard() -> bool:
            if sys.platform != "win32" or _user32 is None or btn not in ("left", "right", "middle"):
                return False
            flags_map = {
                "left": (0x0002, 0x0004),    # MOUSEEVENTF_LEFTDOWN/UP
                "right": (0x0008, 0x0010),   # MOUSEEVENTF_RIGHTDOWN/UP
                "middle": (0x0020, 0x0040),  # MOUSEEVENTF_MIDDLEDOWN/UP
            }
            down_flag, up_flag = flags_map.get(btn, (None, None))
            if down_flag is None:
                return False
            try:
                u32 = _user32
                if u32 is None:
                    return False
                _loop(presses, lambda: (u32.mouse_event(down_flag, 0, 0, 0, 0),
                                        u32.mouse_event(up_flag, 0, 0, 0, 0)))
                return True
            except Exception:
                return False

        def _click_pdi_specific() -> bool:
            try:
                pydirectinput.click(button=btn or 'left', clicks=presses, interval=interval)
                return True
            except Exception:
                return False

        def _fallback_left() -> None:
            _loop(presses, lambda: pydirectinput.click(button='left'))

        # Try in order: extended buttons via Win32, standard L/R/M via Win32, PDI-specific, then fallback left
        if _click_win32_xbutton():
            px, py = self._get_mouse_pos()
            logger.info("mouse: click completed via Win32 xbutton")
            logger.info("mouse: click position (%s,%s)", px, py)
            return
        if _click_win32_standard():
            px, py = self._get_mouse_pos()
            logger.info("mouse: click completed via Win32 standard")
            logger.info("mouse: click position (%s,%s)", px, py)
            return
        if _click_pdi_specific():
            px, py = self._get_mouse_pos()
            logger.info("mouse: click completed via pydirectinput")
            logger.info("mouse: click position (%s,%s)", px, py)
            return
        # Last resort: attempt left-click via PDI (and native left if PDI fails inside loop)
        try:
            _fallback_left()
            px, py = self._get_mouse_pos()
            logger.info("mouse: click completed via fallback left")
            logger.info("mouse: click position (%s,%s)", px, py)
        except Exception:
            if sys.platform == "win32" and _user32 is not None:
                try:
                    u32 = _user32
                    if u32 is None:
                        return
                    _loop(presses, lambda: (u32.mouse_event(0x0002, 0, 0, 0, 0), u32.mouse_event(0x0004, 0, 0, 0, 0)))
                    px, py = self._get_mouse_pos()
                    logger.info("mouse: click completed via Win32 fallback")
                    logger.info("mouse: click position (%s,%s)", px, py)
                except Exception:
                    logger.warning("mouse: all click methods failed")
                    pass

    def mouse_down(self, button: str = 'left'):
        """Press and hold a mouse button (left/right/middle)."""
        logger = logging.getLogger(__name__)
        btn = str(button or 'left').lower()
        # Button-state snapshot (Windows only)
        before = self._snapshot_mouse_buttons()
        t0 = time.perf_counter()
        logger.info("mouse: down request button=%s state_before=%s", btn, before)
        try:
            pydirectinput.mouseDown(button=btn)
        except Exception as e:
            logger.exception("mouse: mouseDown failed via pydirectinput: %s", e)
            # Best-effort Win32 fallback on Windows
            if sys.platform == "win32" and _user32 is not None:
                try:
                    flags = 0x0002 if btn == 'left' else (0x0008 if btn == 'right' else 0x0020)
                    _user32.mouse_event(flags, 0, 0, 0, 0)
                    logger.info("mouse: mouse_event DOWN fallback used for %s", btn)
                except Exception:
                    logger.warning("mouse: mouse_event DOWN fallback failed for %s", btn)
        # Small settle then sample state
        self._sleep(0.003)
        after = self._snapshot_mouse_buttons()
        dt_ms = (time.perf_counter() - t0) * 1000.0
        logger.info("mouse: down applied button=%s dt=%.1fms state_after=%s", btn, dt_ms, after)

    def mouse_up(self, button: str = 'left'):
        """Release a previously held mouse button (left/right/middle)."""
        logger = logging.getLogger(__name__)
        btn = str(button or 'left').lower()
        before = self._snapshot_mouse_buttons()
        t0 = time.perf_counter()
        logger.info("mouse: up request button=%s state_before=%s", btn, before)
        try:
            pydirectinput.mouseUp(button=btn)
        except Exception as e:
            logger.exception("mouse: mouseUp failed via pydirectinput: %s", e)
            if sys.platform == "win32" and _user32 is not None:
                try:
                    flags = 0x0004 if btn == 'left' else (0x0010 if btn == 'right' else 0x0040)
                    _user32.mouse_event(flags, 0, 0, 0, 0)
                    logger.info("mouse: mouse_event UP fallback used for %s", btn)
                except Exception:
                    logger.warning("mouse: mouse_event UP fallback failed for %s", btn)
        self._sleep(0.003)
        after = self._snapshot_mouse_buttons()
        dt_ms = (time.perf_counter() - t0) * 1000.0
        logger.info("mouse: up applied button=%s dt=%.1fms state_after=%s", btn, dt_ms, after)

    def _snapshot_mouse_buttons(self) -> dict:
        """Best-effort snapshot of mouse buttons pressed. Windows only; else returns {}.

        Returns a dict like {"L": True/False, "R": True/False, "M": True/False}.
        """
        if sys.platform != "win32" or _user32 is None:
            return {}
        try:
            # GetAsyncKeyState high-bit indicates key is down
            def down(vk: int) -> bool:
                try:
                        u32 = _user32
                        if u32 is None:
                            return False
                        return bool(u32.GetAsyncKeyState(vk) & 0x8000)
                except Exception:
                    return False
            return {
                "L": down(0x01),  # VK_LBUTTON
                "R": down(0x02),  # VK_RBUTTON
                "M": down(0x04),  # VK_MBUTTON
            }
        except Exception:
            return {}

    def is_mouse_down(self, button: str) -> bool:
        """Return True if the specified mouse button is currently down.

        Supported buttons: 'left', 'right', 'middle'. On non-Windows platforms or
        when state can't be queried, returns False.
        """
        m = self._snapshot_mouse_buttons()
        b = str(button or '').lower()
        if not m:
            return False
        if b == 'left':
            return bool(m.get('L'))
        if b == 'right':
            return bool(m.get('R'))
        if b == 'middle':
            return bool(m.get('M'))
        return False

    def type_text(self, text: str, interval: float = 0.02, pre_delay: float = 0.03):
        """
        Types the given text with an optional per-character interval and a small
        stabilization delay before typing to avoid dropped leading keystrokes.
        """
        try:
            if pre_delay and pre_delay > 0:
                import time as _t
                _t.sleep(pre_delay)
        except Exception:
            pass
        try:
            pydirectinput.write(text, interval=max(0.0, float(interval)))
        except Exception:
            # Fallback: type character by character
            try:
                for ch in str(text):
                    pydirectinput.write(ch)
                    if interval and interval > 0:
                        import time as _t
                        _t.sleep(interval)
            except Exception:
                pass

    def type_text_precise(self, text: str, interval: float = 0.02, pre_delay: float = 0.05):
        """
        Type text character-by-character with explicit Shift handling for uppercase letters.
        Adds a small stabilization delay before typing and a per-character delay to avoid
        the first characters being dropped by some games.
        """
        try:
            if pre_delay and pre_delay > 0:
                import time as _t
                _t.sleep(pre_delay)
        except Exception:
            pass
        try:
            for ch in str(text):
                try:
                    if ch == ' ':
                        pydirectinput.press('space')
                    elif ch.isalpha():
                        name = ch.lower()
                        if ch.isupper():
                            try:
                                pydirectinput.keyDown('shift')
                                pydirectinput.press(name)
                            finally:
                                pydirectinput.keyUp('shift')
                        else:
                            pydirectinput.press(name)
                    else:
                        # Fallback: write raw character
                        pydirectinput.write(ch)
                except Exception:
                    try:
                        pydirectinput.write(ch)
                    except Exception:
                        pass
                if interval and interval > 0:
                    try:
                        import time as _t
                        _t.sleep(interval)
                    except Exception:
                        pass
        except Exception:
            pass

    def paste_text(self, text: str, pre_delay: float = 0.02, settle: float = 0.01):
        """
        Paste text into the focused field by setting the clipboard and sending Ctrl+V.
        Uses the native Win32 clipboard on Windows (thread-safe, COM-independent).
        Falls back to pyperclip or precise typing if necessary.
        """
        ok = False

        # Prefer native Win32 clipboard on Windows to avoid COM threading issues
        if sys.platform == "win32" and _user32 is not None:
            try:
                import ctypes
                GMEM_MOVEABLE = 0x0002
                CF_UNICODETEXT = 13
                data = (str(text) or "") + "\0"
                raw = data.encode("utf-16-le")
                # Retry a few times in case the clipboard is busy
                for _ in range(5):
                    if _user32.OpenClipboard(None):
                        try:
                            _user32.EmptyClipboard()
                            hglb = ctypes.windll.kernel32.GlobalAlloc(GMEM_MOVEABLE, len(raw))
                            if hglb:
                                lp = ctypes.windll.kernel32.GlobalLock(hglb)
                                if lp:
                                    ctypes.memmove(lp, raw, len(raw))
                                    ctypes.windll.kernel32.GlobalUnlock(hglb)
                                    if _user32.SetClipboardData(CF_UNICODETEXT, hglb):
                                        ok = True
                                        hglb = None  # ownership passed to the system
                        finally:
                            _user32.CloseClipboard()
                        if ok:
                            break
                    # brief wait and retry
                    self._sleep(0.01)
            except Exception:
                ok = False

        # Fallback to pyperclip if available
        if not ok:
            try:
                import pyperclip  # type: ignore
                pyperclip.copy(str(text))
                ok = True
            except Exception:
                ok = False

        # Small pre-delay to stabilize focus
        self._sleep(pre_delay)
        try:
            # Inject text as rapid key events (AHK-like SendInput behavior), no Ctrl+V required
            self.type_text_guarded_fast(
                str(text),
                pre_delay=0.0,
                first_delay=0.035,
                post_space_delay=0.02,
                burst_interval=0.0,
            )
            self._sleep(settle)
            return
        except Exception:
            pass

        # If anything failed, fallback to precise typing (still fast)
        try:
            self.type_text_precise(text, interval=0.01, pre_delay=max(0.02, pre_delay))
        except Exception:
            pass

    def type_text_guarded_fast(
        self,
        text: str,
        pre_delay: float = 0.03,
        first_delay: float = 0.035,
        post_space_delay: float = 0.02,
        burst_interval: float = 0.0,
    ):
        """
        Fast text injection tuned for games:
        - small pre-delay before first char
        - ensure the first char and the first char after a space get a short delay
        - otherwise send keys in a tight burst
        """
        try:
            self._sleep(pre_delay)
            prev_space = True  # treat start like after a space
            for i, ch in enumerate(str(text)):
                try:
                    if ch == ' ':
                        pydirectinput.press('space')
                        self._sleep(post_space_delay)
                        prev_space = True
                        continue
                    if ch.isalpha():
                        name = ch.lower()
                        if ch.isupper():
                            try:
                                pydirectinput.keyDown('shift')
                                pydirectinput.press(name)
                            finally:
                                pydirectinput.keyUp('shift')
                        else:
                            pydirectinput.press(name)
                    elif ch.isdigit():
                        pydirectinput.press(ch)
                    else:
                        # Fallback to write for punctuation/others
                        pydirectinput.write(ch)
                except Exception:
                    try:
                        pydirectinput.write(ch)
                    except Exception:
                        pass
                # Guarded delays
                if i == 0:
                    self._sleep(first_delay)
                elif prev_space:
                    self._sleep(post_space_delay)
                elif burst_interval and burst_interval > 0:
                    self._sleep(burst_interval)
                prev_space = (ch == ' ')
        except Exception:
            pass

    def press_key(self, key: str, presses: int = 1, interval: float = 0.05):
        """Press a key one or more times with an optional interval between presses.

        Args:
            key: The key to press (e.g., '0', 'e', 'f1').
            presses: Number of times to press the key.
            interval: Delay in seconds between presses.
        """
        # pydirectinput mirrors PyAutoGUI's API and supports press with repeats.
        pydirectinput.press(key, presses=presses, interval=interval)

    def hotkey(self, *keys: str):
        """Press a chorded hotkey like Ctrl+A reliably.

        Holds all modifiers down, taps the last key, then releases modifiers in reverse order.
        Example: hotkey('ctrl', 'a')
        """
        seq = [str(k).lower() for k in keys if k]
        if not seq:
            return
        try:
            # Hold modifiers (all but last)
            for k in seq[:-1]:
                try:
                    pydirectinput.keyDown(k)
                except Exception:
                    # ignore and continue best-effort
                    pass
                self._sleep(0.012)
            # Tap the last key while modifiers are down
            try:
                pydirectinput.press(seq[-1])
            except Exception:
                # last-ditch fallback
                try:
                    pydirectinput.keyDown(seq[-1])
                    self._sleep(0.01)
                    pydirectinput.keyUp(seq[-1])
                except Exception:
                    pass
            self._sleep(0.015)
        except Exception:
            # Swallow and proceed to releasing modifiers; best-effort only
            pass
        finally:
            # Release modifiers in reverse order
            for k in reversed(seq[:-1]):
                try:
                    pydirectinput.keyUp(k)
                except Exception:
                    pass
                self._sleep(0.006)

    # Convenience to press config tokens (e.g., 'key_i', 'mouse_xbutton2')
    def press_token(self, token: str):
        t = (token or "").strip().lower()
        if not t:
            return
        if t.startswith("mouse_"):
            self.click_button(t.split("_", 1)[1])
        elif t.startswith("key_"):
            self.press_key(t.split("_", 1)[1])
        else:
            # try as a raw key name
            self.press_key(t)
