```markdown
# ADR-0005: Auto SIM Package Consolidation

## Status
Accepted (2025-08-22)

## Context
Historically, `features/auto_sim.py` acted as a public shim re-exporting `AutoSimRunner` while implementation lived in multiple modules. The blueprint mandates Package-by-Feature with a single feature package directory per feature.

## Decision
- Consolidate Auto SIM into `src/gangware/features/auto_sim/` as the canonical package.
- Expose public API via `__init__.py` with:
  - `AutoSimRunner`
  - `AutoSimFeature = AutoSimRunner` (back-compat alias)
- Remove the top-level shim `src/gangware/features/auto_sim.py`.
- Update tests and docs to reference the package path, not the shim file.

## Consequences
- Imports remain stable: `from gangware.features.auto_sim import AutoSimRunner` (and `AutoSimFeature`).
- Cleaner structure, easier maintenance, and adherence to blueprint.
- Any references to the old file path are updated in docs.

## Alternatives Considered
- Keep the shim: rejected to avoid duplication and drift.

```
