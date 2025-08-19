# Gangware
## Advanced Computer Vision Automation for ARK: Survival Evolved

**Version 4.0** - Professional Performance-Optimized Gaming Assistant

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![OpenCV](https://img.shields.io/badge/OpenCV-Computer%20Vision-green.svg)](https://opencv.org)
[![PyQt6](https://img.shields.io/badge/PyQt6-GUI%20Framework-orange.svg)](https://www.riverbankcomputing.com/software/pyqt/)

Gangware is a high-performance automation system designed specifically for ARK: Survival Evolved, featuring sub-second armor swapping, intelligent computer vision, and advanced macro capabilities. Built with professional-grade optimization techniques, Gangware delivers lightning-fast equipment management and combat automation.

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
- **ARK: Survival Evolved** (any resolution)

### Installation

1. **Clone and Setup Environment**:
```powershell
git clone <repository-url>
cd Gangware
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. **Launch Application**:
```powershell
python main.py
```

3. **Initial Calibration**:
   - Press **F1** to open the overlay
   - Navigate to **Calibration** tab
   - Follow the setup wizard for keybind and template capture
   - Use **F6** to capture your custom inventory region for maximum speed

---

## 🎯 Core Hotkeys

| Hotkey | Function | Description |
|--------|----------|-------------|
| **F1** | Toggle Overlay | Show/hide main interface |
| **F2** | Smart Armor Swap | Sub-second helmet/armor equipment |
| **F3** | Tek Dash Combo | Advanced movement sequence |
| **F4** | Medbrew Cycle | Intelligent healing management |
| **F6** | Capture ROI | Manual inventory region capture |
| **F7** | Recalibrate | Reset vision calibration |
| **F10** | Exit | Graceful application shutdown |

---

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

2. (Optional) Enable UI demo in `config/config.ini` by setting `ui_demo = True` under `[Settings]` to see live status updates.

3. Run the app:

```powershell
python main.py
```

Or alternatively use the batch script:

```powershell
.\run.bat
```

Calibration flow (Windows)
--------------------------
If calibration is not complete, the overlay will guide you through these steps:
1) Press your Inventory key (keyboard or mouse). Left/Right mouse buttons are not allowed. Middle/X buttons are accepted.
2) Press your Tek Punch Cancel key (keyboard or mouse). Same restrictions as above.
3) Open your inventory, hover the search bar, and press F8 to capture a small template image. The template is saved to `%APPDATA%/Gangware/templates/search_bar.png` (per-user) and its absolute path recorded in the config.

Calibration is marked complete only after the template is captured and saved.

Overlay behavior
----------------
- The overlay is always on top, click-through, and anchored to the top-right corner of the active screen.
### Testing & Quality Assurance
```powershell
# Run test suite
python -m pytest tests/ -v

# Style and complexity analysis
python -m flake8 src/
python -m bandit -r src/

# Performance profiling
python main.py --debug-timing
```

### Contributing
1. **Fork the repository**
2. **Create feature branch**: `git checkout -b feature/amazing-optimization`
3. **Make changes** with comprehensive testing
4. **Run quality checks**: Style, tests, and performance validation
5. **Submit pull request** with detailed performance analysis

---

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

**Gangware v4.0** - Where performance meets precision in ARK automation.
