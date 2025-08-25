# Testing Strategy

Scope and goals
- Validate correctness of automation logic across Windows, PyQt6, and OpenCV.
- Keep tests fast, deterministic, and isolated from user environment.
- Prefer unit tests for logic; use integration/E2E sparingly with clear guardrails.

Test types
- Unit: ROI math, config parsing, VK normalization, helper utilities.
- Integration: VisionController with mocked frames, InputController dry-run.
- E2E: Overlay boot and basic flow; SIM workflow validation with heavy I/O stubbed/skipped when not available.
- Performance: Enforced via environment flags (e.g., GW_VISION_PERF) with budget asserts.

## Running tests

```powershell
# Quick run
pytest -q

# Verbose with traceback
python -m pytest tests/ -v

# Single test file
pytest tests/test_smoke.py -q

# Filter by keyword
# Filter by keyword
pytest -k "debug and not slow" -q

# Re-run last failures fast
pytest --last-failed -q

# Stop after first failure
pytest -x -q

# Show slowest tests
pytest --durations=10 -q

# Test specific packages after refactoring
pytest src/gangware/features/debug/ -v
pytest src/gangware/features/combat/ -v
pytest src/gangware/io/ -v
pytest src/gangware/vision/ -v
```

**Package Structure Testing:**
After the Package-by-Feature refactoring, verify imports work correctly:
```python
# Test feature package imports
from gangware.features.debug import CalibrationService
from gangware.features.combat import ArmorMatcher, SearchService

# Test supporting package imports
from gangware.io import InputController
from gangware.vision import VisionController
```

## AutoSim-specific tests

- Success detection
	- Mock `_detect_any_menu()` to return False for ≥2 seconds in `_monitor_join_result` and assert success is logged/returned.
	- Edge case: return False immediately after Join (fast join) to verify the consecutive no-menu logic triggers success.

- Connection_Failed handling
	- Template detection: Provide a small synthetic frame containing `connection_failed.jpg` region and assert watcher triggers Enter + Back.
	- Modal detection: Create synthetic frame with centered modal popup and verify Tier 3 heuristic triggers.
	- Multi-ROI: Set GW_CF_ROIS="0.1,0.1,0.5,0.5;0.5,0.5,0.9,0.9" and verify detection works in both regions.
	- Gate scanning by setting `autosim_join_window_until = time.time() + 20` in `StateManager` and ensure detection only runs within that window.
	- Suppression: After Enter pressed, verify `autosim_cf_suppress_until` prevents re-detection for 2.5s.
	- Bounded navigation: Verify watcher-level Back clicks are limited to max 2 attempts with menu confirmation.

- F11 toggle functionality
	- Test toggle behavior: start AutoSim (hide overlay) → F11 → stop AutoSim (show overlay)
	- Verify proper Qt timer cleanup and overlay visibility management.

- Resume functionality
	- Set `autosim_resume_from = "SELECT_GAME"` and verify loader.tick() resumes automation from that menu.

- Retry path
	- Simulate missing BattlEye detection and confirm Back navigation and re-entry from Select Game.

Note: Integration/E2E around Ark should be guarded/skipped; prefer mocked frames and dry-run InputController.

GUI/Windows specifics
- Run GUI-related tests headlessly when possible:
	```powershell
	$env:QT_QPA_PLATFORM = "offscreen"; pytest -q
	```
- Avoid requiring Administrator; if a test needs elevated input hooks, mark/skip with a clear reason.
- Tests must not depend on Ark being open; use stubs/mocks and skip when unavailable.

Skipping optional dependencies
- Use conditional imports where heavy/optional libs may be missing:
	```python
	cv2 = pytest.importorskip("cv2", reason="OpenCV required for this test")
	```

## Linting and types

```powershell
ruff check src/
# Use mypy daemon for fast incremental type checking
dmypy start  # Start daemon once
dmypy check src/  # Fast incremental checks
dmypy stop  # Stop daemon when done

# Or traditional one-shot checking
mypy src/

# Optional formatting
black --check src/ tests/
```

## Coverage (optional)
If `pytest-cov` is installed:
```powershell
pytest --cov=src/gangware --cov-report=term-missing -q
```

## Test data and artifacts
- Tests shouldn’t write to repo; use `tmp_path` for any files.
- Artifacts created during failures (images/logs) should go to temp dirs and be cleaned or ignored.

## Adding tests
- Location: `tests/` with `test_*.py` naming; functions `test_*`.
- Import from the installed package path (conftest adds project root and `src/`):
	```python
	from gangware.controllers.vision import VisionController
	```
- Prefer pytest fixtures; common setup goes in `tests/conftest.py`.
- Keep time-based waits bounded; use dependency injection to avoid real sleeps.
- For E2E, guard with markers/keywords and keep within a few seconds runtime.

## CI expectations
- Tests should pass on a clean Windows runner with Python 3.11.
- No network calls, no admin-only behavior, deterministic seeds where applicable.
