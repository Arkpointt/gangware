# ADR-0011: AutoSim Retry Logic Fix

**Status:** Accepted  
**Date:** 2025-08-25  
**Deciders:** Gangware Maintainers

## Context

AutoSim had critical bugs in its retry logic that caused infinite retry loops and improper timeout enforcement:

1. **Infinite Retry Loop**: Retry counter exceeded maximum limits (showing attempt 5/4, 6/4, 7/4, 8/4, etc.)
2. **Missing Timeout Enforcement**: After clicking "Join Game", the system wasn't properly waiting 15 seconds before timing out
3. **Improper Retry Counter Management**: Connection failures were inappropriately incrementing retry counts during error recovery

### Root Causes Identified

1. **`_handle_connection_failed()` bypassed retry limits**: Called `execute_from_menu(detected_menu, server_number, retry_count + 1)` without checking if `retry_count` was already at maximum
2. **`_monitor_join_result()` lacked timeout enforcement**: Missing proper 15-second timeout handling after "Join Game" click
3. **Navigation methods missing required parameters**: Helper methods called without required `server_number` and `retry_count` arguments

## Decision

### 1. Fixed Retry Counter Management

**Before (Broken):**
```python
def _handle_connection_failed(self, server_number: str, retry_count: int) -> bool:
    # ... popup handling ...
    # PROBLEM: Always increments retry_count, bypassing max limit check
    return self.execute_from_menu(detected_menu, server_number, retry_count + 1)
```

**After (Fixed):**
```python
def _handle_connection_failed(self, server_number: str, retry_count: int) -> bool:
    # Check retry limit BEFORE proceeding
    if retry_count >= self.max_retries:
        self._logger.warning("AutoSim: Max retries (%d) reached while handling connection failure. Aborting.", self.max_retries)
        return False
    
    # Handle popup without incrementing retry count
    if not self._handle_connection_failed_popup():
        return False
    
    # Navigate back with SAME retry count (not incremented)
    return self._navigate_back_to_select_game(server_number, retry_count)
```

### 2. Enhanced Timeout Enforcement

**Added proper 15-second timeout logic in `_monitor_join_result()`:**
- Check retry limits before any navigation attempts
- Proper back navigation with retry counter management
- Clear logging of timeout events

### 3. Refactored Helper Methods

**Created dedicated helper methods:**
- `_handle_connection_failed_popup()`: Handles popup dismissal cleanly
- `_navigate_back_to_select_game()`: Manages back navigation with proper retry counting

**Fixed method signatures:** All navigation methods now properly accept required `server_number` and `retry_count` parameters.

## Rationale

### Why This Fix Was Critical

1. **Infinite loops broke AutoSim**: Users couldn't rely on AutoSim to eventually give up and stop trying
2. **Resource waste**: Infinite retries consumed CPU and prevented other operations
3. **Poor user experience**: No clear feedback when maximum retries should have been reached

### Why This Approach

1. **Retry counter integrity**: Connection failures are temporary recoverable errors, not reasons to increment the main retry counter
2. **Clear separation of concerns**: Helper methods handle specific tasks with proper parameter passing
3. **Proper timeout enforcement**: 15-second timeout is a core requirement for user predictability

## Alternatives Considered

1. **Quick fix approach**: Simply adding retry limit checks without refactoring
   - **Rejected**: Would leave underlying architectural issues unresolved

2. **Complete rewrite of retry logic**: Starting fresh with new approach
   - **Rejected**: Existing logic was sound, just needed proper bounds checking

3. **Increasing retry limits**: Making max_retries higher to mask the problem
   - **Rejected**: Doesn't solve the infinite loop, just makes it longer

## Consequences

### Positive
- **AutoSim now respects retry limits**: Will properly stop at 4/4 attempts
- **Proper timeout behavior**: 15-second timeout after "Join Game" click works correctly
- **Better error recovery**: Connection failures handled gracefully without retry counter corruption
- **Improved observability**: Clear logging of retry attempts and timeout events

### Negative
- **None identified**: This was a pure bug fix with no breaking changes

## Implementation Details

### Files Modified
- `src/gangware/features/autosim/automation.py`: Core retry logic fixes

### Key Behavioral Changes

**Before:**
- Retry counter could exceed maximum (5/4, 6/4, 7/4, etc.)
- No timeout enforcement after "Join Game" click
- Connection failures immediately restarted workflow with incremented retry count

**After:**
- Retry counter respects maximum (stops at 4/4)
- Proper 15-second timeout after "Join Game" click
- Connection failures handled gracefully without inappropriate retry increments

### Testing
- All existing tests pass
- Manual verification shows proper retry limit enforcement
- Timeout behavior verified through log analysis

## Rollback Plan

If issues arise:
1. Revert commit `8cd7baf` 
2. Previous retry logic will be restored
3. Would need to accept infinite retry loop behavior until alternative fix developed

## References

- Previous retry logic issues documented in user logs showing attempts 5/4, 6/4, 7/4, 8/4
- AutoSim architecture documented in Blueprint v6.5
- ADR-0010: AutoSim Detection Strategy and State Model
