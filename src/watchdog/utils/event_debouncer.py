from __future__ import annotations

import logging
import time
import threading
from typing import TYPE_CHECKING

from watchdog.utils import BaseThread

if TYPE_CHECKING:
    from typing import Callable

    from watchdog.events import FileSystemEvent

logger = logging.getLogger(__name__)


class EventDebouncer(BaseThread):
    """Background thread for debouncing event handling.

    When an event is received, wait until the configured debounce interval
    passes before calling the callback.  If additional events are received
    before the interval passes, reset the timer and keep waiting.  When the
    debouncing interval passes, the callback will be called with a list of
    events in the order in which they were received.

    :param debounce_interval_seconds:
        The number of seconds to wait before calling the callback.
    :type debounce_interval_seconds:
        ``int``
    :param events_callback:
        The callback function to be invoked with the debounced events.
    :type events_callback:
        ``Callable[[list[FileSystemEvent]], None]``
    """

    def __init__(
        self,
        debounce_interval_seconds: int,
        events_callback: Callable[[list[FileSystemEvent]], None],
    ) -> None:
        super().__init__()
        self.debounce_interval_seconds = debounce_interval_seconds
        self.events_callback = events_callback

        self._events: list[FileSystemEvent] = []
        self._cond = threading.Condition()

    def handle_event(self, event: FileSystemEvent) -> None:
        with self._cond:
            self._events.append(event)
            self._cond.notify()

    def stop(self) -> None:
        with self._cond:
            super().stop()
            self._cond.notify()

    def time_to_flush(self, started: float) -> bool:
        return time.monotonic() - started > self.debounce_interval_seconds

    def run(self) -> None:
        """Runs the event loop that waits for incoming filesystem events and triggers
        the callback once the debounce interval has passed."""
        with self._cond:
            while self.should_keep_running():
                if self.debounce_interval_seconds:
                    started = time.monotonic()
                    while self.should_keep_running():
                        timed_out = not self._cond.wait(timeout=self.debounce_interval_seconds)
                        if timed_out or self.time_to_flush(started):
                            break
                else:
                    self._cond.wait()

                events = self._events
                self._events = []
                self.events_callback(events)

            # Send any events before leaving
            if self._events:
                self.events_callback(events)
