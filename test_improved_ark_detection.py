#!/usr/bin/env python3
"""
Test the improved Ark window detection.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import ctypes
from gangware.features.auto_sim import AutoSimRunner
from gangware.controllers.vision import VisionController
from gangware.controllers.controls import InputController
from gangware.core.config import ConfigManager


def test_ark_window_enumeration():
    """Test that we can enumerate and find Ark windows regardless of foreground status"""
    print("Testing Ark window enumeration...")

    config_manager = ConfigManager()
    vision = VisionController()
    input_ctrl = InputController()

    auto_sim = AutoSimRunner(config_manager, vision, input_ctrl, overlay=None)

    # Test the improved _get_ark_window_region method
    ark_region = auto_sim._get_ark_window_region()

    if ark_region:
        print(f"✓ Ark window found via enumeration: {ark_region}")
        left, top = ark_region['left'], ark_region['top']
        width, height = ark_region['width'], ark_region['height']
        right, bottom = left + width, top + height

        print(f"  Window bounds: ({left}, {top}) to ({right}, {bottom})")
        print(f"  Size: {width}x{height}")

        # Test if coordinates are reasonable (not negative, not massive)
        if left >= -5000 and top >= -5000 and width > 0 and height > 0 and width < 10000 and height < 10000:
            print("  ✓ Window bounds look reasonable")
        else:
            print("  ⚠️ Window bounds look suspicious")

        # Test coordinate clamping
        test_coords = [
            (left - 100, top + 100),      # Left of window
            (right + 100, top + 100),     # Right of window
            (left + 100, top - 100),      # Above window
            (left + 100, bottom + 100),   # Below window
            (left + width//2, top + height//2)  # Center (should not change)
        ]

        print(f"  Testing coordinate clamping:")
        for i, coords in enumerate(test_coords):
            clamped = auto_sim._clamp_to_ark_window(coords, ark_region)
            changed = coords != clamped
            print(f"    {i+1}. {coords} -> {clamped} {'(clamped)' if changed else '(unchanged)'}")

        return True
    else:
        print("✗ Ark window not found")
        print("  This is expected if Ark Ascended is not currently running")
        return False


def list_ark_processes():
    """List all ArkAscended.exe processes to verify detection"""
    print("\nListing ArkAscended.exe processes...")

    try:
        if not ctypes or not hasattr(ctypes, 'windll'):
            print("  Windows API not available")
            return

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        found_windows = []

        def enum_windows_proc(hwnd, lParam):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True

                # Get process ID for this window
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

                # Open process to get executable name
                hproc = kernel32.OpenProcess(0x1000, False, pid.value)
                if not hproc:
                    return True

                try:
                    buffer = ctypes.create_unicode_buffer(260)
                    size = ctypes.c_ulong(260)
                    if kernel32.QueryFullProcessImageNameW(hproc, 0, buffer, ctypes.byref(size)):
                        exe_path = buffer.value.lower()
                        if 'ark' in exe_path:  # Look for any Ark-related process
                            # Get window title
                            title_buffer = ctypes.create_unicode_buffer(256)
                            user32.GetWindowTextW(hwnd, title_buffer, 256)
                            title = title_buffer.value

                            # Get window rect
                            class RECT(ctypes.Structure):
                                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                                           ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
                            rect = RECT()
                            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                                found_windows.append({
                                    'exe': exe_path,
                                    'title': title,
                                    'hwnd': hwnd,
                                    'pid': pid.value,
                                    'rect': (rect.left, rect.top, rect.right, rect.bottom)
                                })
                finally:
                    kernel32.CloseHandle(hproc)

            except Exception:
                pass
            return True

        # Define the callback type and enumerate
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        enum_proc = WNDENUMPROC(enum_windows_proc)
        user32.EnumWindows(enum_proc, 0)

        if found_windows:
            print(f"  Found {len(found_windows)} Ark-related window(s):")
            for i, window in enumerate(found_windows, 1):
                print(f"    {i}. {window['exe']}")
                print(f"       Title: '{window['title']}'")
                print(f"       PID: {window['pid']}, HWND: {window['hwnd']}")
                left, top, right, bottom = window['rect']
                print(f"       Rect: ({left}, {top}) to ({right}, {bottom}) [{right-left}x{bottom-top}]")
        else:
            print("  No Ark-related windows found")

    except Exception as e:
        print(f"  Error: {e}")


if __name__ == "__main__":
    print("Improved Ark Window Detection Test")
    print("=" * 40)

    try:
        list_ark_processes()
        found = test_ark_window_enumeration()

        print(f"\nResult: {'✓ SUCCESS' if found else '⚠️ NO ARK WINDOW'}")
        if not found:
            print("This is expected if Ark Ascended is not running.")
            print("To test fully, launch Ark Ascended and run this test again.")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
