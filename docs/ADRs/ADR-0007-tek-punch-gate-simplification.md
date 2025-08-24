# ADR-0007: Tek Punch Gate Simplification

**Status:** Accepted
**Date:** 2025-08-23
**Deciders:** User, GitHub Copilot

## Context

The tek punch macro (Shift+R hotkey) had evolved into a complex system with multiple configuration options for buffering, retrigger gaps, shift key detection, and mixed timing scenarios. This complexity was causing:

1. **Inconsistent behavior** during rapid R key spam
2. **Configuration confusion** with many unused settings
3. **Maintenance overhead** from complex state management
4. **User experience issues** where right-click would activate too early or inconsistently

Analysis of actual usage logs showed that a simple gate mechanism was sufficient and more reliable than complex buffering logic.

## Decision

We will **simplify the tek punch system to use a pure gate approach**:

### Removed Complexity
- `tek_punch_enable_buffer` and related buffering logic
- `tek_punch_min_retrigger_gap_ms` complex retrigger timing
- `tek_punch_respect_user_shift` and shift key detection
- `tek_punch_send_r_when_respecting_shift` conditional logic
- `tek_punch_mixed_*` timing variants for different armor types
- Low-level keyboard hook backup interception (primary RegisterHotKey works reliably)

### Simplified Implementation
- **Gate Logic**: Block all Shift+R presses while tek punch is running + 500ms cooldown after completion
- **Consistent Timing**: Single set of timing values that work reliably (120ms pre-delay, 800ms RMB hold, 180ms post-delay)
- **Predictable Behavior**: Always send Shift+R followed by RMB sequence - no conditional logic
- **Clean Configuration**: Only essential timing settings remain

### Key Configuration Changes
```ini
# Removed settings:
# tek_punch_respect_user_shift
# tek_punch_send_shift_r
# tek_punch_send_r_when_respecting_shift
# tek_punch_enable_buffer
# tek_punch_min_retrigger_gap_ms
# tek_punch_mixed_pre_rmb_delay_ms
# tek_punch_mixed_rmb_hold_ms
# tek_punch_mixed_post_rmb_settle_ms

# Simplified to essential timing only:
tek_punch_pre_rmb_delay_ms=120
tek_punch_rmb_hold_ms=800
tek_punch_post_rmb_settle_ms=180
```

## Consequences

### Positive
- **Reliable blocking** of rapid R key spam preventing early right-click activation
- **Consistent 1130ms execution time** with precise timing
- **Reduced configuration complexity** - easier for users to understand and maintain
- **Simplified codebase** - removed ~100 lines of complex logic
- **Better user experience** - predictable behavior during combat

### Negative
- **Less flexibility** for edge cases or different armor configurations
- **Fixed 500ms cooldown** may be too long/short for some users (but is configurable in code)

### Monitoring
The simplified system provides excellent logging:
- `tek_gate: ignored (busy/pending)` when blocking during execution
- `tek_gate: ignored (cooldown Xms remaining)` when in cooldown
- `tek_gate: start tek_punch` when allowing execution
- `tek_punch: RMB held for X ms (target=Y)` for timing validation

## Implementation Notes

The gate is implemented in `HotkeyManager._on_hotkey_shift_r()` with a simple busy check + timestamp-based cooldown. The primary RegisterHotKey interception has proven reliable enough that backup low-level hooks are unnecessary.

This decision aligns with the blueprint principle of "determinism over flakiness" and "make it observable."
