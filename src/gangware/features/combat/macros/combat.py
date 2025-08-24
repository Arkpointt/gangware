"""
Combat Macros
Executes combat-related macros (e.g., Tek Punch).
"""

import time
import logging
from typing import Optional, Protocol


class OverlayProtocol(Protocol):
    """Protocol for overlay-like objects that support hotkey line status."""
    def set_hotkey_line_active(self, hotkey: str) -> None: ...
    def clear_hotkey_line_active(self, hotkey: str, fade_duration_ms: int = 400) -> None: ...


# The macro functions can optionally receive an overlay-like object that exposes
# set_hotkey_line_active(hotkey: str) and clear_hotkey_line_active(hotkey: str, fade_duration_ms: int)
# We pass overlay=None by default to avoid tight coupling.

# Module logger
logger = logging.getLogger(__name__)


# Smart cooldown timestamp for Tek Punch (allow immediate retrigger once complete)
_last_tek_punch_ready_at: float = 0.0


def _resolve_cancel_key(config_manager) -> str:
    """Return a pydirectinput-friendly key from config token like 'key_e'.

    Falls back to 'e' if unavailable.
    """
    try:
        token = None
        if config_manager is not None:
            token = config_manager.get("tek_punch_cancel_key")
        if not token:
            return 'e'
        token = str(token).strip()
        if token.startswith('key_'):
            return token[4:].lower()
        # Mouse tokens are not reliably supported by pydirectinput for extra buttons.
        # Fall back to a reasonable default if a mouse token was captured.
        return 'e'
    except Exception:
        return 'e'


def execute_tek_punch(input_controller, config_manager=None):
    """Simplified tek punch macro with reliable timing.

    Sequence:
    - Send Shift+R to activate tek punch
    - Wait pre-delay (120ms default)
    - Hold right-click for configured duration (800ms default)
    - Release right-click
    - Wait settle delay (180ms default)
    - Double-tap cancel key from config

    The macro is gated by the hotkey manager to prevent rapid retriggering.
    Total execution time: ~1130ms with default timing.
    """
    global _last_tek_punch_ready_at
    now = time.perf_counter()
    if now < _last_tek_punch_ready_at:
        # Still within the active window from a previous run; skip
        logger.info("tek_punch: skipped due to active cooldown window")
        return

    cancel_key = _resolve_cancel_key(config_manager)

    logger.info("Tek punch starting - jetpack preserved, sequence will take ~0.9 seconds")
    try:
        # Since we're here via Shift+R hotkey, user is likely holding Shift for jetpack
        # Just send R key instead of Shift+R to avoid disrupting jetpack state
        logger.debug("tek_punch: sending R (preserving user's Shift state)")
        input_controller.press_key('r')
        time.sleep(0.05)

        # Get timing configuration - optimized for speed
        try:
            if config_manager:
                pre_ms = float(config_manager.get("tek_punch_pre_rmb_delay_ms", fallback="80"))
                hold_ms = float(config_manager.get("tek_punch_rmb_hold_ms", fallback="650"))
                post_ms = float(config_manager.get("tek_punch_post_rmb_settle_ms", fallback="120"))
            else:
                pre_ms, hold_ms, post_ms = 80.0, 650.0, 120.0
        except Exception:
            # Fallback to optimized values
            pre_ms, hold_ms, post_ms = 80.0, 650.0, 120.0

        # Optional pre-delay before holding RMB
        if pre_ms > 0:
            time.sleep(pre_ms / 1000.0)

        # Hold right-click for configured duration, reasserting if the game/system
        # drops the button under heavy input spam.
        t0 = time.perf_counter()
        input_controller.mouse_down('right')
        target_s = max(0.0, hold_ms) / 1000.0
        # Poll at ~2ms to reassert if needed without busy-waiting
        reasserts = 0
        while True:
            elapsed = time.perf_counter() - t0
            if elapsed >= target_s:
                break
            try:
                # If RMB is not reported down, reassert it
                if hasattr(input_controller, 'is_mouse_down') and not input_controller.is_mouse_down('right'):
                    logger.debug(
                        "tek_punch: detected RMB not held at %.0fms, reasserting",
                        elapsed * 1000.0,
                    )
                    reasserts += 1
                    input_controller.mouse_down('right')
            except Exception:
                pass
            # short sleep to avoid high CPU and let input settle
            time.sleep(0.002)
        input_controller.mouse_up('right')
        held_for_ms = (time.perf_counter() - t0) * 1000.0
        logger.info(
            "Tek punch executed successfully - RMB held for %.0f ms (target %.0f ms)",
            held_for_ms,
            hold_ms,
        )

        # Post-release settle delay
        if post_ms > 0:
            time.sleep(post_ms / 1000.0)
        # Double-tap cancel key quickly
        input_controller.press_key(cancel_key, presses=2, interval=0.06)
    except Exception as e:
        logger.error(f"Tek punch failed to execute: {e}. Check your tek punch cancel key configuration.")
    finally:
        # Mark ready timestamp at actual completion time
        _last_tek_punch_ready_at = time.perf_counter()
        logger.info("Tek punch completed - ready for next use")


def execute_medbrew_burst(input_controller):
    """
    Executes the Medbrew Burst: spam hotbar slot 0 five times quickly.

    Assumes Medbrews are bound to the '0' hotbar slot in-game.
    """
    logger.info("medbrew_burst: start (0 x5)")
    try:
        # Press '0' five times with ~200ms between presses for reliability.
        input_controller.press_key('0', presses=5, interval=0.20)
    except Exception:
        logger.exception("medbrew_burst: error")
    finally:
        logger.info("medbrew_burst: done")


def execute_medbrew_hot_toggle(input_controller, overlay: Optional[OverlayProtocol] = None):
    """Heal-over-time effect: press '0' every 1.5s for 22.5s.

    Behavior:
    - Immediately marks Shift+E line active (green) in the overlay if available.
    - Presses '0' at 0.0s, 1.5s, ..., up to 22.5s (inclusive: 16 presses).
    - After the loop, requests a slow fade-out of the Shift+E line.
    """
    HOTKEY_LABEL = "Shift+E"
    total_duration = 22.5
    interval = 1.5
    presses = int(total_duration / interval) + 1  # include t=0 and t=22.5 -> 16

    logger.info(
        "medbrew_hot: start interval=%.2fs total=%.2fs presses=%d",
        interval,
        total_duration,
        presses,
    )

    # Mark line active in overlay
    try:
        if overlay and hasattr(overlay, "set_hotkey_line_active"):
            overlay.set_hotkey_line_active(HOTKEY_LABEL)
    except Exception:
        pass

    try:
        start = time.perf_counter()
        for i in range(presses):
            # Schedule each press at start + i*interval
            target = start + i * interval
            now = time.perf_counter()
            delay = target - now
            if delay > 0:
                time.sleep(delay)
            try:
                input_controller.press_key('0', presses=1)
            except Exception:
                logger.exception("medbrew_hot: press error at %d", i)
    except Exception:
        logger.exception("medbrew_hot: error")
    finally:
        logger.info("medbrew_hot: completed")
        try:
            if overlay and hasattr(overlay, "clear_hotkey_line_active"):
                # Slow fade to match the requested behavior
                overlay.clear_hotkey_line_active(HOTKEY_LABEL, fade_duration_ms=2400)
        except Exception:
            pass
