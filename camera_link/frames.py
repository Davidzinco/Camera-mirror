"""A bounded handoff between camera, network, virtual device and UI threads."""
import threading
import time


class LatestFrame:
    def __init__(self):
        self._lock = threading.Lock()
        self._value = None
        self._sequence = 0
        self._stamp = 0.0

    def put(self, value):
        with self._lock:
            self._value = value
            self._sequence += 1
            self._stamp = time.monotonic()

    def get(self):
        with self._lock:
            return self._value, self._sequence, self._stamp

    def clear(self):
        with self._lock:
            self._value = None
            self._stamp = 0.0
