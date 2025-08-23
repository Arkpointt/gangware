# Gangware
## Advanced Computer Vision Automation for ARK: Survival Ascended

**Version 6.2** - Modular, Testable, Session-Logged Automation

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![OpenCV](https://img.shields.io/badge/OpenCV-Computer%20Vision-green.svg)](https://opencv.org)
[![PyQt6](https://img.shields.io/badge/PyQt6-GUI%20Framework-orange.svg)](https://www.riverbankcomputing.com/software/pyqt/)

Gangware is a high-performance automation system designed specifically for ARK: Survival Ascended, featuring sub-second armor swapping, intelligent computer vision, and advanced macro capabilities. Built with professional-grade optimization techniques, Gangware delivers lightning-fast equipment management and combat automation.

---

## 🚀 Key Features

### ⚡ **Sub-Second Armor Swapping**
- **Performance**: Complete armor swaps in under 1 second
- **F6 Manual ROI**: Capture custom inventory regions for instant targeting
- **Smart Bypass**: Eliminates 2+ second calibration delays when F6 ROI available
- **Multi-Monitor Support**: Intelligent coordinate handling across monitor setups

### 🎯 **Advanced Computer Vision**
- **Hybrid Template Matching**: Edge detection + HSV hue validation for tier confirmation
- **Template Cropping**: Focus on item icons vs inventory slot backgrounds
- **Fast/Slow Pass Optimization**: Early exit on good matches for maximum speed
- **Multi-Scale Robustness**: Handles UI scaling variations automatically

### 🔧 **Professional Automation**
- **Tek Dash Combos**: Frame-perfect movement sequences
- **Medbrew Management**: Intelligent healing over time with threading
- **Hotkey System**: Global Windows hotkeys with fallback polling
- **Real-Time Feedback**: ARK-inspired HUD with status indicators

### 🎮 **Gaming-Focused Design**
- **Zero Game Modification**: External automation, no game files touched
- **Performance Optimized**: 2ms mouse delays, smart caching, timing instrumentation
- **Multi-Monitor Ready**: Per-monitor coordinate detection and logging
- **Professional Logging**: Comprehensive debug output for performance analysis

---

## 📋 Quick Start

### System Requirements
- **Windows 10/11** (DirectX screen capture)
- **Python 3.11+**
- **Multi-monitor compatible**
- **ARK: Survival Ascended** (any resolution)

### Installation

1. **Clone and Setup Environment**:
```powershell
git clone <repository-url>
cd Gangware
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r build/requirements.txt
```

2. **Launch Application**:
```powershell
python -m gangware.main
```

3. **Initial Calibration**:
   - Press **F1** to open the overlay
   - Navigate to **Debug** tab
   - Follow the setup wizard for keybind and template capture
   - Use **F6** to capture your custom inventory region for maximum speed

---

## 🎯 Core Hotkeys

| Hotkey | Function | Description |
|--------|----------|-------------|
| **F1** | Toggle Overlay | Show/hide main interface |
| **F2** | Equip Flak Set | Searches and equips flak armor from inventory |
| **F3** | Equip Tek Set | Searches and equips Tek armor from inventory |
| **F4** | Equip Mixed Set | Searches and equips mixed set from inventory |
| **Shift+Q** | Medbrew Burst | Quick consumption burst |
| **Shift+E** | Medbrew HoT Toggle | Background thread toggles healing-over-time |
| **Shift+R** | Tek Punch (Tek Dash) | Executes Tek punch sequence |
| **F6** | Capture ROI | Manual inventory region capture (two-press corner selection) |
| **F7** | Recalibrate / SIM Capture | Opens calibration UI; when SIM calibration is active, captures a point |
| **F9** | Stop SIM Calibration | Ends SIM capture mode and restores overlay |
| **F11** | Start/Stop Auto SIM | Global toggle to start/stop SIM and hide/show overlay |
| **F10** | Exit | Graceful application shutdown |

---

## 🧭 Auto SIM Usage
- Open the SIM tab in the overlay.
- Enter your server code (e.g., 2133).
- Press Start, or use the global hotkey F11 to start/stop the SIM and auto-hide/show the overlay.
- SIM Calibration: click "Start (use F7)" on the SIM tab, then press F7 to log cursor coordinates as needed; press F9 to stop.

## ⚙️ Advanced Configuration

### F6 Manual ROI Capture
For maximum performance, capture a custom inventory region:

1. **Press F6** to start ROI capture mode
2. **Click top-left** corner of your inventory area
3. **Click bottom-right** corner to complete capture
4. **ROI snapshot** saved to `%APPDATA%/Gangware/templates/roi.png`
5. **Automatic bypass** of slow auto-calibration (2+ second improvement)

### Performance Optimization
- **Template Cropping**: Focuses on item icons vs backgrounds
- **Smart Scaling**: Reduced calibration scales from 23 to 5 for speed
- **Fast/Slow Pass**: Early exit optimization for common matches
- **Mouse Timing**: Baseline 2ms movement settle, but ~20ms stabilization before/after focus clicks (e.g., search field) to ensure Ark reliably registers input

### Multi-Monitor Setup
- **Automatic Detection**: Per-monitor coordinate logging
- **Coordinate Translation**: Intelligent region mapping
- **Fallback Logic**: F6 ROI override when auto-detection fails

### Reliability Guardrails (IMPORTANT)
- Do not reduce stabilization waits around UI focus clicks below ~15–20 ms. Under-speeding these delays can cause Ark to miss focus/clicks and break macros. Current default: 20 ms before/after focusing the search box in the F2 macro.
- Keep baseline movement settle minimal (2 ms) for speed; rely on guarded waits only where necessary to ensure focus reliability.
- Configuration keys relevant to diagnostics and tuning:
  - slow_task_threshold_ms (default 1000)
  - health_monitor (True/False; default True)
  - health_interval_seconds (default 5)

### Diagnostics and Support Bundle
- Per-session logs at %APPDATA%/Gangware/logs/session-YYYYmmdd_HHMMSS/
- Includes: gangware.log, heartbeat.log, health.json, environment.json, and artifacts/
- environment.json captures monitors, game window resolution, and borderless state (if Ark is foreground at startup)

---

## 🏗️ Architecture

### Module boundaries (v6.2)
- core/hotkeys/hook.py: Windows RegisterHotKey + message pump; used by HotkeyManager
- config/hotkeys.py: centralized VK codes, modifiers, and ID→label map
- core/win32/utils.py: cursor pos, Ark window rects/title/process, foreground exe, ROI rel↔abs, ensure_ark_foreground
- core/roi/service.py: two-press F6 ROI flow (first-press hint, clamp, rel+abs persistence, snapshot, overlay updates)
- features/debug/template.py: wait_and_capture_template for F8 search-bar capture
- features/debug/keys.py: capture_input_windows and wait_key_release (Esc restart; ignores F1/F7/F8)
- gui/overlay.py: thread-safe feedback API (flash/set active/clear) via signals; SIM tab with start/stop and calibration signals; no business logic
- core/hotkey_manager.py: thin orchestration (handlers, Ark foreground checks, overlay feedback)

### Logging & artifacts
- Session-based logging in %APPDATA%/Gangware/logs/session-YYYYmmdd_HHMMSS/
- INFO for transitions/decisions; DEBUG for ROI math/coords; artifacts only on detection failures

### Run the app

```powershell
python -m gangware.main
```

Or alternatively use the batch script:

```powershell
.\tools\scripts\run.bat
```

Debug tools (Windows)
--------------------------
If calibration is not complete, the overlay will guide you through these steps:
1) Press your Inventory key (keyboard or mouse). Left/Right mouse buttons are allowed; Middle/X buttons are accepted.
2) Press your Tek Punch Cancel key (keyboard or mouse).
3) Open your inventory, hover the search bar, and press F8 to capture a small template image. The template is saved to `%APPDATA%/Gangware/templates/search_bar.png` (per-user) and its absolute path recorded in the config.

Setup is marked complete only after the template is captured and saved.

Overlay behavior
----------------
- The overlay is always on top, anchored to the top-right corner of the active screen.
- Thread-safe API: background threads use overlay.set_status_safe, set_visible_safe, flash_hotkey_line, set_hotkey_line_active, clear_hotkey_line_active
### Testing & Quality Assurance
```powershell
# Run test suite
python -m pytest tests/ -v

# Linting and types
ruff check src/
mypy src/

# Performance profiling (enable session timing in logs)
$env:GW_VISION_PERF = "1"; python -m gangware.main
```

### Contributing
1. **Fork the repository**
2. **Create feature branch**: `git checkout -b feature/amazing-optimization`
3. **Make changes** with comprehensive testing
4. **Run quality checks**: Style, tests, and performance validation
5. **Submit pull request** with detailed performance analysis

---

## 📚 Guides and Advanced Topics
- Enhanced Server Detection Deep Dive: docs/guides/enhanced_server_detection.md

## 📊 Technical Specifications

### Computer Vision Pipeline
- **OpenCV 4.8+**: Template matching with edge detection
- **MSS Library**: High-performance screen capture
- **HSV Color Space**: Tier validation via hue analysis
- **Multi-Scale Matching**: UI scaling robustness

### Performance Architecture
- **Threading Model**: Background processing with GUI thread safety
- **Memory Management**: Template caching and smart garbage collection
- **Coordinate System**: Multi-monitor aware with per-screen detection
- **Error Handling**: Graceful degradation with fallback logic

### Security & Ethics
- **External Automation**: No game file modification
- **Memory Safe**: No memory injection or process manipulation
- **Privacy Focused**: No data collection or network communication
- **Open Source**: Full source code transparency

---

## 📜 License

MIT License - See LICENSE file for details

---

## 🤝 Support

For technical support, performance optimization, or feature requests:
- **Issues**: GitHub issue tracker with performance logs
- **Documentation**: Comprehensive blueprint in `blueprint.md`
- **Performance Analysis**: Enable debug timing for optimization assistance

---

**Gangware v6.2** - Modular, observable, and fast. Where performance meets precision in ARK automation.
