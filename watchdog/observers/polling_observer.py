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

import os.path

try:
    # Python 3k
    from queue import Queue, Empty as QueueEmpty
except ImportError:
    from Queue import Queue, Empty as QueueEmpty

from watchdog.utils import real_absolute_path, absolute_path
from watchdog.observers import DaemonThread
from watchdog.dirsnapshot import DirectorySnapshot
from watchdog.decorator_utils import synchronized
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

        self.out_event_queue = out_event_queue
        self.snapshot = None
        self.path = real_absolute_path(path)
        self.is_recursive = recursive
        if name is None:
            self.name = '%s(%s)' % (self.__class__.__name__, self.path)
        else:
            self.name = name


    @synchronized()
    def _get_directory_snapshot_diff(self):
        """Obtains a diff of two directory snapshots."""
        if self.snapshot is None:
            self.snapshot = DirectorySnapshot(self.path, recursive=self.is_recursive)
            diff = None
        else:
            new_snapshot = DirectorySnapshot(self.path, recursive=self.is_recursive)
            diff = new_snapshot - self.snapshot
            self.snapshot = new_snapshot
        return diff


    def run(self):
        """
        Appends events to the output event queue
        based on the diff between two states of the same directory.

        """
        while not self.is_stopped:
            self.stopped.wait(self.interval)
            diff = self._get_directory_snapshot_diff()
            if diff and self.out_event_queue:
                q = self.out_event_queue

                for path in diff.files_deleted:
                    q.put((self.path, FileDeletedEvent(path)))

                for path in diff.files_modified:
                    q.put((self.path, FileModifiedEvent(path)))

                for path in diff.files_created:
                    q.put((self.path, FileCreatedEvent(path)))

                for path, dest_path in diff.files_moved.items():
                    q.put((self.path, FileMovedEvent(path, dest_path)))

                for path in diff.dirs_modified:
                    q.put((self.path, DirModifiedEvent(path)))

                for path in diff.dirs_deleted:
                    q.put((self.path, DirDeletedEvent(path)))

                for path in diff.dirs_created:
                    q.put((self.path, DirCreatedEvent(path)))

                for path, dest_path in diff.dirs_moved.items():
                    q.put((self.path, DirMovedEvent(path, dest_path)))



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
        self.event_queue = Queue()
        self.event_emitters = set()
        self.rules = {}
        self.map_name_to_paths = {}


    # The win32/kqueue observers override this method because all of the other
    # functionality of this class is the same as its own.
    def _create_event_emitter(self, path, recursive):
        return _PollingEventEmitter(path=path,
                                    interval=self.interval,
                                    out_event_queue=self.event_queue,
                                    recursive=recursive)


    @synchronized()
    def schedule(self, name, event_handler, paths=None, recursive=False):
        """Schedules monitoring specified paths and calls methods in the
        given callback handler based on events occurring in the file system.
        """
        if not paths:
            raise ValueError('Please specify a few paths.')
        if isinstance(paths, basestring):
            paths = [paths]

        self.map_name_to_paths[name] = set()
        for path in paths:
            if not isinstance(path, basestring):
                raise TypeError("Path must be string, not '%s'." % type(path).__name__)
            path = real_absolute_path(path)
            self._schedule_path(name, event_handler, recursive, path)


    @synchronized()
    def _schedule_path(self, name, event_handler, recursive, path):
        """Starts monitoring the given path for file system events."""
        if os.path.isdir(path) and not path in self.rules:
            event_emitter = self._create_event_emitter(path=path, recursive=recursive)
            self.event_emitters.add(event_emitter)
            self.rules[path] = _Rule(path=path,
                                    event_handler=event_handler,
                                    event_emitter=event_emitter)
            self.map_name_to_paths[name].add(path)
            event_emitter.start()


    @synchronized()
    def unschedule(self, *names):
        """Stops monitoring specified paths for file system events."""
        if not names:
            for name, path in self.map_name_to_paths.items():
                self._unschedule_path(path)
        else:
            for name in names:
                for path in self.map_name_to_paths[name]:
                    self._unschedule_path(path)
                del self.map_name_to_paths[name]


    @synchronized()
    def _unschedule_path(self, path):
        """Stops watching a given path if already being monitored."""
        if path in self.rules:
            rule = self.rules.pop(path)
            rule.event_emitter.stop()
            self.event_emitters.remove(rule.event_emitter)


    def run(self):
        """Dispatches events from the event queue to the callback handler."""
        while not self.is_stopped:
            #logging.debug('runloop')
            try:
                (rule_path, event) = self.event_queue.get(block=True, timeout=self.interval)
                rule = self.rules[rule_path]
                rule.event_handler.dispatch(event)
                self.event_queue.task_done()
            except QueueEmpty:
                #logging.debug('queue empty')
                continue

    def on_stopping(self):
        for event_emitter in self.event_emitters:
            event_emitter.stop()


