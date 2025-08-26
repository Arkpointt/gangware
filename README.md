# Gangware
## Advanced Computer Vision Automation for ARK: Survival Ascended

**Version 6.5** — Package-by-Feature, Deterministic, Observable

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![OpenCV](https://img.shields.io/badge/OpenCV-Computer%20Vision-green.svg)](https://opencv.org)
[![PyQt6](https://img.shields.io/badge/PyQt6-GUI%20Framework-orange.svg)](https://www.riverbankcomputing.com/software/pyqt/)

Gangware is a high-performance automation system designed for ARK: Survival Ascended. It features robust computer vision, package-by-feature architecture, and strict engineering guardrails defined in the Engineering Blueprint (docs/blueprint.md).

—

## 🚀 Key Features

### ⚡ Combat & Inventory Automation
- Sub-second armor swapping (when ROI captured)
- F6 Manual ROI for fast inventory matching
- Search-and-type service with robust input handling
- Multi-monitor aware coordinates and ROI translation

### 🎯 Vision Pipeline
- Template matching (OpenCV TM_CCOEFF_NORMED)
- Inventory ROI calibration and sub-ROI intersection
- Fast-only search option for latency-sensitive operations
- Artifact capture on detection failures (for troubleshooting)

### 🧠 AutoSim (Automated Server Join)
- Dual-signal failure detection (template + modal heuristic)
- Multi-ROI support via GW_CF_ROIS
- Success detection: 2 seconds consecutive no-menu
- Shared state across watcher/automation with gating window
- F11 global toggle with overlay hide/show

### 🧰 Engineering Discipline
- Package-by-feature layout under src/gangware/
- Deterministic timing, bounded retries, explicit gates
- Structured logs with INFO for transitions and DEBUG for details
- Windows-friendly focus and integrity handling (no injection)

—

## 📋 Quick Start

### System Requirements
- Windows 10/11
- Python 3.11+
- ARK: Survival Ascended (borderless windowed recommended)

### Installation

1. Clone and Setup Environment:
```powershell
git clone <repository-url>
cd Gangware
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r build/requirements.txt
```

2. Launch Application:
```powershell
python -m gangware.main
```

3. Initial Calibration:
- Press F1 to open the overlay
- Go to the Debug tab
- Capture Inventory and Tek Cancel keys
- Use F6 to capture inventory ROI (two presses)
- Use the coordinate dropdown + F7 to capture key UI coordinates

—

## 🎮 Hotkeys

| Hotkey | Function |
|--------|----------|
| F1     | Toggle Overlay |
| F2     | Equip Flak Set |
| F3     | Equip Tek Set |
| F4     | Equip Mixed Set |
| Shift+Q| Medbrew Burst |
| Shift+E| Medbrew HoT (background thread) |
| Shift+R| Tek Punch (preserves jetpack) |
| F6     | ROI capture (two-press corners) |
| F7     | Recalibration / Coordinate capture |
| F9     | Stop calibration (if applicable) |
| F11    | Start/Stop AutoSim |
| F10    | Exit |

—

## 🧭 AutoSim Usage
- Open Utilities tab in the overlay
- Enter server number (e.g., 2133)
- Press Start or F11 to begin; overlay hides during automation
- Automation uses watcher state; success = 2s no-menu
- Connection_Failed is dismissed automatically; workflow resumes deterministically

See docs/autosim-comprehensive.md and docs/autosim-success-detection-fix.md.

—

## 🏗️ Architecture

- Package-by-Feature: src/gangware/features/{combat,autosim,debug}
- Shared utilities: core/, io/, vision/, gui/
- Dependency injection for services
- Event flow: hotkeys/overlay → task queue/worker → feature modules → io/vision

Refer to docs/blueprint.md (authoritative) for principles, structure, testing, and performance budgets.

—

## 📑 Documentation & ADRs
- Blueprint (authoritative): docs/blueprint.md
- Runbook: docs/RUNBOOK.md
- Testing: docs/TESTING.md
- Security: docs/SECURITY.md
- Commenting Standards: docs/CONTRIBUTING-COMMENTS.md
- Architectural Decision Records: docs/adr/
  - ADR-0009: Package-by-Feature structure and legacy removal
  - ADR-0010: AutoSim detection strategy and state model
  - ADR-0011: AutoSim retry logic fix (infinite loop prevention)
  - (See folder for additional ADRs.)

—

## 🔍 Diagnostics & Support Bundle
- Logs under %APPDATA%/Gangware/logs/session-<timestamp>/
- Includes gangware.log, health.json, environment.json, artifacts on failures
- Enable performance metrics with GW_VISION_PERF=1

—

## 🧪 Quality Gates
```powershell
ruff check src/
mypy src/
pytest -q
```

—

## 🔒 Security & Ethics
- External OS input only; no code/memory injection
- No telemetry; logs avoid PII

—

## 📄 License
MIT License — see LICENSE
