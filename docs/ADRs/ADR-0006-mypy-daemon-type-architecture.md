# ADR-0006: MyPy Daemon and Type Architecture

**Status**: Accepted
**Date**: 2025-08-23
**Deciders**: Development Team

## Context

Gangware uses MyPy for static type checking, but faced issues with:
1. Slow type checking on large codebases during development
2. "Unreachable code" warnings from improper optional import typing
3. Overuse of `# type: ignore` comments creating technical debt

## Decision

We adopt **MyPy daemon (`dmypy`)** as the primary type checking tool and establish **architectural type solutions** over suppression comments.

### Type Checking Standards

1. **Use MyPy Daemon**: `dmypy start/check/stop` for fast incremental type checking
2. **Optional Import Pattern**: Use proper variable annotations for optional dependencies
3. **Architectural Solutions**: Fix type issues through better design, not `# type: ignore`
4. **Specific Exception Handling**: Use `ImportError` instead of broad `Exception` for imports

### Optional Import Pattern

**Before (problematic)**:
```python
try:
    import mss
except Exception:
    mss = None  # type: ignore  # ← Causes unreachable code warnings
```

**After (proper)**:
```python
mss: Optional[Any]  # ← Proper variable annotation
try:
    import mss
except ImportError:
    mss = None
```

## Consequences

### Positive
- Faster development feedback (incremental type checking)
- Cleaner codebase (fewer type suppressions)
- Better type safety (proper optional import handling)
- Technical debt reduction (architectural solutions vs workarounds)

### Negative
- Requires daemon management (start/stop)
- Additional setup documentation needed
- Team must learn proper optional import patterns

## Compliance

- **Blueprint Updated**: Development standards include daemon usage and architectural preference
- **TESTING.md Updated**: Documents `dmypy` commands and workflow
- **CI Integration**: Gates use `dmypy check` for fast feedback
- **Pattern Enforcement**: Code reviews enforce Optional[Any] pattern for optional imports

## Implementation Notes

Configuration in `mypy.ini` supports both daemon and traditional modes. The `.dmypy.json` file tracks daemon state and should be in `.gitignore`.

Key settings:
- `warn_unreachable = True`: Catches architectural issues
- `warn_unused_ignores = True`: Prevents ignore comment accumulation
- Third-party ignore patterns: For libraries without stubs
