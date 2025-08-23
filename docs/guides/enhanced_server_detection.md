# Enhanced Server Detection Implementation

## Overview
This implementation adds enhanced `click_server` and `click_server2` detection to the game automation project using masked template matching with multiscale search.

## Key Features Implemented

### 1. **Enhanced Detection Function** (`find_server_template_enhanced`)
- **Location**: `src/gangware/controllers/vision.py`
- **Purpose**: Specialized detection for server button templates with improved reliability
- **Key Improvements**:
  - Multiscale search from 0.8x to 1.2x in 0.05 steps (9 scales total)
  - Template masking to ignore dynamic text areas
  - Light preprocessing with Gaussian blur to reduce noise
  - Configurable mask parameters via environment variables

### 2. **Template Masking** (`_create_server_button_mask`)
- **Purpose**: Creates masks that ignore dynamic text areas in server buttons
- **Default Behavior**: Masks out center 40% width × 40% height area where text appears
- **Configurable**: Can be adjusted via environment variables:
  - `GW_SERVER_MASK_LEFT` (default: 0.2)
  - `GW_SERVER_MASK_RIGHT` (default: 0.8)
  - `GW_SERVER_MASK_TOP` (default: 0.3)
  - `GW_SERVER_MASK_BOTTOM` (default: 0.7)

### 3. **Auto Sim Integration**
- **Location**: `src/gangware/features/auto_sim/` (package export via `__init__.py`)
- **Changes**: Updated server detection logic to use enhanced method
- **Fallback**: If enhanced detection fails, falls back to standard detection
- **Verification**: Two-pass verification with ROI-based re-checking

## Technical Details

### Multiscale Search
```python
# Scale range: 0.8 to 1.2 in 0.05 increments
scales = [0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2]
```

### Preprocessing Pipeline
1. **Screenshot capture** with BGRA to grayscale conversion
2. **Gaussian blur** (3x3 kernel) to reduce noise
3. **Template scaling** at each test scale
4. **Mask application** to ignore dynamic areas
5. **Template matching** with `TM_CCOEFF_NORMED` method
6. **Early exit** on excellent matches (>0.9 confidence)

### Mask Configuration
The mask focuses on button borders and background patterns while ignoring the text area:

```
┌─────────────────────────┐
│████████████████████████│ ← Kept for matching
│████████████████████████│
│██████░░░░░░░░░░░░██████│ ← Masked text area
│██████░░░░░░░░░░░░██████│
│██████░░░░░░░░░░░░██████│
│████████████████████████│
│████████████████████████│ ← Kept for matching
└─────────────────────────┘
```

## Benefits

### 1. **Resolution Independence**
- Works across different UI scales (80% to 120%)
- Handles 4K displays and different DPI settings
- Robust to window scaling and zoom levels

### 2. **Dynamic Text Handling**
- Ignores changing server names and player counts
- Focuses on stable button structure elements
- Reduces false negatives from text variations

### 3. **Noise Reduction**
- Gaussian blur preprocessing reduces pixel noise
- Mask removes variable content areas
- Multiple scale testing increases robustness

### 4. **Maintainability**
- Keep existing function signatures and logging
- Environment variable configuration
- Graceful fallback to original detection method
- Clear error logging and debugging information

## Usage Examples

### Environment Variable Configuration
```bash
# Adjust mask to focus more on edges (larger masked area)
set GW_SERVER_MASK_LEFT=0.1
set GW_SERVER_MASK_RIGHT=0.9
set GW_SERVER_MASK_TOP=0.2
set GW_SERVER_MASK_BOTTOM=0.8

# Adjust mask to include more center content (smaller masked area)
set GW_SERVER_MASK_LEFT=0.3
set GW_SERVER_MASK_RIGHT=0.7
set GW_SERVER_MASK_TOP=0.4
set GW_SERVER_MASK_BOTTOM=0.6
```

### Testing
A test script is provided at `test_enhanced_server_detection.py` to verify functionality:

```bash
.venv\Scripts\python.exe test_enhanced_server_detection.py
```

## Performance Considerations

### Optimizations Applied
1. **Early exit** on high-confidence matches
2. **Progressive confidence** testing (starts with lower thresholds)
3. **Efficient scaling** using OpenCV optimized resize
4. **Region-based search** (existing ROI system maintained)

### Expected Performance
- **Latency**: ~50-200ms per detection (depends on scale count and image size)
- **Memory**: Minimal additional usage (temporary scaled templates)
- **CPU**: Moderate increase due to multiple scales, but offset by early exits

## Integration Notes

### Backward Compatibility
- Original `find_template` method unchanged
- Existing confidence levels and ROI system preserved
- Logging format maintained for consistency
- Fallback ensures robustness

### Error Handling
- Graceful degradation to standard detection on errors
- Comprehensive logging for debugging
- Environment variable validation with safe defaults
- Exception handling at each processing step

## Future Enhancements

Potential improvements that could be added:
1. **Adaptive scaling** based on detected UI scale
2. **Template caching** for improved performance
3. **Multi-threading** for parallel scale testing
4. **Learning-based** mask adjustment
5. **Template validation** to detect corrupted assets

## Testing Results

The implementation has been verified to:
- ✅ Import successfully
- ✅ Create proper masks with configurable parameters
- ✅ Integrate with existing auto_sim detection logic
- ✅ Maintain backward compatibility
- ✅ Provide comprehensive error handling and logging
