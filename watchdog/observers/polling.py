# -*- coding: utf-8 -*-
# polling.py: Generic polling emitter implementation.
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

"""
    :module: watchdog.observers.polling_emitter
    :author: Gora Khargosh <gora.khargosh@gmail.com>
"""


from __future__ import with_statement

import threading

from watchdog.utils.dirsnapshot import DirectorySnapshot
from watchdog.observers.api import EventEmitter, DEFAULT_EMITTER_INTERVAL
from watchdog.events import \
    DirMovedEvent, \
    DirDeletedEvent, \
    DirCreatedEvent, \
    DirModifiedEvent, \
    FileMovedEvent, \
    FileDeletedEvent, \
    FileCreatedEvent, \
    FileModifiedEvent


class PollingEmitter(EventEmitter):
    """
    Platform-independent emitter that polls a directory to detect file changes.
    """
    def __init__(self, event_queue, watch, interval=DEFAULT_EMITTER_INTERVAL):
        EventEmitter.__init__(self, event_queue, watch, interval)
        self._snapshot = DirectorySnapshot(watch.path, watch.is_recursive)
        self._lock = threading.RLock()

    def on_thread_exit(self):
        self._snapshot = None

    def queue_events(self, event_queue, watch, interval):
        with self._lock:
            # Get diff between fresh snapshot and previous snapshot.
            # Update snapshot.
            new_snapshot = DirectorySnapshot(watch.path, watch.is_recursive)
            diff = new_snapshot - self._snapshot
            self._snapshot = new_snapshot

        # Files.
        for src_path in diff.files_deleted:
            event_queue.put((FileDeletedEvent(src_path), watch))
        for src_path in diff.files_modified:
            event_queue.put((FileModifiedEvent(src_path), watch))
        for src_path in diff.files_created:
            event_queue.put((FileCreatedEvent(src_path), watch))
        for src_path, dest_path in diff.files_moved.items():
            event_queue.put((FileMovedEvent(src_path, dest_path), watch))

        # Directories.
        for src_path in diff.dirs_deleted:
            event_queue.put((DirDeletedEvent(src_path), watch))
        for src_path in diff.dirs_modified:
            event_queue.put((DirModifiedEvent(src_path), watch))
        for src_path in diff.dirs_created:
            event_queue.put((DirCreatedEvent(src_path), watch))
        for src_path, dest_path in diff.dirs_moved.items():
            event_queue.put((DirMovedEvent(src_path, dest_path), watch))

