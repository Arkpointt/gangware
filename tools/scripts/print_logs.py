#!/usr/bin/env python3
"""
Print latest Gangware log tail.

- Finds the per-user logs directory used by Gangware (next to config.ini).
- Picks GW_LOG_SESSION_DIR if set; else selects the newest session-YYYYmmdd_HHMMSS.
- Prints the session path and last N lines of gangware.log.

Usage:
  python tools/scripts/print_logs.py --tail 200
  python tools/scripts/print_logs.py --grep tek_ --tail 300
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List

# Ensure src is on path to import app utilities
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from gangware.core.config import ConfigManager  # type: ignore
from gangware.core.logging_setup import get_log_dir  # type: ignore


def tail_lines(path: Path, n: int) -> List[str]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
            return lines[-n:]
    except FileNotFoundError:
        return [f"<log file not found: {path}>\n"]
    except Exception as e:
        return [f"<error reading {path}: {e}>\n"]


def find_latest_session(log_dir: Path) -> Path | None:
    try:
        sessions = [p for p in log_dir.iterdir() if p.is_dir() and p.name.startswith("session-")]
        if not sessions:
            return None
        sessions.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return sessions[0]
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tail", type=int, default=200, help="lines to print from end")
    ap.add_argument("--grep", type=str, default="", help="substring filter for lines")
    args = ap.parse_args()

    cfg = ConfigManager()
    # Prefer env-provided session directory if present
    session_env = os.environ.get("GW_LOG_SESSION_DIR", "").strip()
    log_dir = get_log_dir(cfg)

    session_dir: Path | None
    if session_env:
        session_dir = Path(session_env)
    else:
        session_dir = find_latest_session(log_dir)

    if not session_dir:
        print(f"No log sessions found under: {log_dir}")
        return 2

    log_file = session_dir / "gangware.log"
    print(f"Session: {session_dir}")
    print(f"Log: {log_file}")

    lines = tail_lines(log_file, max(1, args.tail))
    if args.grep:
        sub = args.grep
        lines = [ln for ln in lines if sub in ln]
        print(f"--- tail | grep '{sub}' (last {len(lines)} lines) ---")
    else:
        print(f"--- tail (last {len(lines)} lines) ---")

    sys.stdout.writelines(lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
