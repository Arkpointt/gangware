Blueprint for the GANGWARE AI Assistant (v2)
Changelog
2025-08-18: Implemented global vs in-game hotkey logic (F1/F7/F10 global; F2/F3/F4/Shift+Q/E/R Ark-only). Hardened GUI threading by routing all UI operations through Qt signals to avoid QBasicTimer warnings. Refactored hotkey manager to reduce cognitive complexity and added diagnostics for hotkey registration failures.

2025-08-17: Blueprint upgraded to a "Living Document" with a changelog, task checklists, and a system diagram for enhanced project management and clarity.

2025-08-17: Initial blueprint creation.

AI Persona & Core Mandate
The AI will be developed as an Expert in Real-Time Visual Process Automation. Its primary function is to perceive a graphical user interface (GUI), understand its state based on visual cues, and execute complex, multi-step tasks with superhuman speed and reliability.

Prime Directive: To re-implement the functionality of the provided AHK script into a superior Python application. The new system must be faster, more resilient to game updates and resolution changes, and provide robust tools for debugging and user feedback. It will operate under a strict non-invasive protocol.

System Architecture Diagram
Code snippet

graph TD;
    subgraph User Interaction
        A[User Presses Hotkey] --> B{HotkeyManager};
    end
    subgraph AI Core
        B --> C[Task Queue];
        C --> D{Worker Thread};
    end
    subgraph AI Actions
        D -- Reads Task --> E[Macros];
        E -- Uses --> F[VisionController];
        E -- Uses --> G[InputController];
    end
    subgraph Feedback Loop
        G -- Interacts with --> H[Game Window];
        F -- Perceives --> H;
        D -- Updates --> I[GUI Overlay];
    end

Notes:
- Global hotkeys (F1/F7/F10) are registered via Win32 RegisterHotKey and have polling fallbacks. F1 toggles overlay visibility; F7 starts full calibration (keys + F8 capture); F10 exits.
- Game-only hotkeys (F2/F3/F4/Shift+Q/E/R) enqueue tasks only when the ArkAscended.exe window is active (foreground process verified via Win32 APIs). Otherwise, a toast indicates the hotkey is Ark-only.
- All GUI operations (toasts, visibility, mode switching) are executed on the GUI thread via Qt signals to ensure thread safety.

Phase 1: Foundation - The Sensory and Motor Cortex
Objective: Build core abilities to see and interact with the game world.

[x] Module: Vision System (vision.py)
    [x] Create VisionController class.
    [x] Implement find_template using OpenCV.
    [x] Add error handling when templates are not found.

[x] Module: Control System (controls.py)
    [x] Create InputController class.
    [x] Implement mouse movement, clicking, and typing via pydirectinput.

[x] Module: Configuration Core (config.py)
    [x] Create ConfigManager class.
    [x] Implement load/get/save of settings (config.ini).

Phase 2: Cognition - The Central Nervous System
Objective: Process user commands, manage internal state, and connect perception to action.

[x] Module: State & Task Management
    [x] Implement thread-safe StateManager (state.py).
    [x] Implement HotkeyManager thread (core/hotkey_manager.py).
    [x] Implement Worker thread (core/worker.py) to process queued tasks.

Phase 3: Execution - The Procedural Memory
Objective: Codify high-level tasks into intelligent workflows.

[x] Module: Macro Library (macros/)
    [x] Create armor_swapper.py.
    [x] Implement execute() for swapping armor using template matching (Vision + Input).
    [x] Create combat.py for Tek Punch and Medbrew Burst.
    [ ] Future: Implement a real Medbrew HOT toggle (placeholder currently reuses burst).

Phase 4: Interface & Diagnostics - The Frontal Lobe
Objective: Develop the UI and diagnostics.

[x] Module: User Interface (gui/overlay.py)
    [x] Create OverlayWindow with PyQt6.
    [x] Frameless, on-top themed overlay with top-right anchoring.
    [x] Signal/slot system for safe, cross-thread UI updates.
    [x] Thread-safe methods: set_status, show_toast, switch_to_main, switch_to_calibration, visibility toggle.

[ ] Module: Self-Analysis & Logging
    [ ] Configure global logging in main.py.
    [ ] Integrate logging calls (INFO, DEBUG, ERROR) across modules (replace prints gradually).
    [ ] Implement a "dry run" mode flag in ConfigManager and respected in Worker/macros.

Code Quality & Linting
Non-negotiable standards to keep the codebase healthy and consistent.

- Linter: flake8
    - Configuration in `.flake8` (max-line-length=120; ignore E203, W503).
- Editor enforcement:
    - `.editorconfig` sets 4-space indentation, trims trailing whitespace, enforces final newline.
- CI/local checks:
    - Build: `python -m compileall -q .`
    - Lint: `flake8 . --max-line-length=120`
    - Tests: `pytest -q` (smoke tests at minimum).
- Acceptance criteria for PRs:
    - Zero flake8 errors or warnings.
    - No lines > 120 chars (unless excluded).
    - All tests green.

Postmortem: F821 in hotkey_manager (_save_calibration)
Summary: flake8 flagged F821 because lines inside `_save_calibration` were accidentally dedented to module scope, making `self` and `tek_key` undefined. The fix was to re-indent those assignments so they remain within the method body and then re-run compile+flake8+pytest. `.editorconfig` and flake8 help prevent recurrence.

Pre-commit checklist (current release)
- [x] Unit tests: `pytest -q` pass locally.
- [x] Cognitive complexity warnings addressed for hotkey_manager and overlay.
- [x] GUI thread-safety validated (no QBasicTimer warnings during hotkey usage).
- [x] Global vs in-game hotkeys implemented and tested.
- [x] Blueprint updated to reflect current architecture and status.
- [ ] Logging: planned for next iteration; current prints in macros are placeholders.

Known follow-ups
- Replace `print()` calls in macros and worker with structured logging once logging is configured.
- Implement a true Medbrew HOT toggle.
- Expand tests to cover hotkey edge cases, Ark window detection, and overlay signal pathways.
