""":module: watchdog.observers.inotify_buffer
:synopsis: A wrapper for ``Inotify``.
:author: thomas.amland@gmail.com (Thomas Amland)
:author: contact@tiger-222.fr (Mickaël Schoentgen)
:author: Joachim Coenen <joachimcoenen@icloud.com>
:platforms: linux 2.6.13+
"""

from __future__ import annotations

import logging
from typing import TypeAlias, NamedTuple

from watchdog.observers.inotify_c import InotifyEvent
from watchdog.utils.delayed_queue import DelayedQueue

logger = logging.getLogger(__name__)


class PathedInotifyEvent(NamedTuple):
    """An InotifyEvent and its full source path"""
    ev: InotifyEvent
    path: bytes


GroupedInotifyEvent: TypeAlias = PathedInotifyEvent | tuple[PathedInotifyEvent, PathedInotifyEvent]


# todo rename to InotifyMoveEventGrouper
class InotifyBuffer:
    """A queue-like class for `Inotify` that holds events for `delay` seconds. During
    this time, IN_MOVED_FROM and IN_MOVED_TO events are paired.
    """

    delay = 0.5

    def __init__(self) -> None:
        self._queue: DelayedQueue[GroupedInotifyEvent] = DelayedQueue(self.delay)

    def read_event(self) -> GroupedInotifyEvent | None:
        """Returns a single event or a tuple of from/to events in case of a
        paired move event. If this buffer has been closed, immediately return
        None.
        """
        return self._queue.get()

    def put_event(self, event: PathedInotifyEvent) -> None:
        """Add an event to the `queue`. When adding an IN_MOVE_TO event, remove
        the previous added matching IN_MOVE_FROM event and add them back to the
        queue as a tuple.
        """
        logger.debug("in-event %s", event)
        # Only add delay for unmatched move_from events
        should_delay = event.ev.is_moved_from

        if event.ev.is_moved_to:
            event = self._group_moved_to_event(event)

        self._queue.put(event, delay=should_delay)

    def _group_moved_to_event(self, to_event: PathedInotifyEvent) -> GroupedInotifyEvent:
        """Group any matching move events by check if a matching move_from is in delay queue already"""

        def matching_from_event(event: GroupedInotifyEvent) -> bool:
            return isinstance(event, PathedInotifyEvent) and event.ev.is_moved_from and event.ev.cookie == to_event.ev.cookie

        # Check if move_from is in delayqueue already
        from_event = self._queue.remove(matching_from_event)
        if from_event is None:
            logger.debug("could not find matching move_from event")

        return (from_event, to_event) if from_event is not None else to_event

    def get_queued_moved_from_event(self, cookie: int) -> PathedInotifyEvent | None:
        def matching_from_event(event: GroupedInotifyEvent) -> bool:
            return isinstance(event, PathedInotifyEvent) and event.ev.is_moved_from and event.ev.cookie == cookie

        return self._queue.find(matching_from_event)

    def close(self) -> None:
        self._queue.close()
