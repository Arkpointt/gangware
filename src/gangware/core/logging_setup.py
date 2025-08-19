"""Logging setup utilities for Gangware.

Provides a single setup function to configure application-wide logging with:
- Rotating file handler under the per-user config directory
- Console handler for quick inspection during development
- Configurable log level via config.ini (DEFAULT.log_level)

Usage:
    from .core.logging_setup import setup_logging
    setup_logging(config_manager)

This will create logs/gangware.log next to config.ini (e.g., %APPDATA%/Gangware/logs).
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
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
    """Return directory path for debug artifacts (images, dumps)."""
    base_dir = Path(getattr(config_manager, "config_path")).parent
    out_dir = base_dir / name
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def setup_logging(config_manager, level: Optional[str | int] = None) -> None:
    """Configure root logger with a rotating file and console handler.

    - File: logs/gangware.log (max 2MB, keep 5 backups)
    - Console: INFO+ by default
    - Level: from parameter if provided, else DEFAULT.log_level in config, else INFO
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
    for h in list(logger.handlers):
        logger.removeHandler(h)

    # Format with timestamp, level, logger name, and message
    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler
    log_dir = get_log_dir(config_manager)
    file_path = log_dir / "gangware.log"
    fh = RotatingFileHandler(file_path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    fh.setLevel(lvl)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

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
