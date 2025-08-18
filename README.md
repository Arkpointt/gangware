Gangware AI Assistant (v2)
==========================

Overview
--------
Gangware is a modular Python application for real-time visual process automation, inspired by Ark: Ascended aesthetics.

Project Structure
-----------------
The project follows a professional src layout:

```
src/
└── gangware/              # Main application package
    ├── core/             # Core functionality (config, state, etc.)
    ├── controllers/      # Input and vision controllers
    ├── gui/             # User interface components
    ├── macros/          # Automation macros
    └── main.py          # Application entry point
```

Quick start
-----------
1. Create and activate a virtual environment (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

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
- It automatically repositions on resolution/DPI/monitor changes.
- Press F1 to hide/unhide the overlay. Press F7 to recalibrate at any time (global or via overlay).

Notes
-----
- The overlay uses the Consolas font (default on Windows). If the font is not available, the system will fall back to a monospace font.
- To interact with the overlay during development, remove `Qt.WindowTransparentForInput` in `gui/overlay.py`.

Aesthetics
---------
The UI uses a Tek-inspired neon palette (cyan accents) with a dark translucent background and Consolas font to match the Ark: Ascended theme.

Contributing
------------
- Keep modules small and testable.
- Update `requirements.txt` when adding new dependencies.
- File issues or PRs on the repository: https://github.com/Arkpointt/gangware
