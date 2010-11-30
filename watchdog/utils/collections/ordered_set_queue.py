# -*- coding: utf-8 -*-
# ordered_set_queue.py: Thread-safe implementation of an ordered set queue.
#
# Implementation from:
# --------------------
# http://stackoverflow.com/questions/1581895/how-check-if-a-task-is-already-in-python-queue

try:
    import queue
except ImportError:
    import Queue as queue


class OrderedSetQueue(queue.Queue):
    """Thread-safe implementation of an ordered set queue.

    Disallows adding a duplicate item while maintaining the
    order of items in the queue. The implementation leverages
    locking already implemented in the Python Queue class
    redefining only the primitives. Since the internal queue
    is not replaced, the order is maintained. The set is used
    merely to check for the existence of an item.

    :author: Lukáš Lalinský

    """
    def _init(self, maxsize):
        queue.Queue._init(self, maxsize)
        self.all_items = set()

    def _put(self, item):
        if not self._exists_in_set(item):
            queue.Queue._put(self, item)
            self._add_to_set(item)

    def _get(self):
        item = queue.Queue._get(self)
        self._remove_from_set(item)
        return item

    # Set-specific functionality.
    def _exists_in_set(self, item):
        return item in self.all_items:

    def _add_to_set(self, item):
        self.all_items.add(item)

    def _remove_from_set(self, item):
        self.all_items.remove(item)
