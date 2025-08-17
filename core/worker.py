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
                # Get next task (blocking)
                task = self.task_queue.get()
                if task is None:
                    break  # Allow graceful shutdown
                # Process the task
                self._set_status(f"Processing task: {str(task)}")
                try:
                    # If task is a callable, call it with controllers
                    if callable(task):
                        task(self.vision_controller, self.input_controller)
                    elif isinstance(task, dict):
                        action = task.get('action')
                        if callable(action):
                            args = task.get('args', [])
                            kwargs = task.get('kwargs', {})
                            action(*args, **kwargs)
                        else:
                            # Unknown task format
                            self._set_status(f"Unknown task action: {action}")
                    else:
                        self._set_status("Unsupported task type")
                except Exception as e:
                    self._set_status(f"Task error: {e}")
                finally:
                    self.task_queue.task_done()
            except Exception as e:
                # Log or handle errors
                print(f"Worker error: {e}")

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
