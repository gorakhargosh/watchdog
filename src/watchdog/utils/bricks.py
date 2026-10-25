"""Utility collections or "bricks".

:module: watchdog.utils.bricks
:author: yesudeep@google.com (Yesudeep Mangalapilly)
:author: lalinsky@gmail.com (Lukáš Lalinský)
:author: python@rcn.com (Raymond Hettinger)
:author: Mickaël Schoentgen <contact@tiger-222.fr>

Classes
=======
.. autoclass:: OrderedSetQueue
   :members:
   :show-inheritance:
   :inherited-members:

.. autoclass:: OrderedSet

"""

from __future__ import annotations

import queue
import threading
from time import monotonic
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

_EMPTY = object()


class SkipRepeatsQueue(queue.Queue):
    """Thread-safe implementation of an special queue where a
    put of the last-item put'd will be dropped.

    Producers are serialized while queue operations and task accounting are
    delegated to the base class.

    Queued items must be immutable and hashable so that they can be used
    as dictionary keys. You must implement **only read-only properties** and
    the :meth:`Item.__hash__()`, :meth:`Item.__eq__()`, and
    :meth:`Item.__ne__()` methods for items to be hashable.

    An example implementation follows::

        class Item:
            def __init__(self, a, b):
                self._a = a
                self._b = b

            @property
            def a(self):
                return self._a

            @property
            def b(self):
                return self._b

            def _key(self):
                return (self._a, self._b)

            def __eq__(self, item):
                return self._key() == item._key()

            def __ne__(self, item):
                return self._key() != item._key()

            def __hash__(self):
                return hash(self._key())

    based on the OrderedSetQueue below
    """

    def __init__(self, maxsize: int = 0) -> None:
        super().__init__(maxsize)
        self._last_item = _EMPTY
        self._put_lock = threading.Lock()

    def put(self, item: Any, block: bool = True, timeout: float | None = None) -> None:  # noqa: FBT001,FBT002
        """This method will be used by `eventlet`, when enabled, so we cannot use force proper keyword-only
        arguments nor touch the signature. The base queue interprets the remaining timeout.

        For bounded queues, nonblocking puts may raise Full when another
        producer holds the lock, even if the queue has space. A finite timeout
        includes time spent acquiring the producer lock; only the remaining
        budget is forwarded to the base queue. As in the base class, a negative
        timeout raises ValueError only for blocking puts to a bounded queue.
        Unbounded queues never wait for space, so the lock is always acquired
        in blocking mode there.

        Timeouts above the lock's platform limit first try acquiring an idle
        producer lock without a timed conversion. Actual waits retain the
        underlying platform's timeout limits.
        """
        bounded = self.maxsize > 0
        if bounded and block and timeout is not None and timeout < 0:
            raise ValueError("'timeout' must be a non-negative number")

        if not bounded:
            acquired = self._put_lock.acquire()
        elif not block:
            acquired = self._put_lock.acquire(blocking=False)
        elif timeout is None:
            acquired = self._put_lock.acquire()
        else:
            if timeout > threading.TIMEOUT_MAX and self._put_lock.acquire(blocking=False):
                acquired = True
            else:
                deadline = monotonic() + timeout
                acquired = self._put_lock.acquire(blocking=True, timeout=timeout)
                if acquired:
                    timeout = max(0.0, deadline - monotonic())
        if not acquired:
            raise queue.Full

        try:
            if self._last_item is _EMPTY or item != self._last_item:
                super().put(item, block, timeout)
        finally:
            self._put_lock.release()

    def _put(self, item: Any) -> None:
        super()._put(item)
        self._last_item = item

    def _get(self) -> Any:
        item = super()._get()
        if item is self._last_item:
            self._last_item = _EMPTY
        return item
