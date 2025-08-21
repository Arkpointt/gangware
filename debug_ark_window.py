#!/usr/bin/env python3
"""
Debug Ark window detection in detail
"""

import sys
from pathlib import Path
import ctypes
from ctypes import wintypes

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def debug_ark_window_detection():
    """Comprehensive debugging of Ark window detection"""
    print("Detailed Ark Window Detection Debug")
    print("=" * 50)

    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # Find all Ark windows
        found_windows = []

        def enum_windows_proc(hwnd, lParam):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True

                # Get process ID
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

                # Get executable name
                hproc = kernel32.OpenProcess(0x1000, False, pid.value)
                if not hproc:
                    return True

                try:
                    buffer = ctypes.create_unicode_buffer(260)
                    size = ctypes.c_ulong(260)
                    if kernel32.QueryFullProcessImageNameW(hproc, 0, buffer, ctypes.byref(size)):
                        exe_path = buffer.value.lower()
                        if 'arkascended.exe' in exe_path:
                            # Get window title
                            title_buffer = ctypes.create_unicode_buffer(512)
                            user32.GetWindowTextW(hwnd, title_buffer, 512)
                            title = title_buffer.value

                            found_windows.append({
                                'hwnd': hwnd,
                                'pid': pid.value,
                                'exe': exe_path,
                                'title': title
                            })
                finally:
                    kernel32.CloseHandle(hproc)

            except Exception as e:
                print(f"  Error in enum: {e}")
            return True

        # Enumerate windows
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        enum_proc = WNDENUMPROC(enum_windows_proc)
        user32.EnumWindows(enum_proc, 0)

        if not found_windows:
            print("❌ No Ark windows found!")
            return

        print(f"Found {len(found_windows)} Ark window(s):")

        for i, window in enumerate(found_windows, 1):
            hwnd = window['hwnd']
            print(f"\n🔍 Window {i}: HWND={hwnd}")
            print(f"   Title: '{window['title']}'")
            print(f"   PID: {window['pid']}")
            print(f"   Exe: {window['exe']}")

            # Test different rectangle functions
            class RECT(ctypes.Structure):
                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                           ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

            # GetWindowRect (outer window bounds)
            window_rect = RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(window_rect)):
                w_w = window_rect.right - window_rect.left
                w_h = window_rect.bottom - window_rect.top
                print(f"   📐 GetWindowRect: ({window_rect.left}, {window_rect.top}) to ({window_rect.right}, {window_rect.bottom}) [{w_w}x{w_h}]")
            else:
                print(f"   ❌ GetWindowRect failed")

            # GetClientRect (inner client area)
            client_rect = RECT()
            if user32.GetClientRect(hwnd, ctypes.byref(client_rect)):
                c_w = client_rect.right - client_rect.left
                c_h = client_rect.bottom - client_rect.top
                print(f"   📐 GetClientRect: ({client_rect.left}, {client_rect.top}) to ({client_rect.right}, {client_rect.bottom}) [{c_w}x{c_h}]")
            else:
                print(f"   ❌ GetClientRect failed")

            # Check if maximized
            placement = wintypes.WINDOWPLACEMENT()
            placement.length = ctypes.sizeof(wintypes.WINDOWPLACEMENT)
            if user32.GetWindowPlacement(hwnd, ctypes.byref(placement)):
                state_names = {
                    1: "NORMAL",
                    2: "MINIMIZED",
                    3: "MAXIMIZED"
                }
                state = state_names.get(placement.showCmd, f"UNKNOWN({placement.showCmd})")
                print(f"   🪟 Window State: {state}")

            # Check foreground
            fg_hwnd = user32.GetForegroundWindow()
            is_foreground = (hwnd == fg_hwnd)
            print(f"   🎯 Is Foreground: {is_foreground}")

            # DPI awareness
            try:
                dpi = user32.GetDpiForWindow(hwnd)
                print(f"   🔍 DPI: {dpi} (scale: {dpi/96:.2f}x)")
            except:
                print(f"   🔍 DPI: Unable to detect")

            # Monitor info
            try:
                monitor = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
                if monitor:
                    print(f"   🖥️ Monitor Handle: {monitor}")
            except:
                pass

        # Test what our current detection returns
        print(f"\n🧪 Testing our _get_ark_window_region()...")
        try:
            from gangware.features.auto_sim import AutoSimRunner
            from gangware.controllers.vision import VisionController
            from gangware.controllers.controls import InputController
            from gangware.core.config import ConfigManager

            config_manager = ConfigManager()
            vision = VisionController()
            input_ctrl = InputController()
            auto_sim = AutoSimRunner(config_manager, vision, input_ctrl, overlay=None)

            result = auto_sim._get_ark_window_region()
            if result:
                print(f"   ✅ Our detection: {result}")
                width, height = result['width'], result['height']
                if width == 1920 and height == 1080:
                    print(f"   ⚠️ Detected 1080p but you said it's 4K - likely DPI scaling issue!")
                elif width == 3840 and height == 2160:
                    print(f"   ✅ Correctly detected 4K resolution")
                else:
                    print(f"   ❓ Unexpected resolution: {width}x{height}")
            else:
                print(f"   ❌ Our detection failed")

        except Exception as e:
            print(f"   ❌ Error testing our detection: {e}")

    except Exception as e:
        print(f"❌ Debug failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_ark_window_detection()
