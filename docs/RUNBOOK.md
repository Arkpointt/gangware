# Runbook

## Prerequisites & Setup
- Windows 10/11
- - If ove### Debug
- Verify templates: assets/debuTroubleshooting AutoSim
- If popup isn't detected: verify the template path exists and the popup is within the ROI
- Multi-ROI debugging: set GW_CF_ROIS="x1,y1,x2,y2;x1,y1,x2,y2" for multiple regions
- Debug logging: set GW_CF_DEBUG=1 for template detection scores, GW_MODAL_DEBUG=1 for modal heuristic
- Tier 3 modal: uses edge detection + contour analysis for template-less popup detection
- F11 toggle: stops current AutoSim and shows overlay, or starts new AutoSim and hides overlay
- Suppression: after pressing Enter, 2.5s suppression prevents immediate re-detection
- Resume: if watcher reaches SELECT_GAME/MAIN_MENU, signals loader to resume automation and optionally %APPDATA%/Gangware/templates/
- If debug can't find elements, try debug calibration (debug tab > Start, then press F7 at required points)
- Environment overrides supported by TemplateLibrary (e.g., custom template paths) doesn't show, confirm PyQt6 is installed and no other topmost UI obstructs it
- If clicks miss, verify DPI scaling and run debug calibration / F6 ROI again

### Debug
- Verify templates: assets/debug/ and optionally %APPDATA%/Gangware/templates/
- If detection can't find buttons, try Debug Calibration (Debug tab > Start, then press F7 at required points)
- Environment overrides supported by TemplateLibrary (e.g., custom template paths)
- Health monitor interval configurable via `health_interval_seconds` (seconds).11+
- Recommended: run in a virtual environment

Setup steps:
1) Create venv: `python -m venv .venv`
2) Activate: `.\\.venv\\Scripts\\Activate.ps1` (PowerShell)
3) Install deps: `pip install -r build/requirements.txt`

## Launch
- Dev run: `python -m gangware.main`
- Batch scripts: `tools/scripts/run.bat` (normal) or `tools/scripts/run_admin.bat` (elevated)
- Admin note: Some global hotkey integrations or input hooks may require the app to match the integrity level of Ark (run both as normal user or both as admin).

## UI Structure
- COMBAT: Tek Punch, Medbrew, Med HoT, Armor search/equip (F2/F3/F4)
- DEBUG: capture keys, F8 template, optional F6 ROI, debug calibration via F7/F9
- AUTOSIM: Server number input, Start/Stop, status feedback

## Debug/Calibration
- Open Overlay (F1)
- Debug tab: capture keys, F8 template, optional F6 ROI, debug calibration: click Start, then F7 to capture points; F9 to finish

## Package Structure (For Developers)
**Feature Packages:**
- `gangware.features.debug` - Calibration, ROI/template capture
- `gangware.features.combat` - Armor, search, tek punch, medbrew

**Supporting Packages:**
- `gangware.io` - Input controls, Windows APIs
- `gangware.vision` - Image processing, vision controller
- `gangware.core` - Hotkeys, state, task management
- `gangware.gui` - Qt overlay interface

**Import Examples:**
```python
from gangware.features.combat import ArmorMatcher, SearchService
from gangware.features.debug import CalibrationService
from gangware.io import InputController
from gangware.vision import VisionController
```

## Logs & Support
- Logs: %APPDATA%/Gangware/logs/session-<ts>/
- Artifacts: last_screenshot.png, last_template.png
- Support bundle: zip the latest session folder with environment.json

## Configuration
- File: `%APPDATA%/Gangware/config.ini` (DEFAULT section)
- Precedence: environment variables > config.ini > built-in defaults
- Common keys:
	- `log_level` (INFO/DEBUG)
	- `health_monitor` (True/False)
	- `health_interval_seconds` (default 5)
	- `ui_theme`, `resolution`, `calibration_complete`

Environment overrides (PowerShell):
```powershell
$env:GW_HEALTH_MONITOR = "True"; $env:GW_HEALTH_INTERVAL_SECONDS = "10"
```

## Graceful Shutdown
- Use the UI Exit control or press `F10`. Threads stop and logs flush.

## Troubleshooting
- Ensure ArkAscended.exe is foreground (borderless windowed)
- Check UI scale = 1.0, Windows DPI scaling 100%
- Disable pointer precision, ensure admin integrity level matches
- If hotkeys don’t work, try run_admin.bat or align Ark’s integrity level
- If overlay doesn’t show, confirm PyQt6 is installed and no other topmost UI obstructs it
- If clicks miss, verify DPI scaling and run SIM calibration / F6 ROI again

### AutoSim (Server Join)
- Start: Open overlay → Utilities/AutoSim → enter server number → press Start or F11
- Stop: Press F11 to toggle AutoSim on/off
- Foreground: AutoSim brings Ark to foreground before detection
- From any menu: AutoSim detects current menu and navigates appropriately
- BattlEye: detected via template with multi-confidence (0.8/0.7/0.6)
- Success: considered when no menus are detected for 2 consecutive seconds after Join
- Retries: up to 3 attempts; uses Back navigation to return to Select Game between attempts

Failure handling (Connection_Failed popup)
- Asset: `assets/menus/connection_failed.jpg`
- Dual detection: Template matching + Tier 3 modal heuristic (template-less edge detection)
- Watcher-level: scans during 20s post-Join window, any menu, ~80-100ms cadence
- Multi-ROI: supports multiple detection regions via GW_CF_ROIS environment variable
- Suppression: 2.5s cooldown after Enter to prevent re-detection
- On detection: presses Enter x2 to dismiss, precise rect-based clicks, bounded Back navigation (max 2 clicks)
- Automation-level: also monitors during join; sets suppression window after handling

Troubleshooting AutoSim
- If popup isn’t detected: verify the template path exists and the popup is within the central ROI
- If Back click misses: re-run SIM calibration and update `coord_back`
- If success is not recognized: enable DEBUG logs; confirm 7s of no-menu detection after Join
