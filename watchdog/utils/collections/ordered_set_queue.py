# -*- coding: utf-8 -*-
# ordered_set_queue.py: Thread-safe implementation of an ordered set queue.
#
# Implementation from:
# --------------------
# http://stackoverflow.com/questions/1581895/how-check-if-a-task-is-already-in-python-queue

"""
    Thread-safe implementation of an ordered set queue.

    :author: Lukáš Lalinský <lalinsky@gmail.com>
    :author: Gora Khargosh <gora.khargosh@gmail.com>

"""


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

    Queued items must be immutable and hashable so that they can be used
    as dictionary keys. You must implement **only read-only properties** and
    the :func:`__hash__()`, :func:`__eq__()`, and :func:`__ne__` methods 
    for items to be hashable. An example implementation follows::
    
        class Item(object):
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
    """
    def _init(self, maxsize):
        queue.Queue._init(self, maxsize)
        self._set_of_items = set()

    def _put(self, item):
        if item not in self._set_of_items:
            queue.Queue._put(self, item)
            self._set_of_items.add(item)

    def _get(self):
        item = queue.Queue._get(self)
        self._set_of_items.remove(item)
        return item
