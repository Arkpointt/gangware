"""
Worker Thread Module
Processes tasks from the queue.
"""


import threading
import logging
import time


class Worker(threading.Thread):
    """Worker thread for executing tasks from the queue."""

    def __init__(
        self,
        config_manager,
        state_manager,
        vision_controller,
        input_controller,
        task_queue,
        status_callback=None,
    ):
        super().__init__(daemon=True)
        self.config_manager = config_manager
        self.state_manager = state_manager
        self.vision_controller = vision_controller
        self.input_controller = input_controller
        self.task_queue = task_queue
        self.status_callback = status_callback
        # Add more initialization as needed

    def run(self):
        """Main loop delegating to a per-iteration handler to lower complexity."""
        while self._process_queue_iteration():
            pass

    def _process_queue_iteration(self) -> bool:
        """Process a single queue item. Return False to break the loop."""
        try:
            task = self.task_queue.get()
        except Exception:
            logging.getLogger(__name__).exception("worker: queue get error")
            return True
        if task is None:
            return False
        self._display_task_status(task)
        is_tek_dash = self._is_tek_punch_task(task)
        label = self._task_label(task)
        t0 = time.perf_counter()
        try:
            self._before_execute(task, is_tek_dash)
            self._execute_task(task)
        except Exception as e:
            logging.getLogger(__name__).exception("worker: task execution error for %s", label)
            self._set_status(f"Task error: {e}")
        finally:
            dur_ms = (time.perf_counter() - t0) * 1000.0
            try:
                # Read configurable threshold (default 1000ms)
                thr_ms = 1000.0
                try:
                    v = self.config_manager.get("slow_task_threshold_ms", fallback="1000")
                    thr_ms = float(v)
                except Exception:
                    pass
                if dur_ms > thr_ms:
                    logging.getLogger(__name__).warning("worker: slow task %s took %.1fms", label, dur_ms)
                else:
                    logging.getLogger(__name__).info("worker: task %s executed in %.1fms", label, dur_ms)
            except Exception:
                pass
            self._after_execute(is_tek_dash)
            try:
                self.task_queue.task_done()
            except Exception:
                pass
        return True

    def _before_execute(self, task, is_tek_dash: bool) -> None:
        # For labeled tasks, trigger a subtle success flash in the UI at start
        if isinstance(task, dict) and 'label' in task and hasattr(self.status_callback, 'success_flash'):
            try:
                self.status_callback.success_flash(task['label'])
            except Exception:
                pass
        if is_tek_dash:
            # Record Tek Dash start time for input-window buffering
            try:
                import time as _t
                self.state_manager.set('tek_dash_started_at', _t.perf_counter())
                # Keep in sync with manager's estimate if needed
                self.state_manager.set('tek_dash_est_duration', 0.9)
            except Exception:
                pass

    def _after_execute(self, is_tek_dash: bool) -> None:
        # Handle buffering only for Tek Dash tasks
        if not is_tek_dash:
            return
        try:
            # Mark not busy now that the execution finished
            self.state_manager.set('tek_dash_busy', False)
        except Exception:
            pass
        # Check buffered flag and enqueue one more if present
        try:
            buffered = bool(self.state_manager.get('tek_dash_buffer', False))
        except Exception:
            buffered = False
        if not buffered:
            return
        try:
            # Consume buffer and mark busy, then enqueue one more
            self.state_manager.set('tek_dash_buffer', False)
            self.state_manager.set('tek_dash_busy', True)
        except Exception:
            pass
        try:
            self.task_queue.put_nowait(self._make_tek_punch_task())
            if hasattr(self.status_callback, 'flash_hotkey_line'):
                try:
                    self.status_callback.flash_hotkey_line("Shift+R")
                except Exception:
                    pass
        except Exception:
            pass

    def _make_tek_punch_task(self):
        # Helper to produce a tagged Tek Punch callable similar to HotkeyManager
        def _job(vc, ic):
            try:
                from ..macros import combat as _combat
                _combat.execute_tek_punch(ic, self.config_manager)
            except Exception:
                pass
        try:
            setattr(_job, "_gw_task_id", "tek_punch")
        except Exception:
            pass
        return _job

    @staticmethod
    def _is_tek_punch_task(task_obj) -> bool:
        try:
            if callable(task_obj) and getattr(task_obj, "_gw_task_id", "") == "tek_punch":
                return True
            if isinstance(task_obj, dict):
                label = str(task_obj.get('label', '')).lower()
                name = str(task_obj.get('name', '')).lower()
                return ('tek' in label and 'punch' in label) or ('tek' in name and 'punch' in name)
        except Exception:
            pass
        return False

    @staticmethod
    def _task_label(task) -> str:
        try:
            if isinstance(task, dict):
                if 'label' in task:
                    return str(task['label'])
                if 'name' in task:
                    return str(task['name'])
            if callable(task):
                tid = getattr(task, '_gw_task_id', None)
                if tid:
                    return str(tid)
                fn = getattr(task, '__name__', None)
                if fn:
                    return str(fn)
            return type(task).__name__
        except Exception:
            return "task"

    def _display_task_status(self, task):
        try:
            # Suppress status for callables (macros) and labeled tasks
            if callable(task):
                return
            if isinstance(task, dict) and "label" in task:
                return
            self._set_status(f"Processing task: {str(task)}")
        except Exception:
            pass

    def _execute_task(self, task):
        if callable(task):
            task(self.vision_controller, self.input_controller)
            return
        if isinstance(task, dict):
            action = task.get('action')
            if callable(action):
                args = task.get('args', [])
                kwargs = task.get('kwargs', {})
                action(*args, **kwargs)
                return
            self._set_status(f"Unknown task action: {action}")
            return
        self._set_status("Unsupported task type")

    def _set_status(self, text: str):
        try:
            if self.status_callback:
                # status_callback expected to have set_status method
                if hasattr(self.status_callback, 'set_status'):
                    self.status_callback.set_status(text)
                else:
                    # If it's a callable, call it directly
                    if callable(self.status_callback):
                        self.status_callback(text)

        except Exception:
            # Swallow errors from status updates to avoid crashing worker
            pass
