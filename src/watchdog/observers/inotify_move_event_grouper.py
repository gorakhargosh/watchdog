""":module: watchdog.observers.inotify_buffer
:synopsis: queue-like class for ``Inotify`` to group move events.
:author: thomas.amland@gmail.com (Thomas Amland)
:author: Mickaël Schoentgen <contact@tiger-222.fr>
:author: Joachim Coenen <joachimcoenen@icloud.com>
:platforms: linux 2.6.13+
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, NamedTuple, cast

from watchdog.utils.delayed_queue import DelayedQueue

if TYPE_CHECKING:
    from typing import TypeAlias

    from watchdog.observers.inotify_c import InotifyEvent, WatchDescriptor
    from watchdog.utils import Seconds

logger = logging.getLogger(__name__)


class PathedInotifyEvent(NamedTuple):
    """An InotifyEvent and its full source path"""

    ev: InotifyEvent
    path: bytes


GroupedInotifyEvent: TypeAlias = PathedInotifyEvent | tuple[PathedInotifyEvent, PathedInotifyEvent]


class InotifyMoveEventGrouper:
    """A queue-like class for `Inotify` that holds IN_MOVE_FROM events for
    `delay`. During this time, IN_MOVED_FROM and IN_MOVED_TO events are
    paired.
    """

    delay: Seconds = 0.5

    def __init__(self) -> None:
        self._queue: DelayedQueue[GroupedInotifyEvent] = DelayedQueue(self.delay)

    def read_event(self) -> GroupedInotifyEvent | None:
        """Returns a single event or a tuple of from/to events in case of a
        paired move event. If this buffer has been closed, raise the Closed
        exception.
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

        grouped_event = self._group_moved_to_event(event) if event.ev.is_moved_to else event

        self._queue.put(grouped_event, delay=should_delay)

    def _group_moved_to_event(self, to_event: PathedInotifyEvent) -> GroupedInotifyEvent:
        """Group any matching move events by checking if a matching move_from is
        in delay queue already and removing it"""
        cookie = to_event.ev.cookie

        def matching_from_event(event: GroupedInotifyEvent) -> bool:
            return isinstance(event, PathedInotifyEvent) and event.ev.is_moved_from and event.ev.cookie == cookie

        # Check if move_from is in delayqueue already
        from_event = cast("PathedInotifyEvent", self._queue.remove(matching_from_event))
        if from_event is None:
            logger.debug("could not find matching move_from event")

        return (from_event, to_event) if from_event is not None else to_event

    def get_queued_moved_from_event(self, cookie: int) -> PathedInotifyEvent | None:
        """Finds a queued IN_MOVED_FROM event with the give cookie, but does not
        remove it."""

        def matching_from_event(event: GroupedInotifyEvent) -> bool:
            return isinstance(event, PathedInotifyEvent) and event.ev.is_moved_from and event.ev.cookie == cookie

        return cast("PathedInotifyEvent", self._queue.find(matching_from_event))

    def has_pending_moved_from(self, path: bytes) -> bool:
        """Check if an IN_MOVED_FROM event for the given directory path is pending."""
        norm_path = os.path.normpath(path)

        def _is_matching_moved_from(item: GroupedInotifyEvent) -> bool:
            return (
                isinstance(item, PathedInotifyEvent)
                and item.ev.is_moved_from
                and item.ev.is_directory
                and os.path.normpath(item.path) == norm_path
            )

        return self._queue.find(_is_matching_moved_from) is not None

    def has_pending_move_to_or_create(self, path: bytes) -> bool:
        """Check if an IN_MOVED_TO or IN_CREATE directory event for the given path is pending."""
        norm_path = os.path.normpath(path)

        def _is_matching(item: GroupedInotifyEvent) -> bool:
            if isinstance(item, PathedInotifyEvent):
                return (
                    item.ev.is_directory
                    and (item.ev.is_moved_to or item.ev.is_create)
                    and os.path.normpath(item.path) == norm_path
                )
            return item[1].ev.is_directory and os.path.normpath(item[1].path) == norm_path

        return self._queue.find(_is_matching) is not None

    def purge_events_for_wds(self, wds: set[WatchDescriptor]) -> None:
        """Purge all queued events associated with any of the given watch descriptors."""
        if not wds:
            return

        def _is_matching(item: GroupedInotifyEvent) -> bool:
            if isinstance(item, PathedInotifyEvent):
                return item.ev.wd in wds
            # For paired move events (item[0] is from_event, item[1] is to_event),
            # only purge if the destination WD belongs to the removed subtree.
            # If the destination remains watched, the move into the surviving tree
            # is a valid event that must be preserved.
            return item[1].ev.wd in wds

        while self._queue.remove(_is_matching) is not None:
            pass

    def close(self) -> None:
        """closes the queue"""
        self._queue.close()
