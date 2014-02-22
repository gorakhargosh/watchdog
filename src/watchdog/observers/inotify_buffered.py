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


DEALAY = 0.5


class _Worker(DaemonThread):
    def __init__(self, inotify, queue):
        DaemonThread.__init__(self)
        self.read_events = inotify.read_events
        self.queue = queue

    def run(self):
        while self.should_keep_running():
            inotify_events = self.read_events()
            for inotify_event in inotify_events:
                logging.debug("worker: in event %s", inotify_event)
                if inotify_event.is_moved_to:
                    from_event = self.queue._catch(inotify_event.cookie)
                    if from_event:
                        self.queue._put((from_event, inotify_event))
                    else:
                        logging.debug("worker: could not find maching move_from event")
                        self.queue._put(inotify_event)
                else:
                    self.queue._put(inotify_event)


class InotifyBuffered(object):
    def __init__(self, path, recursive=False):
        self.lock = threading.Lock()
        self.not_empty = threading.Condition(self.lock)
        self.queue = deque()
        self.delay = DEALAY
        self.inotify = Inotify(path, recursive)
        self.worker = _Worker(self.inotify, self)
        self.worker.start()

    def read_event(self):
        while True:
            # wait for queue
            self.not_empty.acquire()
            while len(self.queue) == 0:
                self.not_empty.wait()
            head, insert_time = self.queue[0]
            self.not_empty.release()

            # wait for delay
            time_left = insert_time + self.delay - time.time()
            while time_left > 0:
                time.sleep(time_left)
                time_left = insert_time + self.delay - time.time()

            # return if event is still here
            self.lock.acquire()
            try:
                if len(self.queue) > 0 and self.queue[0][0] is head:
                    self.queue.popleft()
                    return head
            finally:
                self.lock.release()

    def close(self):
        self.worker.stop()
        self.inotify.close()
        self.worker.join()

    def _put(self, elem):
        self.lock.acquire()
        self.queue.append((elem, time.time()))
        self.not_empty.notify()
        self.lock.release()

    def _catch(self, cookie):
        self.lock.acquire()
        ret = None
        for i, elem in enumerate(self.queue):
            event, _ = elem
            try:
                if event.is_moved_from and event.cookie == cookie:
                    ret = event
                    del self.queue[i]
                    break
            except AttributeError:
                pass
        self.lock.release()
        return ret
