# ADR-0009: Adopt Package-by-Feature Structure and Remove Legacy Folders

Status: Accepted
Date: 2025-08-25
Deciders: Gangware Maintainers

## Context

The v6.5 Engineering Blueprint mandates a Package-by-Feature layout under `src/gangware/` and the removal of the legacy `controllers/` pattern. Some legacy directories and loose module paths remained in the repository:

- `src/gangware/controllers/` (empty)
- `src/gangware/macros/` (empty; canonical macros reside in `features/combat/macros/`)
- `src/gangware/features/calibration/` (empty; calibration consolidated in `features/debug/`)
- A duplicate/loose module path `features/search/search_service.py` (empty) while the canonical implementation lives in `features/combat/search_service.py` as defined in the blueprint.

This residual structure created confusion and violated the blueprint’s "Package-by-Feature" guidance and "no loose modules" preference.

## Decision

1. Remove legacy/empty directories:
   - Deleted `src/gangware/controllers/`
   - Deleted `src/gangware/macros/`
   - Deleted `src/gangware/features/calibration/`

2. Consolidate search under the combat feature:
   - Kept `src/gangware/features/combat/search_service.py` as the canonical implementation.
   - Added a temporary deprecation shim at `src/gangware/features/search/search_service.py` that re-exports the canonical class and emits a `DeprecationWarning` guiding callers to migrate.

3. Align ADR location with the blueprint’s expectation (`docs/adr/`).

## Rationale

- Aligns the project layout with the authoritative blueprint (v6.5).
- Reduces developer confusion by removing empty/legacy directories.
- Preserves backward compatibility with a clear, time-bounded deprecation path for the search service import location.
- Supports future feature isolation, testability, and observability by keeping feature code inside its package.

## Alternatives Considered

- Retain legacy directories for historical reference: rejected. The blueprint prohibits comment-as-changelog and legacy structure; history is preserved in Git.
- Hard break on `features/search/` imports without a shim: rejected. Shim allows a short migration period without breaking downstream code.

## Consequences

- Cleaner, deterministic imports and discoverability.
- Any remaining imports from `gangware.features.search.search_service` will continue to function but log a `DeprecationWarning`.
- New work must place feature code under the appropriate feature package; shared utilities remain under `core/`, `io/`, `vision/`, `gui/`.

## Migration Plan

- Immediately prefer `from gangware.features.combat.search_service import SearchService`.
- Treat the shim as temporary; remove `features/search/search_service.py` once internal/external callers are migrated.
- Ensure CI/log review flags deprecation warnings during the migration window.

## Rollback Plan

- Recreate removed directories only if a critical dependency emerges (unlikely, given they were empty).
- The deprecation shim provides a non-breaking path back; if necessary, keep it longer than planned.

## Related

- Blueprint v6.5: Package-by-Feature layout; removal of `controllers/` pattern; calibration consolidated under `features/debug/`.
- Debug/Calibration: `src/gangware/features/debug/`.
- Combat macros: `src/gangware/features/combat/macros/`.

## Notes on Commenting & Documentation

- Code comments must follow the blueprint: explain intent/constraints/safety; no dated notes, author tags, ticket IDs, or comment-as-changelog.
- This ADR documents the structural decision; subsequent PRs should remove any legacy references and update imports accordingly.
