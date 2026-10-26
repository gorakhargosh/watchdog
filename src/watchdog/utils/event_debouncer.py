from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, overload

from watchdog.utils import BaseThread, renamed_attribute, resolve_renamed_argument

if TYPE_CHECKING:
    from collections.abc import Callable

    from watchdog.events import FileSystemEvent
    from watchdog.utils import Seconds

logger = logging.getLogger(__name__)


class EventDebouncer(BaseThread):
    """Background thread for debouncing event handling.

    When an event is received, wait until the configured debounce interval
    passes before calling the callback.  If additional events are received
    before the interval passes, reset the timer and keep waiting.  When the
    debouncing interval passes, the callback will be called with a list of
    events in the order in which they were received.

    :param debounce_interval:
        How long to wait before calling the callback.
    :type debounce_interval:
        ``Seconds``
    :param events_callback:
        The callback function to be invoked with the debounced events.
    :type events_callback:
        ``Callable[[list[FileSystemEvent]], None]``
    :param debounce_interval_seconds:
        Deprecated, use ``debounce_interval`` instead.
    :type debounce_interval_seconds:
        ``Seconds``
    """

    @overload
    def __init__(
        self,
        debounce_interval: Seconds,
        events_callback: Callable[[list[FileSystemEvent]], None],
    ) -> None: ...

    @overload
    def __init__(
        self,
        *,
        debounce_interval_seconds: Seconds,
        events_callback: Callable[[list[FileSystemEvent]], None],
    ) -> None: ...

    def __init__(
        self,
        debounce_interval: Seconds | None = None,
        events_callback: Callable[[list[FileSystemEvent]], None] | None = None,
        *,
        debounce_interval_seconds: Seconds | None = None,
    ) -> None:
        super().__init__()
        interval = resolve_renamed_argument(
            "debounce_interval_seconds",
            debounce_interval_seconds,
            "debounce_interval",
            debounce_interval,
            default=None,
        )
        if interval is None:
            error = "EventDebouncer() missing required argument: 'debounce_interval'"
            raise TypeError(error)
        if events_callback is None:
            error = "EventDebouncer() missing required argument: 'events_callback'"
            raise TypeError(error)
        self.debounce_interval = interval
        self.events_callback = events_callback

        self._events: list[FileSystemEvent] = []
        self._cond = threading.Condition()

    debounce_interval_seconds = renamed_attribute("debounce_interval_seconds", "debounce_interval")

    def handle_event(self, event: FileSystemEvent) -> None:
        with self._cond:
            self._events.append(event)
            self._cond.notify()

    def stop(self) -> None:
        with self._cond:
            super().stop()
            self._cond.notify()

    def run(self) -> None:
        """Runs the event loop that waits for incoming filesystem events and triggers
        the callback once the debounce interval has passed."""
        with self._cond:
            while True:
                # Wait for first event (or shutdown).
                self._cond.wait()

                if self.debounce_interval:
                    # Wait for additional events (or shutdown) until the debounce interval passes.
                    while self.should_keep_running():
                        if not self._cond.wait(timeout=self.debounce_interval):
                            break

                if not self.should_keep_running():
                    break

                events = self._events
                self._events = []
                self.events_callback(events)
