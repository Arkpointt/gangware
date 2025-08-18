"""
Worker Thread Module
Processes tasks from the queue.
"""


import threading


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
        """Main loop for processing tasks from the queue."""
        while True:
            try:
                task = self.task_queue.get()
                if task is None:
                    break
                self._display_task_status(task)
                try:
                    # For labeled tasks, trigger a subtle success flash in the UI at start
                    if isinstance(task, dict) and 'label' in task and hasattr(self.status_callback, 'success_flash'):
                        try:
                            self.status_callback.success_flash(task['label'])
                        except Exception:
                            pass
                    self._execute_task(task)
                except Exception as e:
                    self._set_status(f"Task error: {e}")
                finally:
                    self.task_queue.task_done()
            except Exception as e:
                print(f"Worker error: {e}")

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
