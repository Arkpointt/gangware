# Debug feature package
# Provides template capture, ROI selection, and calibration functionality

from .calibration_service import CalibrationService
from .template import wait_and_capture_template

__all__ = ["CalibrationService", "wait_and_capture_template"]
