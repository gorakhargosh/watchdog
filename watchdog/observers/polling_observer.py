# -*- coding: utf-8 -*-
# polling_observer.py: Generic polling observer implementation.
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

import os.path
import threading
try:
    # Python 3k
    import queue
except ImportError:
    import Queue as queue

from watchdog.utils.collections import OrderedSetQueue
from watchdog.utils import real_absolute_path, absolute_path, DaemonThread
from watchdog.utils.dirsnapshot import DirectorySnapshot
from watchdog.events import \
    DirMovedEvent, \
    DirDeletedEvent, \
    DirCreatedEvent, \
    DirModifiedEvent, \
    FileMovedEvent, \
    FileDeletedEvent, \
    FileCreatedEvent, \
    FileModifiedEvent


#import logging
#logging.basicConfig(level=logging.DEBUG)

class _PollingEventEmitter(DaemonThread):
    """Daemon thread that monitors a given path recursively and emits
    file system events.
    """
    def __init__(self, path, interval=1, out_event_queue=None, recursive=False, name=None):
        """Monitors a given path and appends file system modification
        events to the output queue."""
        super(_PollingEventEmitter, self).__init__(interval)

        self._lock = threading.Lock()
        self._q = out_event_queue
        self._snapshot = DirectorySnapshot(path, recursive=recursive)
        self._path = real_absolute_path(path)
        self._is_recursive = recursive


    def _get_directory_snapshot_diff(self):
        """Obtains a diff of two directory snapshots."""
        with self._lock:
            new_snapshot = DirectorySnapshot(self._path, recursive=self._is_recursive)
            diff = new_snapshot - self._snapshot
            self._snapshot = new_snapshot
        return diff


    def run(self):
        """
        Appends events to the output event queue
        based on the diff between two states of the same directory.

        """
        while not self.is_stopped:
            self.stopped_event.wait(self.interval)
            diff = self._get_directory_snapshot_diff()

            for path in diff.files_deleted:
                self._q.put((self._path, FileDeletedEvent(path)))
            for path in diff.files_modified:
                self._q.put((self._path, FileModifiedEvent(path)))
            for path in diff.files_created:
                self._q.put((self._path, FileCreatedEvent(path)))
            for path, dest_path in diff.files_moved.items():
                self._q.put((self._path, FileMovedEvent(path, dest_path)))

            for path in diff.dirs_modified:
                self._q.put((self._path, DirModifiedEvent(path)))
            for path in diff.dirs_deleted:
                self._q.put((self._path, DirDeletedEvent(path)))
            for path in diff.dirs_created:
                self._q.put((self._path, DirCreatedEvent(path)))
            for path, dest_path in diff.dirs_moved.items():
                self._q.put((self._path, DirMovedEvent(path, dest_path)))



class _Rule(object):
    '''
    A rule object represents
    '''
    def __init__(self, path, event_handler, event_emitter):
        self._path = path
        self._event_handler = event_handler
        self._event_emitter = event_emitter

    @property
    def path(self):
        return self._path

    @property
    def event_handler(self):
        return self._event_handler

    @property
    def event_emitter(self):
        return self._event_emitter



class PollingObserver(DaemonThread):
    """Observer daemon thread that spawns threads for each path to be monitored.
    """
    def __init__(self, interval=1):
        super(PollingObserver, self).__init__(interval)
        
        self._lock = threading.RLock()
        
        self._event_queue = OrderedSetQueue()
        self._event_emitters = set()
        self._rules = {}
        self._map_name_to_paths = {}

    @property
    def event_queue(self):
        return self._event_queue
        

    # The win32/kqueue observers override this method because all of the other
    # functionality of this class is the same as its own.
    def _create_event_emitter(self, path, recursive):
        return _PollingEventEmitter(path=path,
                                    interval=self.interval,
                                    out_event_queue=self._event_queue,
                                    recursive=recursive)


    def schedule(self, name, event_handler, paths=None, recursive=False):
        """Schedules monitoring specified paths and calls methods in the
        given callback handler based on events occurring in the file system.
        """
        with self._lock:
            if not paths:
                raise ValueError('Please specify a few paths.')
            if isinstance(paths, basestring):
                paths = [paths]
    
            self._map_name_to_paths[name] = set()
            for path in paths:
                if not isinstance(path, basestring):
                    raise TypeError("Path must be string, not '%s'." % type(path).__name__)
                path = real_absolute_path(path)
                self._schedule_path(name, event_handler, recursive, path)


    def _schedule_path(self, name, event_handler, recursive, path):
        """Starts monitoring the given path for file system events."""
        with self._lock:
            if os.path.isdir(path) and not path in self._rules:
                event_emitter = self._create_event_emitter(path=path, recursive=recursive)
                self._event_emitters.add(event_emitter)
                self._rules[path] = _Rule(path=path,
                                        event_handler=event_handler,
                                        event_emitter=event_emitter)
                self._map_name_to_paths[name].add(path)
                event_emitter.start()


    def unschedule(self, *names):
        """Stops monitoring specified paths for file system events."""
        with self._lock:
            if not names:
                for name, path in self._map_name_to_paths.items():
                    self._unschedule_path(path)
            else:
                for name in names:
                    for path in self._map_name_to_paths[name]:
                        self._unschedule_path(path)
                    del self._map_name_to_paths[name]


    def _unschedule_path(self, path):
        """Stops watching a given path if already being monitored."""
        with self._lock:
            if path in self._rules:
                rule = self._rules.pop(path)
                rule.event_emitter.stop()
                self._event_emitters.remove(rule.event_emitter)


    def run(self):
        while not self.is_stopped:
            try:
                (rule_path, event) = self._event_queue.get(block=True, timeout=self.interval)
                rule = self._rules[rule_path]
                rule.event_handler.dispatch(event)
                self._event_queue.task_done()
            except queue.Empty:
                continue


    def on_stopping(self):
        for event_emitter in self._event_emitters:
            event_emitter.stop()


