"""
Worker Thread Module
Processes tasks from the queue.
"""


import threading

class Worker(threading.Thread):
    """
    Worker thread for executing tasks from the queue.
    """
    def __init__(self, config_manager, state_manager, vision_controller, input_controller, task_queue):
        super().__init__(daemon=True)
        self.config_manager = config_manager
        self.state_manager = state_manager
        self.vision_controller = vision_controller
        self.input_controller = input_controller
        self.task_queue = task_queue
        # Add more initialization as needed

    def run(self):
        """
        Main loop for processing tasks from the queue.
        """
        while True:
            try:
                # Get next task (blocking)
                task = self.task_queue.get()
                if task is None:
                    break  # Allow graceful shutdown
                # Process the task (placeholder)
                # Example: task could be a function or dict with action info
                # self.process_task(task)
                self.task_queue.task_done()
            except Exception as e:
                # Log or handle errors
                print(f"Worker error: {e}")
