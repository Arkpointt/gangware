"""
Health monitoring and log aggregation utilities.

- HealthAggregator: logging handler counting warnings/errors and slow tasks, flushing to JSON
- HealthMonitor: periodic heartbeat writer and state sampler
- write_environment_snapshot: capture one-time environment info into the session folder
- start_health_monitor: helper to wire everything up
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import sys
import threading
import time
from collections import deque, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Deque, Dict, Optional, Tuple


@dataclass
class RecentError:
    ts: float
    level: str
    logger: str
    msg: str


class HealthAggregator(logging.Handler):
    """Aggregate log signals for support without heavy overhead.

    - Counts warnings/errors per logger
    - Keeps a ring buffer of recent error messages
    - Tracks slow task counts by label (from worker warnings)
    - Flushes a compact health.json snapshot on demand
    """

    def __init__(self, session_dir: Path, max_recent: int = 50) -> None:
        super().__init__(level=logging.INFO)
        self.session_dir = Path(session_dir)
        self.health_path = self.session_dir / "health.json"
        self._lock = threading.Lock()
        self.total_errors = 0
        self.total_warnings = 0
        self.per_logger: Dict[str, Dict[str, int]] = defaultdict(lambda: {"errors": 0, "warnings": 0})
        self.recent: Deque[RecentError] = deque(maxlen=max_recent)
        self.slow_tasks: Dict[str, int] = defaultdict(int)
        self.last_state: Dict[str, Any] = {}
        atexit.register(self.flush)

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            lvl = record.levelno
            name = record.name or "root"
            msg = self.format(record) if self.formatter else record.getMessage()
            now = time.time()
            with self._lock:
                if lvl >= logging.ERROR:
                    self.total_errors += 1
                    self.per_logger[name]["errors"] += 1
                    self.recent.append(RecentError(ts=now, level="ERROR", logger=name, msg=record.getMessage()))
                elif lvl >= logging.WARNING:
                    self.total_warnings += 1
                    self.per_logger[name]["warnings"] += 1
                # Parse slow task pattern: "worker: slow task <label> took <ms>ms"
                if "worker: slow task" in msg:
                    try:
                        # crude parse, robust to variations
                        # example: worker: slow task F2 took 1234.5ms
                        after = msg.split("worker: slow task", 1)[1].strip()
                        label = after.split("took", 1)[0].strip()
                        if label:
                            self.slow_tasks[label] += 1
                    except Exception:
                        pass
        except Exception:
            # Never raise from emit
            pass

    def set_last_state(self, state: Dict[str, Any]) -> None:
        with self._lock:
            self.last_state = dict(state)

    def flush(self) -> None:
        try:
            with self._lock:
                data = {
                    "total_errors": int(self.total_errors),
                    "total_warnings": int(self.total_warnings),
                    "per_logger": {k: dict(v) for k, v in self.per_logger.items()},
                    "slow_tasks": dict(self.slow_tasks),
                    "recent_errors": [
                        {"ts": e.ts, "level": e.level, "logger": e.logger, "msg": e.msg}
                        for e in list(self.recent)
                    ],
                    "last_state": dict(self.last_state),
                    "flushed_at": time.time(),
                }
            self.session_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.health_path.with_suffix(".json.tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            tmp.replace(self.health_path)
        except Exception:
            pass


class HealthMonitor(threading.Thread):
    """Periodic health sampler and heartbeat writer.

    Writes a heartbeat.log line every `interval` seconds and publishes a compact
    state snapshot into the aggregator, which in turn flushes health.json on demand.
    """

    def __init__(
        self,
        session_dir: Path,
        aggregator: HealthAggregator,
        hotkey_thread: Optional[threading.Thread],
        worker_thread: Optional[threading.Thread],
        task_queue: Any,
        interval: float = 5.0,
    ) -> None:
        super().__init__(daemon=True)
        self.session_dir = Path(session_dir)
        self.aggregator = aggregator
        self.hotkey_thread = hotkey_thread
        self.worker_thread = worker_thread
        self.task_queue = task_queue
        self.interval = max(1.0, float(interval))
        self._stop_event = threading.Event()
        self._hb_path = self.session_dir / "heartbeat.log"
        atexit.register(self._on_exit)

    def stop(self) -> None:
        try:
            self._stop_event.set()
        except Exception:
            pass

    def _on_exit(self) -> None:
        try:
            self._write_heartbeat_line(prefix="# shutdown")
            self.aggregator.flush()
        except Exception:
            pass

    def _write_heartbeat_line(self, prefix: str = "") -> None:
        try:
            ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
            parts = [prefix, ts]
            parts.append(f"hotkey_alive={self.hotkey_thread.is_alive() if self.hotkey_thread else False}")
            parts.append(f"worker_alive={self.worker_thread.is_alive() if self.worker_thread else False}")
            qsz = -1
            try:
                qsz = int(self.task_queue.qsize())
            except Exception:
                pass
            parts.append(f"queue_size={qsz}")
            parts.append(f"ark_active={_is_ark_active()}" if sys.platform == "win32" else "ark_active=NA")
            line = " ".join(str(p) for p in parts if p)
            self.session_dir.mkdir(parents=True, exist_ok=True)
            with self._hb_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception:
            pass

    def run(self) -> None:
        logger = logging.getLogger(__name__)
        last = time.perf_counter()
        while not self._stop_event.is_set():
            t0 = time.perf_counter()
            # Build last_state snapshot
            state = {
                "hotkey_alive": bool(self.hotkey_thread.is_alive() if self.hotkey_thread else False),
                "worker_alive": bool(self.worker_thread.is_alive() if self.worker_thread else False),
                "queue_size": int(self._safe_qsize()),
                "ark_active": bool(_is_ark_active()) if sys.platform == "win32" else None,
                "ts": time.time(),
            }
            self.aggregator.set_last_state(state)
            # Heartbeat
            self._write_heartbeat_line()
            # Detect drift (lag spikes)
            now = time.perf_counter()
            drift_ms = (now - last - self.interval) * 1000.0
            if drift_ms > (self.interval * 1000.0):
                logger.warning("health: heartbeat drift %.1fms", drift_ms)
            last = now
            # Periodic aggregator flush (every 30s)
            if int(state["ts"]) % 30 < int(self.interval):
                try:
                    self.aggregator.flush()
                except Exception:
                    pass
            # Sleep remaining
            remain = self.interval - (time.perf_counter() - t0)
            if remain > 0:
                time.sleep(remain)
            else:
                time.sleep(self.interval)

    def _safe_qsize(self) -> int:
        try:
            return int(self.task_queue.qsize())
        except Exception:
            return -1


def write_environment_snapshot(config_manager: Any, session_dir: Path) -> None:
    """Write environment.json in the session folder with system and app info."""
    env: Dict[str, Any] = {}
    try:
        import platform
        env["platform_system"] = platform.system()
        env["platform_release"] = platform.release()
        env["platform_version"] = platform.version()
        env["python_version"] = platform.python_version()
    except Exception:
        pass
    # library versions
    for name in ("cv2", "mss", "numpy", "pydirectinput"):
        try:
            mod = __import__(name)
            v = getattr(mod, "__version__", None)
            env[f"{name}_version"] = v if v is not None else "unknown"
        except Exception:
            env[f"{name}_version"] = "not_installed"
    # monitors topology
    try:
        import mss
        with mss.mss() as sct:
            env["monitors"] = [dict(m) for m in sct.monitors]
            _mons = env["monitors"]
    except Exception:
        env["monitors"] = []
        _mons = []
    # Game window info (one-time, only if Ark is foreground now)
    if sys.platform == "win32":
        try:
            info = _ark_window_info()
            if info:
                env["game_window"] = {k: int(info[k]) for k in ("left", "top", "width", "height")}
                env["game_resolution"] = f"{int(info['width'])}x{int(info['height'])}"
                env["game_borderless"] = _is_borderless(int(info.get("style", 0)))
                try:
                    env["game_monitor_index"] = _monitor_index_for_rect(_mons, int(info["left"]), int(info["top"]), int(info["width"]), int(info["height"]))
                except Exception:
                    pass
        except Exception:
            pass
    # key config and ROI
    try:
        env["inventory_key"] = config_manager.get("inventory_key")
        env["tek_punch_cancel_key"] = config_manager.get("tek_punch_cancel_key")
        env["search_bar_template"] = config_manager.get("search_bar_template")
        env["log_level"] = config_manager.get("log_level")
    except Exception:
        pass
    try:
        env["GW_VISION_ROI"] = os.environ.get("GW_VISION_ROI")
        env["GW_INV_SUBROI"] = os.environ.get("GW_INV_SUBROI")
    except Exception:
        pass
    try:
        session_dir = Path(session_dir)
        with (session_dir / "environment.json").open("w", encoding="utf-8") as fh:
            json.dump(env, fh, indent=2)
    except Exception:
        pass


def start_health_monitor(
    config_manager: Any,
    session_dir: Path,
    hotkey_thread: Optional[threading.Thread],
    worker_thread: Optional[threading.Thread],
    task_queue: Any,
    interval_seconds: float = 5.0,
) -> Tuple[HealthAggregator, HealthMonitor]:
    """Create and start health aggregator and monitor.

    Adds the aggregator as a root logging handler and starts the monitor thread.
    """
    agg = HealthAggregator(session_dir=session_dir)
    # Attach to root logger at INFO level to see warnings/errors and info timings
    root = logging.getLogger()
    # Avoid duplicate handlers if re-running
    have = False
    for h in root.handlers:
        if isinstance(h, HealthAggregator):
            have = True
            agg = h
            break
    if not have:
        root.addHandler(agg)
    # Write environment snapshot once
    try:
        write_environment_snapshot(config_manager, session_dir)
    except Exception:
        pass
    mon = HealthMonitor(session_dir=session_dir, aggregator=agg, hotkey_thread=hotkey_thread, worker_thread=worker_thread, task_queue=task_queue, interval=interval_seconds)
    try:
        mon.start()
    except Exception:
        pass
    return agg, mon


# ------------------------ Minimal Ark active check -------------------------
# Copy-lightweight logic to detect ArkAscended.exe as foreground process.
if sys.platform == "win32":
    try:
        import ctypes
        from ctypes import wintypes
        _user32 = ctypes.windll.user32
        _kernel32 = ctypes.windll.kernel32
    except Exception:  # pragma: no cover
        _user32 = None
        _kernel32 = None
else:
    _user32 = None
    _kernel32 = None


def _is_ark_active() -> bool:
    if _user32 is None or _kernel32 is None:
        return False
    try:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return False
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        hproc = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not hproc:
            return False
        try:
            buf_len = wintypes.DWORD(260)
            while True:
                buf = ctypes.create_unicode_buffer(buf_len.value)
                ok = _kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(buf_len))
                if ok:
                    exe = os.path.basename(buf.value or "").lower()
                    return exe == "arkascended.exe"
                needed = buf_len.value
                if needed <= len(buf):
                    break
                buf_len = wintypes.DWORD(needed)
            return False
        finally:
            _kernel32.CloseHandle(hproc)
    except Exception:
        return False

# ------------------------ Window info helpers -------------------------
if sys.platform == "win32":
    import ctypes as _ct
    GWL_STYLE = -16
    GWL_EXSTYLE = -20
    WS_CAPTION = 0x00C00000
    WS_THICKFRAME = 0x00040000
    WS_POPUP = 0x80000000

    class _RECT(_ct.Structure):
        _fields_ = [("left", _ct.c_long), ("top", _ct.c_long), ("right", _ct.c_long), ("bottom", _ct.c_long)]

    def _ark_window_info() -> Optional[dict]:
        if _user32 is None:
            return None
        try:
            if not _is_ark_active():
                return None
            hwnd = _user32.GetForegroundWindow()
            rc = _RECT()
            if not _user32.GetWindowRect(hwnd, _ct.byref(rc)):
                return None
            width = int(rc.right - rc.left)
            height = int(rc.bottom - rc.top)
            style = int(_user32.GetWindowLongW(hwnd, GWL_STYLE))
            exstyle = int(_user32.GetWindowLongW(hwnd, GWL_EXSTYLE))
            return {"left": int(rc.left), "top": int(rc.top), "width": width, "height": height, "style": style, "exstyle": exstyle}
        except Exception:
            return None

    def _is_borderless(style: int) -> Optional[bool]:
        try:
            has_caption = bool(style & WS_CAPTION)
            has_thick = bool(style & WS_THICKFRAME)
            is_popup = bool(style & WS_POPUP)
            if not has_caption and not has_thick:
                return True if is_popup or True else True
            return False
        except Exception:
            return None

    def _monitor_index_for_rect(monitors: list[dict], left: int, top: int, width: int, height: int, tol: int = 2) -> Optional[int]:
        try:
            for i, mon in enumerate(monitors):
                if i == 0:
                    continue
                if abs(int(mon.get("left", 0)) - left) <= tol and abs(int(mon.get("top", 0)) - top) <= tol and abs(int(mon.get("width", 0)) - width) <= tol and abs(int(mon.get("height", 0)) - height) <= tol:
                    return i
            return None
        except Exception:
            return None
