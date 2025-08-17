Gangware AI Assistant (v2)
==========================

Overview
--------
Gangware is a modular Python application for real-time visual process automation, inspired by Ark: Ascended aesthetics.

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

Notes
-----
- The overlay uses the Consolas font (default on Windows). If the font is not available, the system will fall back to a monospace font.
- The overlay is designed to be click-through and non-invasive. If you need to interact with it during development, remove `Qt.WindowTransparentForInput` from `gui/overlay.py`.

Aesthetics
---------
The UI uses a Tek-inspired neon palette (cyan accents) with a dark translucent background and Consolas font to match the Ark: Ascended theme.

Contributing
------------
- Keep modules small and testable.
- Update `requirements.txt` when adding new dependencies.
- File issues or PRs on the repository: https://github.com/Arkpointt/gangware
