"""
State & Task Management Module
Handles internal state and task queue.
"""

import threading


class StateManager:
    """Thread-safe state manager."""

    def __init__(self):
        self.lock = threading.Lock()
        self._state = {}

    def set(self, key, value):
        """Thread-safe setter for global state."""
        with self.lock:
            self._state[key] = value

    def get(self, key, default=None):
        """Thread-safe getter for global state."""
        with self.lock:
            return self._state.get(key, default)

    def remove(self, key):
        """Thread-safe remover for global state."""
        with self.lock:
            if key in self._state:
                del self._state[key]

    def clear(self):
        """Thread-safe clear for global state."""
        with self.lock:
            self._state.clear()
