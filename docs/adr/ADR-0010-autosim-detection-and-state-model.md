# ADR-0010: AutoSim Detection Strategy and State Model

Status: Accepted
Date: 2025-08-25
Deciders: Gangware Maintainers

## Context

AutoSim performs automated server joining for Ark using a background watcher and a foreground automation workflow. The v6.5 blueprint defines:

- Dual-signal detection of Connection_Failed (template + Tier 3 modal heuristic)
- Multi-ROI support via `GW_CF_ROIS`
- State variables to coordinate watcher and automation: `autosim_menu`, `autosim_join_window_until`, `autosim_cf_suppress_until`, `autosim_resume_from`
- Success condition: 2 seconds of consecutive no-menu detection after Join
- Timings: 15s attempt timeout; 20s post-Join gated scan window; 2.5s suppression after Enter

## Decision

- Implemented dual detection in the watcher with hysteresis and score logging, selecting the best signal each frame.
- Implemented multi-ROI parsing and clamping; default ROI centered.
- The automation sets `autosim_join_window_until` on Join click. The watcher uses this to increase scan cadence.
- Both watcher and automation respect/emit `autosim_cf_suppress_until` after Enter to prevent re-detection.
- The watcher signals `autosim_resume_from` when landing on a safe resume menu; the loader polls and resumes.
- Success detection: In automation, track 2.0s of no-menu consecutively; reset on any menu detection.
- Lifecycle hygiene: loader clears autosim flags on start/stop to prevent stale state.

## Rationale

- Robust detection covers both template-bound and template-less popups.
- Multi-ROI and gated scanning improve performance and reliability.
- Shared state ensures clean handoff between watcher and automation.
- Success detection works for both fast joins (no intermediate menus) and slower joins.

## Alternatives Considered

- Template-only detection: insufficient under UI variation.
- Continuous high-rate scanning: higher CPU without gating.
- Single-shot resume: replaced by a polling/timer approach to tolerate timing variance.

## Consequences

- Clear observability in logs; debug env flags (`GW_CF_DEBUG`, `GW_MODAL_DEBUG`) available.
- Deterministic behavior across retries; bounded navigation and suppression reduce flakiness.

## Rollback Plan

- Disable modal heuristic via feature flag if a severe regression is observed (not currently present; would require code change).

## References

- docs/autosim-comprehensive.md
- docs/blueprint.md (AutoSim Architecture)
