# Architecture Decision Records (ADRs)

This directory stores concise decisions with context and consequences.

- ADR-0001: Package-by-Feature structure in `src/gangware` with `features/`, `core/`, `gui/`, `io/`, `vision/`
- ADR-0002: Windows-specific APIs isolated in `core/win32` and `io/win`
- ADR-0003: Observability strategy with session logs and artifacts
- ADR-0004: Global hotkey hook extraction and centralized bindings
- ADR-0005: Auto SIM package consolidation (`features/auto_sim/`), shim removal, package exports
- ADR-0006: MyPy daemon and type architecture (architectural solutions over suppressions)
