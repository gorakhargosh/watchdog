# -*- coding: utf-8 -*-
#
# Copyright 2014 Thomas Amland <thomas.amland@gmail.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import time
import logging
import threading
from collections import deque
from watchdog.utils import DaemonThread
from .inotify_c import Inotify


class _Worker(DaemonThread):
    """
    Thread that reads events from `inotify` and writes to `queue`.
    """

    def __init__(self, inotify, queue):
        DaemonThread.__init__(self)
        self._read_events = inotify.read_events
        self._queue = queue

    def run(self):
        while self.should_keep_running():
            inotify_events = self._read_events()
            for inotify_event in inotify_events:
                logging.debug("worker: in event %s", inotify_event)
                if inotify_event.is_moved_to:
                    from_event = self._queue._catch(inotify_event.cookie)
                    if from_event:
                        self._queue._put((from_event, inotify_event))
                    else:
                        logging.debug("worker: could not find maching move_from event")
                        self._queue._put(inotify_event)
                else:
                    self._queue._put(inotify_event)


class InotifyBuffer(object):
    """
    A wrapper for `Inotify` that keeps events in memory for `delay` seconds.
    IN_MOVED_FROM and IN_MOVED_TO events are paired during this time.
    """
    def __init__(self, path, recursive=False):
        self.delay = 0.5
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._queue = deque()
        self._inotify = Inotify(path, recursive)
        self._worker = _Worker(self._inotify, self)
        self._worker.start()

    def read_event(self):
        """
        Returns a single event or a tuple of from/to events in case of a
        paired move event.
        """
        while True:
            # wait for queue
            self._not_empty.acquire()
            while len(self._queue) == 0:
                self._not_empty.wait()
            head, insert_time = self._queue[0]
            self._not_empty.release()

            # wait for delay
            time_left = insert_time + self.delay - time.time()
            while time_left > 0:
                time.sleep(time_left)
                time_left = insert_time + self.delay - time.time()

            # return if event is still here
            self._lock.acquire()
            try:
                if len(self._queue) > 0 and self._queue[0][0] is head:
                    self._queue.popleft()
                    return head
            finally:
                self._lock.release()

    def close(self):
        self._worker.stop()
        self._inotify.close()
        self._worker.join()

    def _put(self, elem):
        self._lock.acquire()
        self._queue.append((elem, time.time()))
        self._not_empty.notify()
        self._lock.release()

    def _catch(self, cookie):
        self._lock.acquire()
        ret = None
        for i, elem in enumerate(self._queue):
            event, _ = elem
            try:
                if event.is_moved_from and event.cookie == cookie:
                    ret = event
                    del self._queue[i]
                    break
            except AttributeError:
                pass
        self._lock.release()
        return ret
