# -*- coding: utf-8 -*-
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

from __future__ import with_statement

import threading
from watchdog.utils import DaemonThread, real_absolute_path


class _EventEmitter(DaemonThread):
    def __init__(self, path, handler, event_queue,
                 recursive=False, interval=1):
        super(_EventEmitter, self).__init__(interval)

        self._handlers = set([handler])
        self._lock = threading.Lock()
        self._path = real_absolute_path(path)
        self._event_queue = event_queue
        self._is_recursive = recursive

    @property
    def lock(self):
        return self._lock

    @property
    def is_recursive(self):
        return self._is_recursive

    @property
    def event_queue(self):
        return self._event_queue

    @property
    def path(self):
        return self._path

    @property
    def handlers(self):
        return self._handlers

    def add_handler(self, handler):
        with self._lock:
            self._handlers.add(handler)

    def remove_handler(self, handler):
        with self._lock:
            self._handlers.remove(handler)

