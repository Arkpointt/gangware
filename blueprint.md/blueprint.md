Blueprint for the GANGWARE AI Assistant (v4.0)
Changelog
2025-08-19: Major performance o6) Calibration Page Structure
- Purpose: guide user to capture four items:
  - Inventory Key (keyboard/mouse)
  - Tek Cancel Key (keyboard/mouse)
  - Inventory Template (hover search bar and press F8)
  - **Manual ROI (F6 two-press capture for precise armor matching area)**
- Each task row contains: label, action button, and a compact status box (initial "[ None ]", becomes "[ Captured ]" or "[ key ]").
- **F6 ROI row displays "[ Set ]" with tooltip showing coordinates when captured**
- Start button is the primary action aligned right. Enabled only when all items are captured.
- Signals and wiring:
  - capture_inventory -> prompt to capture inventory key
  - capture_tek -> prompt to capture tek cancel key
  - capture_template -> F8-triggered template capture
  - **capture_roi -> F6 two-press manual ROI selection with visual feedback**
  - start -> allow_calibration_start gate to proceedupdate (v4.0). Implemented sub-second armor swapping with F6 manual ROI capture, template cropping optimizations, fast/slow pass matching, ROI calibration bypass, and multi-monitor coordinate handling. Achieved target of <1 second total F2 execution time.

2025-08-18: Added "Gangware UI – AI Design Blueprint" tokens and strict rules section; marked as authoritative for UI visuals while preserving prior context.

2025-08-18: Blueprint refactored to support a full-featured, two-page GUI. The interface will now include a "Main" view for displaying hotkeys and a "Calibration" view for setup, with seamless navigation between them. This supersedes the previous simplified UI plan.

2025-08-18: UI/Overlay design specification added. Establishes Ark-inspired Floating HUD as the canonical style for all present and future screens.

2025-08-17: Blueprint upgraded to a "Living Document" with a changelog, task checklists, and a system diagram.

2025-08-17: Initial blueprint creation.

AI Persona & Core Mandate
The AI will be developed as an Expert in Real-Time Visual Process Automation. Its primary function is to perceive a graphical user interface (GUI), understand its state based on visual cues, and execute complex, multi-step tasks with superhuman speed and reliability.

Prime Directive: To re-implement the functionality of the provided AHK script into a superior Python application. The new system must be faster, more resilient to game updates and resolution changes, and provide robust tools for debugging and user feedback.

Design Precedence & Conflict Resolution
- The "Gangware UI – AI Design Blueprint" Tokens are the visual source of truth. If any instruction elsewhere conflicts, Tokens win (colors, radii, fonts, effects, components).
- Fonts: Prefer Orbitron (if installed) with fallbacks Segoe UI and Consolas. Do not download external fonts. Older notes that only mention Segoe UI/Consolas remain valid as fallbacks.
- Key inputs display: Older references to "angled polygon badges" are legacy. Canonical style is cyan keycaps (rounded boxes with bold glowing text) per Tokens.
- Backgrounds/gradients: May be used, but derive values from BACKGROUND_CARD and BACKGROUND_SECTION Tokens; accent borders/glows remain cyan/orange per Tokens.
- Resizing/rearranging must not remove required sections; styling remains identical to Tokens.

System Architecture Diagram
graph TD;
    subgraph User Interaction
        A[User Presses Hotkey] --> B[HotkeyManager];
        I[GUI Overlay] -- User Clicks --> B;
    end
    subgraph AI Core
        B --> C[Task Queue];
        C --> D[Worker Thread];
    end
    subgraph AI Actions
        D -- Reads Task --> E[Macros];
        E -- Uses --> F[VisionController];
        E -- Uses --> G[InputController];
    end
    subgraph Feedback Loop
        G -- Interacts with --> H[Game Window];
        F -- Perceives --> H;
        D -- Updates --> I;
    end

Notes:

The GUI will feature a two-page design ("Main" and "Calibration") managed by a QStackedWidget.

Navigation buttons will allow the user to switch between views.

The application will start in "Calibration" mode if setup is incomplete, and in "Main" mode otherwise.


UI/Overlay Design Specification (Ark-inspired Floating HUD)
This specification is authoritative. All current and future UI must adhere to these rules to ensure a consistent design.

1) Concept and Placement
- Floating HUD overlay anchored to the top-right of the primary screen.
- Frameless, translucent, always-on-top window, click-through disabled (the overlay is interactive when visible).
- Primary container uses a subtle horizontal gradient with a cyan accent border.

2) Visual Language
- Palette: Cyan #00DDFF (primary accent), Orange #FFB800 (secondary category accent), neutrals in the #C8–#E6 range.
- Background: gradient from rgba(10,25,40,0.85) to rgba(10,25,40,0.60) with a 3px cyan accent line on the left of content containers. Base colors should be derived from BACKGROUND_CARD/BACKGROUND_SECTION Tokens.
- Title: “GANGWARE” with a subtle cyan glow (implemented using QGraphicsDropShadowEffect, not CSS text-shadow).
- Typography: use system-safe fonts (Segoe UI/Consolas). Prefer Orbitron if installed; Segoe UI/Consolas are fallbacks per Tokens. Do not depend on external font files. Avoid unsupported QSS like text-shadow.

3) Navigation
- Segmented navigation with two tabs: MAIN and CALIBRATION.
- Buttons are checkable; the active tab is indicated via a stronger cyan bottom border and text color. No heavy filled backgrounds.
- Keep buttons compact: approx 28–32 px tall, padding 6–12 px horizontally.

4) Layout and Density
- Overall overlay width: ~420 px height: ~260 px initial (auto-resize permitted via content).
- Margins/padding: root 10 px; container 12 px; grid row spacing 6–10 px; column spacing ~18–25 px.
- High information density: minimize empty space; avoid large button blocks.

5) Main Page Structure
- Three columns: COMBAT (cyan), ARMOR SWAP (orange), CORE (cyan).
- Items:
  - COMBAT: Medbrew (Shift+Q), HoT (Shift+E), Tek Punch (Shift+R)
  - ARMOR SWAP: Flak (F2), Tek (F3), Mixed (F4)
  - CORE: Hide (F1), Recal (F7), Exit (F10)
- Key badges: angled polygon badges with cyan 2px stroke and a faint cyan fill. Text centered, compact (9–10 pt), medium/semibold. Minimum size ~60x22 px. (Legacy style; canonical display is cyan keycaps per Tokens.)

6) Calibration Page Structure
- Purpose: guide user to capture three items:
  - Inventory Key (keyboard/mouse)
  - Tek Cancel Key (keyboard/mouse)
  - Inventory Template (hover search bar and press F8)
- Each task row contains: label, action button, and a compact status box (initial “[ None ]”, becomes “[ Captured ]” or “[ key ]”).
- Start button is the primary action aligned right. Enabled only when all three items are captured.
- Signals and wiring:
  - capture_inventory -> prompt to capture inventory key
  - capture_tek -> prompt to capture tek cancel key
  - capture_template -> F8-triggered template capture
  - start -> allow_calibration_start gate to proceed

7) Feedback and Animations
- success_flash: brief green (#1BD97B) status tint, ~850 ms, then revert.
- Hotkey feedback:
  - flash_hotkey_line(hotkey): quick cyan border/text flash of the corresponding key badge (~400 ms).
  - set_hotkey_line_active(hotkey): persistent cyan border indicating active/toggled state (e.g., Shift+E HoT).
  - clear_hotkey_line_active(hotkey, fade): brief fade-out (~300–400 ms) returning to rest style.

8) Keyboard Shortcuts and Behavior
- HotkeyManager owns global hotkeys: F1 toggle overlay, F7 recalibrate, F10 exit, and in-game macro keys.
- Overlay provides fallback shortcuts (Application context): F1 toggle visibility, F7 trigger recalibration, F10 close.
- When switching tabs, update check-state of nav buttons; avoid heavy restyling—use underline/border and weight.

9) Accessibility and Constraints
- Focus-visible: ensure tab focus is visible on buttons/badges (1–2 px outline acceptable via QSS if needed).
- Contrast: maintain readable contrast for small text (>= 4.5:1 on dark backgrounds).
- No external fonts or unsupported QSS properties. Do not use CSS text-shadow; use QGraphicsDropShadowEffect for glow.

10) Do / Don’t
- Do: keep UI compact, avoid oversized buttons, keep consistent cyan/orange accents, keep animations fast.
- Do: retain segmented navigation for brand consistency. Note: "angled key badges" are legacy; use cyan keycaps per Tokens.
- Don’t: introduce heavy fills, large gaps, or long neon glows. Don’t rely on custom font files.

11) Acceptance Criteria
- The overlay renders top-right, frameless, with cyan-accent gradient container and segmented navigation.
- Main shows three columns and the listed items with compact cyan keycaps (supersedes earlier "angled key badges").
- Calibration shows three task rows with status boxes and a Start button, all wired to signals as specified.
- success_flash and hotkey flash/hold/clear behave as specified.
- Works with system fonts; no runtime warnings about missing fonts or unsupported QSS.


Phase 1: Foundation - The Sensory and Motor Cortex
Objective: Build core abilities to see and interact with the game world.

[x] Module: Vision System (vision.py)

[x] Module: Control System (controls.py)

[x] Module: Configuration Core (config.py)

Phase 2: Cognition - The Central Nervous System
Objective: Process user commands, manage internal state, and connect perception to action.

[x] Module: State & Task Management

[x] Implement thread-safe StateManager (state.py).

[x] Implement HotkeyManager thread (core/hotkey_manager.py).

[x] Implement Worker thread (core/worker.py).

Phase 3: Execution - The Procedural Memory
Objective: Codify high-level tasks into intelligent workflows.

[x] Module: Macro Library (macros/)

[x] Create armor_swapper.py with "Smart Armor" logic.

[x] Create combat.py for Tek Dash and Medbrew macros.

[x] Implement dedicated threading for Medbrew HoT.

**Phase 3.5: Performance Engineering - The Speed Layer**
**Objective: Achieve sub-second armor swapping through advanced computer vision optimizations.**

[x] **Module: Advanced Armor Matching (armor_matcher.py)**

[x] **Implement hybrid template matching with edge detection and HSV hue validation**

[x] **Create fast/slow pass optimization with early exit on good matches**

[x] **Add template cropping to focus on item icons vs inventory slot backgrounds**

[x] **Implement multi-scale template matching for UI scaling robustness**

[x] **Add performance timing instrumentation and debugging**

[x] **Module: Precision ROI Management**

[x] **Implement F6 two-press manual ROI capture system with visual feedback**

[x] **Add ROI persistence to config.ini and environment variable coordination**

[x] **Create ROI intersection and fallback logic for multi-monitor setups**

[x] **Add F6 ROI snapshot saving to %APPDATA%/Gangware/templates/roi.png**

[x] **Optimize ROI calibration bypass when F6 ROI available (eliminates 2+ second delay)**

[x] **Module: Input System Optimization**

[x] **Reduce mouse movement delays from 20ms to 2ms for instant targeting**

[x] **Optimize click timing and sleep intervals for minimal latency**

[x] **Add comprehensive timing debug for performance analysis**

Phase 4: Interface & Diagnostics - The Frontal Lobe
Objective: Develop the UI and diagnostics.

[x] Module: User Interface (gui/overlay.py)

[x] Create OverlayWindow with a frameless, top-right, Ark-inspired design.

[x] Implement a QStackedWidget to manage two views: "Main" and "Calibration".

[x] Create navigation buttons to switch between the two views.

[x] "Main" View: Design a clean, multi-column layout to display all macro hotkeys.

[x] "Calibration" View: Design a unified menu for all setup tasks (keybinds, template capture) with interactive buttons and status indicators.

[x] Implement logic to start in the correct view based on calibration_complete flag.

[x] Implement signal/slot system for safe, cross-thread UI updates.

[x] **Add F6 Manual ROI capture with visual feedback and status display**

[x] **Implement real-time calibration status updates and ROI capture confirmation**

[ ] Module: Self-Analysis & Logging

Performance Guardrails (Authoritative)
- Mouse/UI focus timing: Maintain ~20 ms stabilization before/after focus-critical clicks (e.g., search field) to ensure Ark reliably registers focus. Do NOT lower below ~15 ms without a validated test plan. Baseline movement settle may remain at ~2 ms.
- Speed vs reliability: Prefer minimal waits everywhere else, but protect UI focus transitions explicitly to avoid regressions.
- Configurable diagnostics: slow_task_threshold_ms (default 1000), health_monitor (default True), health_interval_seconds (default 5).

Diagnostics & Support Bundle
- Per-session folder at %APPDATA%/Gangware/logs/session-YYYYmmdd_HHMMSS/
- Contents: gangware.log, heartbeat.log, health.json, environment.json, artifacts/
- environment.json includes monitor topology, game window resolution, and borderless state when Ark is foreground at startup.
- Macro tracing: F2 logs phase timings with correlation IDs (macro=F2 phase=... corr=...).

[x] Configure global logging in main.py.

[x] Integrate logging calls (INFO, DEBUG, ERROR) across all modules.

[x] **Add performance timing instrumentation and debug logging**

[x] **Implement multi-monitor detection and coordinate debugging**

[ ] Implement a "dry run" mode.

Design Consistency Directive
All future UI changes must conform to the UI/Overlay Design Specification above. Any deviation requires an explicit changelog entry and approval with clear rationale. This ensures the Ark-inspired Floating HUD remains consistent throughout the application.

---

# Gangware UI – AI Design Blueprint 🎨

This section is authoritative for UI tokens and visual rules. Do not delete any past design context; if conflicts arise, the tokens and rules below take precedence for visuals while earlier sections remain for historical intent and architecture.

## Purpose
This blueprint defines the exact design system for Gangware’s HUD and Calibration UI. All AI contributions must follow these rules strictly.

## Tokens (Do not change these values)
- COLOR_PRIMARY: #00DDFF (cyan glow)
- COLOR_ACCENT: #FFB800 (orange glow)
- COLOR_TEXT: #D5DCE3 (default text)
- COLOR_STATUS_OK: #31F37A (status “operational” green)
- BACKGROUND_CARD: rgba(10,20,30,0.85)
- BACKGROUND_SECTION: rgba(18,28,40,0.60)
- BORDER_RADIUS: 14px (card), 10px (sections), 8px (buttons)
- FONT_FAMILY: Orbitron, Segoe UI, Consolas
- FONT_TITLE_SIZE: 34px
- FONT_CATEGORY_SIZE: 18px
- KEYCAP_STYLE: cyan border, bold text, dark background
- GLOW_RADIUS: 24–36px (depending on widget importance)

## Layout rules
- Always use the card layout with:
  - Header → Tabs → Stacked Pages → Footer
- Main Page must have:
  - Left: Combat Section
  - Right: Armor Section
  - Bottom: Core Section
- Calibration Page must have:
  - Keybind Setup section
  - Visual Template section
  - Start button in footer
- Layout may scale (bigger/smaller, grid rearrangement) but styling must remain identical.

## Styling rules
- All borders use cyan glow (COLOR_PRIMARY) or orange (COLOR_ACCENT) for highlights.
- All buttons follow ark-button style: semi-transparent cyan background, border, glow on hover.
- Section headers use orange text with glow.
- Keybinds must render as cyan keycaps (rounded boxes with bold glowing text).
- Footer must always show a status line with STATUS: OPERATIONAL (green if OK).

## AI Guidance
When generating UI code (PyQt6, HTML, CSS, or any language):
1. Always pull visual values from the tokens above — never invent new colors, fonts, or radii.
2. If resizing, scaling, or rearranging:
   - Respect proportions.
   - Do not remove required sections (Combat, Armor, Core, Calibration).
3. Glow effects, transparency, and neon feel are mandatory.
4. If uncertain, default to this design instead of making up new styles.
5. Document any new component’s token usage (e.g., “button background uses BACKGROUND_SECTION + COLOR_PRIMARY border”).