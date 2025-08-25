# AutoSim Comprehensive Documentation

## Overview
AutoSim is Gangware's automated server joining system for ARK: Survival Evolved. It provides intelligent menu navigation, robust failure detection, and fast success detection.

## Architecture

### Core Components

**`loader.py`** - Main Orchestrator
- Manages watcher and automation lifecycle
- F11 toggle functionality (start/stop with overlay management)
- Periodic tick (200ms) for resume signal polling
- Server number storage and state coordination

**`menu_watch.py`** - Background Detection Engine
- Continuous menu detection and popup scanning
- Dual-signal detection: Template + Tier 3 modal heuristic
- Multi-ROI scanning support
- Suppression and cooldown management
- Fast dismissal with bounded navigation

**`automation.py`** - Workflow Controller
- Full server join sequence
- Success detection (2s consecutive no-menu)
- Retry logic with Back navigation
- BattlEye detection with multi-confidence

## Detection Systems

### Template Matching
- **Asset**: `assets/menus/connection_failed.jpg`
- **Algorithm**: OpenCV TM_CCOEFF_NORMED
- **Thresholds**: Strong (0.82), Soft (0.68)
- **Hysteresis**: Requires 2 consecutive soft hits or 1 strong hit

### Tier 3 Modal Heuristic (Template-less)
- **Algorithm**: Edge detection → morphological operations → contour analysis
- **Scoring**: Rectangularity + centrality + area fraction
- **Thresholds**: Strong (0.78), Soft (0.64)
- **Purpose**: Catch popups that don't match template exactly

### Multi-ROI Support
- **Default ROI**: Central region (0.20, 0.20, 0.80, 0.82) as fractions of window
- **Multi-ROI**: Via `GW_CF_ROIS` environment variable
- **Format**: `"x1,y1,x2,y2;x1,y1,x2,y2"` (semicolon or pipe separated)
- **Validation**: Coordinates clamped to [0.0, 1.0] range

## State Management

### Key State Variables
- **`autosim_menu`**: Current detected menu with confidence and timestamp
- **`autosim_join_window_until`**: End time for 20s fast scanning window
- **`autosim_cf_suppress_until`**: End time for 2.5s suppression after Enter
- **`autosim_resume_from`**: Signal menu name for automation resume

### State Flow
1. **Join Game Click** → Set join window (20s) → Begin fast scanning
2. **Popup Detected** → Press Enter → Set suppression (2.5s) → Navigate back
3. **Menu Reached** → Set resume signal → Loader picks up and continues
4. **Success/Failure** → Clear all state → Show/hide overlay

## Timing & Thresholds

### Critical Timings
- **Success Detection**: 2 seconds consecutive no-menu
- **Join Timeout**: 15 seconds maximum per attempt
- **Join Window**: 20 seconds fast scanning after Join Game click
- **Suppression**: 2.5 seconds after Enter pressed
- **Cooldown**: 2 seconds between popup detections

### Scan Rates
- **Normal**: 250ms menu detection interval
- **Join Window**: ~80-100ms aggressive scanning
- **Resume Polling**: 200ms loader tick rate

## Environment Configuration

### Debug Variables
```bash
# Template detection score logging
GW_CF_DEBUG=1

# Modal heuristic score logging
GW_MODAL_DEBUG=1

# Multiple ROI regions (fractional window coordinates)
GW_CF_ROIS="0.15,0.15,0.85,0.85;0.10,0.10,0.90,0.90"
```

### ROI Format Examples
```bash
# Single large ROI
GW_CF_ROIS="0.1,0.1,0.9,0.9"

# Two ROIs (center + wider)
GW_CF_ROIS="0.2,0.2,0.8,0.8;0.1,0.15,0.9,0.85"

# Three ROIs with pipe separator
GW_CF_ROIS="0.2,0.2,0.8,0.8|0.1,0.1,0.5,0.5|0.5,0.5,0.9,0.9"
```

## User Interface

### F11 Toggle Behavior
- **When Overlay Visible**: Start AutoSim → Hide overlay
- **When AutoSim Running**: Stop AutoSim → Show overlay
- **Proper Cleanup**: Qt timer management and overlay state sync

### Status Feedback
- **Starting**: "Starting AutoSim workflow..."
- **Progress**: "Clicking Main Menu button", "Looking for BattlEye symbol"
- **Success**: "Successfully joined server!"
- **Failure**: "Max retries reached - unable to join server"
- **Resume**: Automatic continuation from detected menu

## Failure Handling

### Connection_Failed Popup Response
1. **Detection**: Template or modal heuristic triggers
2. **Dismissal**: Press Enter twice for reliability
3. **Precise Clicks**: Use detected rectangle coordinates for fallback
4. **Navigation**: Bounded Back clicks (max 2) with menu verification
5. **Verification**: Ensure correct menu reached before resume
6. **Suppression**: Prevent re-detection for 2.5s

### Bounded Navigation
- **Max Attempts**: 2 Back button clicks
- **Verification**: Check menu after each click
- **Timeout**: 1.5s max for menu confirmation
- **Fallback**: If navigation fails, automation handles appropriately

## Success Detection

### Algorithm
1. **Monitor**: Continuously check for menu presence after Join Game
2. **Reset**: Any menu detection resets consecutive timer
3. **Track**: Count consecutive time without menu detection
4. **Trigger**: 2 seconds consecutive no-menu → SUCCESS
5. **Logging**: Progress updates and final success message

### Fast Join Handling
- Works even if no menu ever detected after Join Game click
- Starts timing immediately when menus disappear
- Robust against intermittent loading screens

## Retry Logic

### Attempt Sequence
1. **First Failure**: Navigate back to Select Game → Retry (attempt 2/4)
2. **Second Failure**: Navigate back to Select Game → Retry (attempt 3/4)
3. **Third Failure**: Navigate back to Select Game → Retry (attempt 4/4)
4. **Final Failure**: Max retries reached → Stop with error message

### Navigation Recovery
- **Current Menu Detection**: Uses watcher state when available
- **Fallback Detection**: Template matching if watcher unavailable
- **Preference**: SELECT_GAME over MAIN_MENU to avoid false positives
- **Timeout**: 15s maximum per join attempt

## Troubleshooting

### Common Issues
- **No Detection**: Check template asset exists, verify ROI covers popup area
- **False Positives**: Use debug logging to check scores, adjust ROI
- **Navigation Issues**: Verify Back button coordinates, check menu detection
- **F11 Not Working**: Ensure admin privileges match ARK's integrity level

### Debug Workflow
1. **Enable Logging**: Set `GW_CF_DEBUG=1` and `GW_MODAL_DEBUG=1`
2. **Check Scores**: Watch log output during join attempts
3. **Adjust ROI**: Use `GW_CF_ROIS` if default region misses popups
4. **Verify Assets**: Ensure `connection_failed.jpg` template exists
5. **Test Multi-ROI**: Try multiple regions if single ROI insufficient

### Performance Tuning
- **ROI Size**: Smaller ROIs = faster detection, larger ROIs = better coverage
- **Thresholds**: Lower = more sensitive, higher = more specific
- **Multiple ROIs**: Balance between coverage and performance impact
- **Debug Logging**: Disable in production for better performance

## Integration Points

### MenuDetector Integration
- **Menu Recognition**: Uses same template matching system
- **State Sharing**: Common menu state for watcher and automation
- **Coordinate System**: Shared config for click coordinates

### Input Controller Integration
- **Key Presses**: Standardized "enter" key handling
- **Mouse Clicks**: Precise coordinate clicking with fallbacks
- **ARK Foreground**: Ensures game focus before input

### Overlay Integration
- **Status Updates**: Real-time feedback to UI
- **Toggle Control**: F11 hotkey management
- **Visibility Sync**: Proper show/hide coordination

## Future Enhancements

### Potential Improvements
- **Adaptive Thresholds**: Dynamic confidence adjustment based on success rate
- **Template Variants**: Multiple Connection_Failed templates for different UI scales
- **Machine Learning**: Pattern recognition for non-template popup detection
- **Network Awareness**: Integration with connection quality metrics

### Maintenance Considerations
- **Template Updates**: Monitor for ARK UI changes requiring new assets
- **Threshold Tuning**: Periodic review of detection confidence levels
- **Performance Monitoring**: Track detection speed and accuracy metrics
- **User Feedback**: Incorporate reports of false positives/negatives
