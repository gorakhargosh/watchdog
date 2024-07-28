from __future__ import annotations

import logging
import time
import threading

from watchdog.utils import BaseThread

logger = logging.getLogger(__name__)


class EventDebouncer(BaseThread):
    """Background thread for debouncing event handling.

    When an event is received, wait until the configured debounce interval
    passes before calling the callback.  If additional events are received
    before the interval passes, reset the timer and keep waiting.  When the
    debouncing interval passes, the callback will be called with a list of
    events in the order in which they were received.
    """

    def __init__(self, debounce_interval_seconds, events_callback):
        super().__init__()
        self.debounce_interval_seconds = debounce_interval_seconds
        self.events_callback = events_callback

        self._events = []
        self._cond = threading.Condition()

    def handle_event(self, event):
        with self._cond:
            self._events.append(event)
            self._cond.notify()

    def stop(self):
        with self._cond:
            super().stop()
            self._cond.notify()

    def time_to_flush(self, started: float) -> bool:
        return time.monotonic() - started > self.debounce_interval_seconds

    def run(self):
        with self._cond:
            while self.should_keep_running():
                started = time.monotonic()
                if self.debounce_interval_seconds:
                    while self.should_keep_running():
                        timed_out = not self._cond.wait(
                            timeout=self.debounce_interval_seconds
                        )
                        if timed_out or self.time_to_flush(started):
                            break
                else:
                    self._cond.wait()

                events = self._events
                self._events = []
                self.events_callback(events)

            # send any events before leaving
            if self._events:
                self.events_callback(events)
