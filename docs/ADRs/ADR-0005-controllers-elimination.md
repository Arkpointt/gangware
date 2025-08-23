# ADR-0005: Controllers Elimination and Package-by-Feature Consolidation

**Status:** Accepted (August 2025)
**Context:** Package-by-Feature architecture implementation

## Problem

The `controllers/` directory created an artificial layer that didn't align with Package-by-Feature principles. Controllers contained functionality that belonged in specific feature packages or core utilities, creating unnecessary indirection and violating cohesion principles.

## Decision

**Eliminate the `controllers/` directory** and redistribute functionality to appropriate packages:

- `controllers/armor_matcher.py` → `features/combat/armor_matcher.py` (armor-specific functionality)
- `controllers/controls.py` → `io/controls.py` (Windows input automation)
- `controllers/vision.py` → `vision/controller.py` (vision orchestration)

**Consolidate related functionality:**
- Move search capability from standalone `features/search/` into `features/combat/`
- Merge calibration from `features/calibration/` into `features/debug/`
- Remove duplicate/obsolete files in `core/` (calibration_old, task_management_new, etc.)

## Consequences

**Positive:**
- ✅ True Package-by-Feature: related functionality colocated
- ✅ Cleaner import paths and dependencies
- ✅ Eliminates artificial controller layer
- ✅ Better feature cohesion (armor + search together)
- ✅ Reduced cognitive overhead from fewer top-level packages

**Trade-offs:**
- 📋 Temporary import path updates required across codebase
- 📋 Package exports need updating for backward compatibility

## Implementation

- [x] Move controller files to appropriate packages
- [x] Update all import references in codebase
- [x] Update package `__init__.py` exports
- [x] Provide backward compatibility where needed
- [x] Clean up duplicate/obsolete files
- [x] Verify all tests pass

## Result

Final structure aligns perfectly with blueprint Package-by-Feature architecture:
```
features/
├─ debug/      # calibration + ROI/template capture
└─ combat/     # armor + search + combat actions
```

Supporting packages contain only shared utilities, no feature-specific logic.
