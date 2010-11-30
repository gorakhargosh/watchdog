# -*- coding: utf-8 -*-
# ordered_set_queue.py: Thread-safe implementation of an ordered set queue.
#
# Implementation from:
# --------------------
# http://stackoverflow.com/questions/1581895/how-check-if-a-task-is-already-in-python-queue

try:
    from queue import Queue
except ImportError:
    from Queue import Queue


class OrderedSetQueue(Queue):
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
        Queue._init(maxsize)
        self.all_items = set()

    def _put(self, item):
        if item not in self.all_items:
            Queue._put(self, item)
            self.all_items.add(item)

    def _get(self):
        item = Queue._get(self)
        self.all_items.remove(item)
        return item
