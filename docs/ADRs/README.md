# Architecture Decision Records (ADRs)

This directory stores concise decisions with context and consequences.

- ADR-0001: Package-by-Feature structure in `src/gangware` with `features/`, `core/`, `gui/`, `io/`, `vision/`
- ADR-0002: Windows-specific APIs isolated in `core/win32` and `io/win`
- ADR-0003: Observability strategy with session logs and artifacts
- ADR-0004: Global hotkey hook extraction and centralized bindings
- ADR-0005: Controllers elimination and Package-by-Feature consolidation (Aug 2025)
- ADR-0006: MyPy daemon and type architecture (architectural solutions over suppressions)

**Recent Implementation Notes:**
- Controllers directory eliminated: functionality moved to appropriate feature/core packages
- Calibration consolidated into `features/debug/` with backward compatibility
- Search functionality moved to `features/combat/` as armor search capability
- All import paths updated to reflect new package structure
