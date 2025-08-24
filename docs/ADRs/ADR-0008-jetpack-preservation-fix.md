# ADR-0008: Jetpack Preservation Fix

**Status:** Accepted
**Date:** 2025-08-23
**Deciders:** User, GitHub Copilot

## Context

After implementing the tek punch gate simplification (ADR-0007), users reported that using tek punch while holding Shift for jetpack would turn off the jetpack. This was because the tek punch macro was sending `Shift+R` via the input controller, which would:

1. Release the user's held Shift key
2. Press Shift+R combination
3. Release Shift+R
4. Break the user's jetpack state

The jetpack in ARK requires continuous Shift key hold to remain active, so any interruption to the Shift key state would disable it.

## Decision

**Modify the tek punch macro to send only the R key instead of Shift+R when triggered via hotkey.**

### Root Cause Analysis
The issue occurred because:
- User holds Shift for jetpack
- User presses R to trigger tek punch
- Global hotkey handler detects Shift+R and triggers macro
- Macro sends `input_controller.hotkey('shift', 'r')` which interrupts the user's held Shift
- Jetpack turns off due to Shift interruption

### Solution Implementation
Change the tek punch macro from:
```python
# Old - breaks jetpack
input_controller.hotkey('shift', 'r')
```

To:
```python
# New - preserves jetpack
input_controller.press_key('r')
```

### Rationale
Since the macro is only triggered when the global hotkey handler detects Shift+R, we know:
1. The user is already holding Shift (or the hotkey wouldn't have triggered)
2. We only need to send the R key to activate tek punch in ARK
3. Preserving the user's Shift state maintains jetpack functionality

## Consequences

### Positive
- **Jetpack preserved** during tek punch execution
- **Better user experience** - no unexpected jetpack deactivation
- **Simpler input sequence** - only one key press instead of key combination
- **No timing issues** from Shift key state management

### Negative
- **Slight change in behavior** - macro now assumes user is holding Shift
- **Dependency on hotkey detection** - relies on global hotkey working correctly

### Edge Cases Handled
- **Non-jetpack usage**: Still works fine - sending R while Shift is held has same effect as Shift+R
- **Hotkey malfunction**: If somehow triggered without Shift held, R key alone won't activate tek punch (fail-safe)

## Implementation Details

**File Modified:** `src/gangware/features/combat/macros/combat.py`
**Function:** `execute_tek_punch()`
**Lines Changed:** 74-76

```python
# Before
logger.debug("tek_punch: sending Shift+R")
input_controller.hotkey('shift', 'r')

# After
logger.debug("tek_punch: sending R (preserving user's Shift state)")
input_controller.press_key('r')
```

## Testing

Verified behavior:
1. ✅ Hold Shift for jetpack
2. ✅ Press R to trigger tek punch
3. ✅ Jetpack remains active during and after tek punch
4. ✅ Tek punch executes correctly (RMB hold sequence works)
5. ✅ Gate logic still prevents spam

## Related ADRs

- **ADR-0007**: Tek Punch Gate Simplification - established the foundation gate logic
- This ADR builds on that work to address the jetpack preservation issue

This change maintains the reliability improvements from ADR-0007 while fixing the user experience regression with jetpack usage.
