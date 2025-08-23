Gangware Engineering Blueprint

Version: 6.5 (Living Document)
Status: Authoritative Reference
Last Updated: August 22, 2025

Changelog

2025-08-22: Removed “patch” terminology and workflows. Adopted changeset model aligned with interactive “review/approve” editing tools. Clarified commenting standards and change scopes.

2025-08-22: (prior) Controller refactor; ROI service; calibration helpers; centralized hotkeys; overlay feedback API; SIM tab; F11 start/stop; F7 SIM capture; F9 stop.

Earlier entries unchanged.

1. Purpose & Scope

This blueprint is the single source of truth for how Gangware is engineered, tested, released, and supported. It defines principles, architecture, structure, development workflow, testing/CI, configuration, observability, performance budgets, Windows constraints, asset rules, UI tokens, commenting standards, and change scopes for AI-assisted development.

2. Guiding Principles

Correctness before speed.

Determinism over flakiness (bounded waits, explicit gates, idempotency).

Make it observable (structured logs with correlation IDs).

Fail closed (on uncertainty, do the safe thing and log why).

Config over code (env/config toggles; safe defaults).

Small, reversible steps (short branches, focused reviews).

User empathy (errors suggest a resolution).

Respect the platform (Windows integrity/focus; no unsafe injection).

3. High-Level Architecture

Package-by-Feature inside src/gangware/.

Dependency Injection for services.

Anti-Corruption Layer: Windows/API specifics isolated in io/.

Event flow: Hotkey/overlay → queue → worker → controllers → feature modules.

Decision vs Actuation: intents produced → validated → safe OS input.

(Reference diagram unchanged from v6.4.)

4. Project Structure (Minimal Root + Package-by-Feature)
4.1 Minimal Root
gangware/
├─ README.md
├─ LICENSE
├─ pyproject.toml
├─ .gitignore
├─ .github/              # CI workflows, PR/issue templates, CODEOWNERS
└─ .aipolicy.yml         # Optional, small policy file (no patch mechanics)

4.2 Source Layout
src/gangware/
├─ features/
│  ├─ auto_sim/          # server join, armor swap
│  ├─ calibration/       # ROI and template capture
│  └─ combat/
├─ core/                 # hotkeys, worker, ROI, logging
├─ gui/                  # Qt overlay (feedback only)
├─ io/                   # Windows helpers (Win32)
└─ vision/               # image processing utilities

4.3 Supporting
assets/                  # bundled, read-only
docs/                    # ARCHITECTURE, RUNBOOK, TESTING, SECURITY, CONFIGURATION, adr/, ai/, changes/
configs/                 # schemas
tests/                   # cross-feature tests
logs/                    # runtime (not committed)


No .artifacts/patches/ folder. We do not store patch files; the tool’s approve-changes flow is our mechanism.

5. Development Standards (Python 3.11+)

Style/Lint: black(88), isort, ruff; Typing: mypy (strict on critical paths).

Type Checking: Use mypy daemon (`dmypy`) for fast incremental checking. Prefer architectural solutions over `# type: ignore` comments. Optional imports must use `Optional[Any]` variable annotations to prevent unreachable code warnings.

Logging: structured; INFO for transitions; DEBUG for ROI math/candidate rejections; artifacts on detection failures.

Module size: ≤1000 LOC (goal <500). Split by single responsibility.

Threading: never block GUI; heavy work in worker thread.

Placement rules: feature-specific code stays in its feature; shared logic in core/, io/, vision/, gui/.

6. Commenting & Documentation in Code (Authoritative)

Explain intent, constraints, safety—not history.

Prohibit: “we changed this”, dated notes, ticket IDs, author tags, comment-as-changelog.

If logic changes, update or remove nearby comments/docstrings in the same changeset.

Prefer concise function docstrings and targeted inline notes where reasoning isn’t obvious.

Link to docs/ or ADR titles when helpful (not external ticket URLs).

7. Change Scopes (no “patch” files; tool shows changesets you approve)
7.1 Small Changeset — Default

Keep each proposed changeset small and focused (rough guidance: ~≤3 files, ~≤200 lines).

Include/update tests when behavior changes.

No unrelated reformatting or drive-by renames.

Rationale: one-sentence intent + expected user-visible effect (if any).

7.2 Guided Refactor (when small isn’t enough)

Justified by: recurring defects in the same area, excessive module size/complexity, cross-file consistency fixes, or algorithmic need to meet performance budgets.

Delivered as a sequence of small, reviewable changesets—not a big-bang rewrite.

Preserve public behavior or provide shims + deprecation notes if behavior changes.

7.3 Replacement (rare)

New implementation behind a feature flag with an ADR documenting rationale, alternatives, migration, and rollback.

Prefer staged enablement; benchmark against performance budgets.

Guardrails (all scopes): respect Windows constraints; keep decision/actuation separation; never remove safety checks just to “make tests pass.”

8. Workflow & Versioning

Branching: trunk-based; short-lived feature/<name> branches.

Edits: the AI proposes changesets on your feature branch; you review/approve each one.

PRs: open a PR from your feature branch to main once ready.

Review rule: at least one human approval + all CI checks green.

Commits: Conventional Commits; Versioning: SemVer; Releases: tagged with PyInstaller artifacts.

9. Testing & CI/CD (Policy)

Unit: ROI math, config parsing, utilities.

Integration: VisionController (mock frames), InputController (dry-run).

E2E: overlay launch; start/stop; SIM flow beacons.

Performance: assert budgets via GW_VISION_PERF; track P50/P95.

CI gates: ruff, mypy, pytest(+coverage), pip-audit, Windows build (PyInstaller).

On failure: upload concise logs/artifacts to speed diagnosis.

10. Configuration & Secrets

Precedence: env > %APPDATA%/Gangware/config.ini > defaults (repo config/).

Secrets: never committed; use Windows Credential Manager.

Feature flags: document default, owner, rollback in config/feature_flags.yml.

11. Observability & Support

Logs: %APPDATA%/Gangware/logs/session-<ts>/ with gangware.log, health.json, environment.json.

Artifacts on failures: last_screenshot.png, last_template.png.

Perf exposure: VisionController provides timings; enable via env.

Support bundle: share the latest session folder for repro.

12. Performance Budgets

Overlay responsiveness < 50 ms.

Fast-path detection < 1.5 s.

Auto-SIM loop ≈ ≤400 ms typical.

Mouse settle ≤ 35 ms.

Join assessment tick 150 ms, timeout 15 s.

13. Platform Constraints (Windows)

DPI/Scaling: 100% preferred; override to “Application” if needed.

Windowing: Ark borderless windowed, fixed resolution, UI scale 1.0.

Focus: Same integrity level (Admin); disable overlays/Focus Assist.

Mouse: No Snap-To; no enhanced precision; no vendor macros.

Multi-monitor: constrain cursor to Ark monitor; hide taskbar on Ark monitor.

14. Asset & Template Governance

Bundled: assets/auto_sim/; Overrides: %APPDATA%/Gangware/templates/auto_sim.

Capture: tight crops; recapture after resolution/UI-scale/HDR changes; maintain synonyms for backward compatibility.

Confidence thresholds: documented in code comments + here.

15. Incident Response & Hotfix Protocol

Severity: S1 (blocking), S2 (feature broken), S3 (degraded).

Hotfix: branch from main → focused change(s) → tag patch release.

Postmortem: root cause, detection gap, guardrail added (store in docs/changes/).

16. Security & Privacy

No telemetry.

OS input only (no memory/code injection).

Redaction: logs avoid PII.

Appendix A — Authoritative UI Tokens

(Same as your v5.0 tokens; immutable for HUD/Calibration UI.)