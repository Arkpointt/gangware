"""Logging setup utilities for Gangware.

Provides a single setup function to configure application-wide logging with:
- Session-based file handler under the per-user config directory
- Console handler for quick inspection during development
- Configurable log level via config.ini (DEFAULT.log_level)
- Automatic retention of the last 3 sessions

Usage:
    from .core.logging_setup import setup_logging
    setup_logging(config_manager)

This will create logs/session-YYYYmmdd_HHMMSS/gangware.log next to config.ini (e.g., %APPDATA%/Gangware/logs).
"""
from __future__ import annotations

import logging
import os
import platform
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def _level_from_str(value: Optional[str]) -> int:
    if not value:
        return logging.INFO
    v = str(value).strip().upper()
    mapping = {
        "CRITICAL": logging.CRITICAL,
        "ERROR": logging.ERROR,
        "WARNING": logging.WARNING,
        "WARN": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
        "NOTSET": logging.NOTSET,
    }
    return mapping.get(v, logging.INFO)


def get_log_dir(config_manager) -> Path:
    """Return directory path for logs next to the config.ini.

    Example on Windows: %APPDATA%/Gangware/logs
    """
    base_dir = Path(getattr(config_manager, "config_path")).parent
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_artifacts_dir(config_manager, name: str = "artifacts") -> Path:
    """Return directory path for debug artifacts (images, dumps).

    If a session directory is active (GW_LOG_SESSION_DIR), artifacts are stored
    under that session directory to keep support bundles self-contained.
    """
    session_env = os.environ.get("GW_LOG_SESSION_DIR", "").strip()
    if session_env:
        out_dir = Path(session_env) / name
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir
    base_dir = Path(getattr(config_manager, "config_path")).parent
    out_dir = base_dir / name
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def get_session_dir(config_manager) -> Path:
    """Create and return a new session directory under logs/."""
    base = get_log_dir(config_manager)
    ts = datetime.now().strftime("session-%Y%m%d_%H%M%S")
    session = base / ts
    session.mkdir(parents=True, exist_ok=True)
    return session


def prune_old_sessions(log_dir: Path, keep: int = 3) -> None:
    """Keep only the most recent 'keep' session directories inside log_dir."""
    try:
        # Consider only directories named like 'session-...'
        entries = [p for p in log_dir.iterdir() if p.is_dir() and p.name.startswith("session-")]
        entries.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for old in entries[keep:]:
            try:
                shutil.rmtree(old, ignore_errors=True)
            except Exception:
                pass
        # Optionally, prune legacy flat log files older than the most recent 3 by mtime
        files = [p for p in log_dir.iterdir() if p.is_file() and p.suffix == ".log"]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for oldf in files[keep:]:
            try:
                oldf.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception:
        pass


def _create_session_info(session_dir: Path, config_manager) -> None:
    """Create session_info.txt with system and application details for support."""
    try:
        info_file = session_dir / "session_info.txt"
        with open(info_file, 'w', encoding='utf-8') as f:
            f.write("GANGWARE SESSION INFORMATION\n")
            f.write("=" * 50 + "\n\n")

            # Session details
            f.write(f"Session Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Session Directory: {session_dir.name}\n\n")

            # System information
            f.write("SYSTEM INFORMATION:\n")
            f.write("-" * 20 + "\n")
            f.write(f"Operating System: {platform.system()} {platform.release()}\n")
            f.write(f"Platform: {platform.platform()}\n")
            f.write(f"Architecture: {platform.machine()}\n")
            f.write(f"Python Version: {sys.version}\n")
            f.write(f"Python Executable: {sys.executable}\n\n")

            # Application configuration
            f.write("APPLICATION CONFIGURATION:\n")
            f.write("-" * 30 + "\n")
            try:
                config_path = getattr(config_manager, 'config_path', 'Unknown')
                f.write(f"Config File: {config_path}\n")

                # Key settings that affect functionality
                key_settings = [
                    'log_level', 'inventory_key', 'search_bar_template',
                    'flak_boots_display', 'flak_chestpiece_display',
                    'flak_gauntlets_display', 'flak_helmet_display', 'flak_leggings_display'
                ]

                for setting in key_settings:
                    try:
                        value = config_manager.get(setting)
                        if setting == 'search_bar_template' and value:
                            # Just show if it's set, not the full path
                            value = f"Set ({Path(value).name})" if Path(value).exists() else "Set (missing file)"
                        f.write(f"{setting}: {value}\n")
                    except Exception:
                        f.write(f"{setting}: <error reading>\n")

            except Exception as e:
                f.write(f"Error reading configuration: {e}\n")

            f.write("\n")
            f.write("SUPPORT INSTRUCTIONS:\n")
            f.write("-" * 20 + "\n")
            f.write("This folder contains all files needed for technical support.\n")
            f.write("Please zip this entire session folder and email it for assistance.\n")
            f.write(f"Session folder location: {session_dir}\n")

    except Exception:
        # Don't fail logging setup if session info creation fails
        pass


def _create_support_readme(log_dir: Path) -> None:
    """Create a README file in the logs directory explaining support process."""
    try:
        readme_file = log_dir / "README_SUPPORT.txt"
        # Only create if it doesn't exist to avoid overwriting user notes
        if not readme_file.exists():
            with open(readme_file, 'w', encoding='utf-8') as f:
                f.write("GANGWARE SUPPORT LOGS\n")
                f.write("=" * 30 + "\n\n")
                f.write("This folder contains log sessions for technical support.\n\n")
                f.write("FOR SUPPORT:\n")
                f.write("-" * 12 + "\n")
                f.write("1. Find the most recent 'session-YYYYMMDD_HHMMSS' folder below\n")
                f.write("2. Right-click that folder and choose 'Send to > Compressed (zipped) folder'\n")
                f.write("3. Email the created .zip file for technical support\n\n")
                f.write("FOLDER STRUCTURE:\n")
                f.write("-" * 17 + "\n")
                f.write("- session-YYYYMMDD_HHMMSS/  (Most recent session)\n")
                f.write("  ├── gangware.log           (Application logs)\n")
                f.write("  ├── session_info.txt       (System information)\n")
                f.write("  └── artifacts/             (Screenshots, debug files)\n\n")
                f.write("The application automatically keeps only the 3 most recent sessions.\n")
                f.write("Each session represents one run of the application from start to exit.\n\n")
                f.write(f"Support logs location: {log_dir}\n")

    except Exception:
        # Don't fail logging setup if README creation fails
        pass


def setup_logging(config_manager, level: Optional[str | int] = None) -> Path:
    """Configure root logger with a session-based file and console handler.

    Returns the created session directory Path.

    - File: logs/session-YYYYmmdd_HHMMSS/gangware.log (keep last 3 sessions)
    - Console: INFO+ by default
    - Level: from parameter if provided, else DEFAULT.log_level in config, else INFO

    Creates a support-ready session folder containing:
    - gangware.log: All application logs
    - session_info.txt: System and application information
    - artifacts/: Screenshots and debug data when issues occur
    """
    # Determine level
    cfg_level = getattr(config_manager, "get", lambda *_: None)("log_level")
    if isinstance(level, str):
        lvl = _level_from_str(level)
    elif isinstance(level, int):
        lvl = level
    else:
        lvl = _level_from_str(cfg_level)

    logger = logging.getLogger()
    logger.setLevel(lvl)

    # Clear existing handlers to avoid duplicates on re-run
    for h in logger.handlers[:]:
        logger.removeHandler(h)

    # Format with timestamp, level, logger name, and message
    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Session-based file handler
    log_dir = get_log_dir(config_manager)
    session_dir = get_session_dir(config_manager)
    # Expose session dir via environment for other modules (e.g., artifacts)
    try:
        os.environ["GW_LOG_SESSION_DIR"] = str(session_dir)
    except Exception:
        pass

    file_path = session_dir / "gangware.log"
    fh = logging.FileHandler(file_path, encoding="utf-8", delay=True)
    fh.setLevel(lvl)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    # Prune old sessions, keep 3 most recent
    prune_old_sessions(log_dir, keep=3)

    # Create session info file for support
    _create_session_info(session_dir, config_manager)

    # Create support README in main logs directory for first-time users
    _create_support_readme(log_dir)

    # Console handler (INFO+ to keep noise lower by default)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO if lvl < logging.INFO else lvl)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # Quiet down noisy libraries unless in DEBUG
    if lvl > logging.DEBUG:
        logging.getLogger("cv2").setLevel(logging.WARNING)
        logging.getLogger("PIL").setLevel(logging.WARNING)
        logging.getLogger("matplotlib").setLevel(logging.WARNING)

    logger.info("Logging initialized: level=%s, file=%s", logging.getLevelName(lvl), str(file_path))
    logger.info("Support logs: %s (send latest session folder for support)", str(log_dir))
    return session_dir
