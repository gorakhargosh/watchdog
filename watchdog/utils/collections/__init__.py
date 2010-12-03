# -*- coding: utf-8 -*-
# collections: utility collections.
#
# Copyright (C) 2010 Gora Khargosh <gora.khargosh@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# Implementation from:
# --------------------
# http://stackoverflow.com/questions/1581895/how-check-if-a-task-is-already-in-python-queue

"""
    Utility collections.

    :module: watchdog.utils.collections
    :author: Gora Khargosh <gora.khargosh@gmail.com>
    :author: Lukáš Lalinský <lalinsky@gmail.com>
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
