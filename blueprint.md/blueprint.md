Gangware Engineering Blueprint (v5.0)

Changelog
- 2025-08-21: Generalized blueprint from vision/UI-only to a full project engineering blueprint; added engineering principles, workflows, testing/CI, release, observability, performance budgets, and platform constraints. Cleaned prior formatting issues. Preserved UI tokens as an authoritative appendix.
- 2025-08-19: Major performance update (v4.0). Implemented sub-second armor swapping with F6 manual ROI capture, template cropping optimizations, fast/slow pass matching, ROI calibration bypass, and multi-monitor coordinate handling.
- 2025-08-18: Added “Gangware UI – AI Design Blueprint” tokens and strict rules section; marked as authoritative for UI visuals.
- 2025-08-18: Blueprint refactored to support a full-featured, two-page GUI (Main + Calibration).
- 2025-08-18: UI/Overlay design specification added (Ark-inspired Floating HUD).
- 2025-08-17: Blueprint upgraded to a “Living Document” with changelog, task checklists, and a system diagram.
- 2025-08-17: Initial blueprint creation.

Purpose & Scope
This blueprint is the single source of truth for how Gangware is engineered, tested, released, and supported. It defines:
- Principles and decision-making
- Architecture and project structure
- Development workflow, branching, code quality, and review
- Testing strategy and CI/CD
- Configuration, secrets, and environment management
- Observability and performance budgets
- Platform constraints (Windows, DPI, multi-monitor)
- Asset/template capture rules for automation features
- UI design tokens and visual rules (authoritative appendix)

Guiding Principles
1) Correctness first, speed second: automation must be safe and deterministic before we optimize.
2) Determinism over flakiness: prefer bounded waits, explicit gates, and idempotent actions.
3) Explicit observability: every non-trivial path emits structured logs with correlation IDs.
4) Fail closed: on uncertainty, do the safe thing (don’t click) and log why.
5) Config over code: behavior toggles via config/env; code contains defaults and safe fallbacks.
6) Small, reversible steps: short-lived branches, small PRs, fast code reviews.
7) User empathy: every error must suggest a resolution (missing template paths, DPI hints, etc.).

High-Level Architecture
graph TD;
    subgraph User Interaction
        A[User Presses Hotkey] --> B[HotkeyManager];
        I[GUI Overlay] -- User Clicks --> B;
    end
    subgraph Core
        B --> C[Task Queue];
        C --> D[Worker Thread];
        D --> F[VisionController];
        D --> G[InputController];
        D --> M[Feature Modules];
    end
    subgraph Environment
        F -- capture --> H[Game Window];
        G -- input --> H;
    end
    subgraph Observability
        D -- events --> L[Logging + Artifacts];
        F -- perf --> L;
    end

Project Structure Conventions
- src/gangware: application modules
  - controllers/: vision.py, controls.py, input/output abstractions
  - features/: user-facing workflows (e.g., auto_sim)
  - gui/: overlay/Qt UI
  - core/: hotkeys, worker, health, logging
  - config/: tunables and constants
  - vision/: pure image processing and matching utilities
  - io/: platform-specific helpers (Windows APIs)
- assets/: bundled templates and images (read-only)
- %APPDATA%/Gangware/templates/: user-provided templates, override assets
- logs/: per-session logs and artifacts (auto-created)
- tests/: unit, integration, e2e (TBD)

Branching, Versioning, and Releases
- Branching model: trunk-based with short-lived topic branches
  - main: releasable at all times
  - feature/<name>: short-lived; open PR to main
  - hotfix/<ticket>: emergency fixes from main
- Commit messages: Conventional Commits (feat:, fix:, perf:, refactor:, docs:, test:, chore:)
- Versioning: SemVer X.Y.Z
  - bump patch for fixes and perf improvements
  - bump minor for compatible features
  - bump major for breaking changes
- Release channel: tagged releases from main; build artifacts (installer/exe) published with changelog

Coding Standards (Python)
- Python 3.11+
- Style: black (88 width), isort, ruff lint; mypy for typed modules
- Type hints for public APIs and critical internal paths
- Docstrings: Google or NumPy style consistently; include parameters and returns
- Logging: use structured log helpers; no print()
- OS interactions: isolate platform-specific code under io/ modules
- Threading: never block GUI thread; use worker thread and signals/slots

Development Workflow
1) Open issue or task with acceptance criteria
2) Create feature/<name> branch
3) Implement with unit tests where feasible; add integration test hooks
4) Update config knobs and env var documentation if behavior changes
5) Update blueprint (this document) when adding new rules or altering processes
6) Open PR with:
   - What and why (design notes), risks, toggles
   - Logs or screenshots for critical flows
   - Test evidence and manual QA checklist
7) Reviewer enforces standards; CI must pass; merge squash

Testing Strategy
- Unit tests: pure vision utilities, config parsing, helpers
- Integration tests: VisionController with mocked mss frames; InputController dry-run
- E2E smoke: launch overlay, simulate start/stop, validate log beacons and state transitions
- Performance tests: perf toggles (GW_VISION_PERF) and budget assertions
- Coverage target: 70%+ overall; critical modules >80%

CI/CD (reference pipeline)
- Lint/type: ruff + mypy
- Test: pytest with coverage report
- Build: PyInstaller build on Windows runner
- Artifacts: upload logs from failed tests; attach build artifacts to releases
- Security: dependency scan (pip-audit)

Configuration & Secrets
- Config file: %APPDATA%/Gangware/config.ini (defaults in repo under config/)
- Env vars (documented, non-exhaustive):
  - GW_VISION_ROI: absolute ROI "left,top,width,height"
  - GW_INV_SUBROI: sub-ROI fractions for inventory "l,t,w,h"
  - GW_VISION_FAST_ONLY: 1 to skip slow multiscale pass
  - GW_VISION_PERF: 1 to emit perf metrics
- Secrets: never committed; use Windows Credential Manager or .env.local excluded via .gitignore

Observability and Support
- Per-session log directory: %APPDATA%/Gangware/logs/session-YYYYmmdd_HHMMSS/
  - gangware.log, heartbeat.log, health.json, environment.json, artifacts/
- Structured log events: use consistent event keys (feature=, event=, id=)
- Artifacts: last_screenshot.png + last_template.png on vision miss
- Perf: VisionController.get_last_perf() and GW_VISION_PERF for timing
- Support process: share latest session folder; logs include monitor topology and Ark window bounds

Performance Budgets
- UI responsiveness: overlay actions < 50 ms
- Start sequence: state detection fast path < 1.5 s; avoid slow pass unless needed
- Auto Sim loop:
  - Search focus + type + apply <= 400 ms typical
  - Server availability detection <= 500 ms with constrained ROI
  - Join assessment loop: 150 ms polling; timeout default 15 s
- Mouse movement settle: ~2–15 ms depending on context; never > 35 ms without rationale

Platform Constraints (Windows)
- DPI and scaling:
  - Prefer 100% scaling on all monitors while testing
  - Override high DPI scaling for the runner executable and Ark (Application mode)
- Windowing:
  - Borderless windowed at fixed resolution on primary monitor: -windowed -noborder -ResX=3840 -ResY=2160
  - Ensure ARK UI scale 1.0 and exact in-game resolution
- Focus stability:
  - Run both Ark and Gangware at same integrity level (ideally Administrator)
  - Disable overlays: Steam/NVIDIA/Discord/Xbox Game Bar
  - Focus Assist: Alarms only
- Mouse:
  - Disable "Snap To" and "Enhance pointer precision"
  - Temporarily disable vendor mouse drivers/macros during automation
- Multi-monitor:
  - Constrain cursor to Ark monitor during automation if needed
  - Keep taskbar off the Ark monitor or set to auto-hide

Templates & Asset Capture Rules
- Locations:
  - Bundled: assets/auto sim
  - User overrides: %APPDATA%/Gangware/templates/auto_sim
- Naming & synonyms: use TemplateLibrary canonical names; provide synonyms for backwards-compatibility
- Capture guidance:
  - Tight crops on distinctive features; avoid large backgrounds
  - Re-capture when resolution, UI scale, or HDR setting changes
  - Maintain both star-only and row templates where applicable
- Acceptance and gating:
  - Use geometric gates (header divider, row bands, proximity) to avoid false positives
  - Document confidence thresholds per template category in code comments and here

Feature Modules: Definition of Done
- Logs: at least one info beacon per major step; warnings on fallbacks; errors on exceptions
- Config: tunables documented in config.ini and here
- Tests: unit coverage where feasible; at least one integration hook
- Performance: respects budgets; perf toggles tested
- UI: adheres to Tokens (see appendix)
- Docs: README and this blueprint updated

Incident Response & Hotfix Protocol
- Severity triage: S1 (blocking clicks/wrong window), S2 (feature broken), S3 (degraded)
- Repro bundle: session logs + environment.json + artifacts
- Hotfix branch hotfix/<ticket> from main; targeted fix; tag patch release with concise changelog
- Postmortem: root cause, detection gaps, and guardrail additions documented here

Security & Privacy
- No network telemetry or data collection
- Local-only logs under %APPDATA%; redact PII if introduced
- No code injection or memory manipulation; input is standard OS events

Quickstart (Developer)
- Create virtual environment and install deps per README
- Run: .\run.bat
- Enable perf logs (optional): set GW_VISION_PERF=1
- Force fast-only matching (optional): set GW_VISION_FAST_ONLY=1

Acceptance Criteria (Project-wide)
- Feature PRs include: rationale, logs/screenshots, tests, config notes
- CI green (lint, type, tests); build succeeds on Windows runner
- Performance within budgets or justified
- UX conforms to UI Tokens; no external fonts; no unsupported QSS

---

Appendix A — Gangware UI – AI Design Blueprint (Authoritative Visual Tokens)

Purpose
Defines the exact design system for Gangware’s HUD and Calibration UI. All visual changes must follow these tokens and rules.

Tokens (Do not change these values)
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

Layout rules
- Container: Header → Tabs → Stacked Pages → Footer
- Main Page: Combat (left), Armor (right), Core (bottom)
- Calibration Page: Keybind Setup, Visual Template, Start button in footer
- Layout may scale; styling must remain identical

Styling rules
- Buttons: semi-transparent cyan background, border, glow on hover
- Section headers: orange text with glow
- Keybinds: cyan keycaps (rounded, bold text)
- Footer: status line with STATUS: OPERATIONAL (green when OK)

Overlay specifics (Ark-inspired Floating HUD)
- Top-right anchor; frameless, translucent, always-on-top
- Gradient background (derive from BACKGROUND_* tokens) with cyan accent line
- Typography: Orbitron preferred (if installed), else Segoe UI/Consolas; no external font downloads
- No CSS text-shadow; use QGraphicsDropShadowEffect for glow in Qt

Navigation and Interactions
- Two tabs: MAIN and CALIBRATION; active tab indicated by cyan underline/border
- Button height ~28–32 px; compact density with small paddings/margins
- Feedback: success_flash (~850 ms), hotkey flash/hold/clear behaviors

Calibration Page Structure
- Tasks capture:
  - Inventory Key (keyboard/mouse)
  - Tek Cancel Key (keyboard/mouse)
  - Inventory Template (hover search bar and press F8)
  - Manual ROI via F6 two-press selection with visual feedback
- Status boxes: “[ None ]” → “[ Captured ]” or “[ key ]”; ROI shows “[ Set ]” with tooltip of coordinates
- Start button primary, right-aligned; enabled only when all required items are captured

Acceptance Criteria (UI)
- Overlay renders top-right; cyan-accent gradient; segmented navigation
- Main shows three logical areas with compact cyan keycaps
- Calibration shows required tasks, statuses, and Start button with wiring
- Animations fast and consistent; no missing fonts or unsupported QSS warnings
