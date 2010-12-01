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
    import queue
except ImportError:
    import Queue as queue

#from watchdog.utils import echo

from watchdog.utils.dirsnapshot import DirectorySnapshot
from watchdog.utils import \
    real_absolute_path, \
    absolute_path, \
    DaemonThread
from watchdog.observers import _EventEmitter
from watchdog.events import \
    DirMovedEvent, \
    DirDeletedEvent, \
    DirCreatedEvent, \
    DirModifiedEvent, \
    FileMovedEvent, \
    FileDeletedEvent, \
    FileCreatedEvent, \
    FileModifiedEvent, \
    EventQueue



class _PollingEventEmitter(_EventEmitter):
    """Daemon thread that monitors a given path recursively and emits
    file system events.
    """
    def __init__(self, path, handler, event_queue,
                 recursive=False, interval=1):
        """Monitors a given path and appends file system modification
        events to the output queue."""
        super(_PollingEventEmitter, self).__init__(path,
                                                   handler,
                                                   event_queue,
                                                   recursive,
                                                   interval)
        self._snapshot = DirectorySnapshot(path, recursive=recursive)

    #@echo.echo
    def _get_directory_snapshot_diff(self):
        """Obtains a diff of two directory snapshots."""
        with self.lock:
            new_snapshot = DirectorySnapshot(self.path,
                                             recursive=self.is_recursive)
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
                self.event_queue.put(
                    FileDeletedEvent(path, handlers=self.handlers))
            for path in diff.files_modified:
                self.event_queue.put(
                    FileModifiedEvent(path, handlers=self.handlers))
            for path in diff.files_created:
                self.event_queue.put(
                    FileCreatedEvent(path, handlers=self.handlers))
            for path, dest_path in diff.files_moved.items():
                self.event_queue.put(
                    FileMovedEvent(path, dest_path, handlers=self.handlers))

            for path in diff.dirs_modified:
                self.event_queue.put(
                    DirModifiedEvent(path, handlers=self.handlers))
            for path in diff.dirs_deleted:
                self.event_queue.put(
                    DirDeletedEvent(path, handlers=self.handlers))
            for path in diff.dirs_created:
                self.event_queue.put(
                    DirCreatedEvent(path, handlers=self.handlers))
            for path, dest_path in diff.dirs_moved.items():
                self.event_queue.put(
                    DirMovedEvent(path, dest_path, handlers=self.handlers))



class PollingObserver(DaemonThread):
    """Observer daemon thread that spawns threads for each path to be monitored.
    """
    def __init__(self, interval=0.5):
        super(PollingObserver, self).__init__(interval=interval)

        self._lock = threading.Lock()

        # All the emitters created as a result of scheduling a group of
        # paths under a name.
        self._emitters_for_name = {}

        # Collection of all the emitters.
        self._emitters = set()

        # Used to detect emitters with duplicate signatures.
        self._emitter_for_signature = {}

        # Event queue that will be filled by worker-emitter threads with events.
        self._event_queue = EventQueue()

        # Maintains a mapping of names to their event handlers.
        # There's a one-to-one mapping between names and event handlers.
        self._handler_for_name = {}


    @property
    def event_queue(self):
        return self._event_queue


    #@echo.echo
    def create_event_emitter(self, path, handler, event_queue, recursive, interval):
        return _PollingEventEmitter(path=path,
                                    handler=handler,
                                    event_queue=event_queue,
                                    recursive=recursive,
                                    interval=interval)

    #@echo.echo
    def schedule(self, name, event_handler, paths=None, recursive=False):
        """Schedules monitoring specified paths and calls methods in the
        given callback handler based on events occurring in the file system.
        """
        if not paths:
            raise ValueError('Please specify a few paths.')
        if isinstance(paths, basestring):
            paths = [paths]

        with self._lock:
            if name in self._emitters_for_name:
                raise ValueError("Duplicate watch entry named '%s'" % name)

            self._emitters_for_name[name] = set()
            for path in paths:
                if not isinstance(path, basestring):
                    raise TypeError("Path must be string, not '%s'." %
                                    type(path).__name__)

                path = real_absolute_path(path)
                if not os.path.isdir(path):
                    raise ValueError("Path '%s' is not a directory." % path)

                try:
                    # If we have an emitter for this path already with
                    # this signature, we don't create a new
                    # emitter. Instead we add the handler to the event
                    # object, which when dispatched calls the handler code.
                    emitter = self._emitter_for_signature[(path, recursive)]
                    emitter.add_handler(handler)
                except KeyError:
                    # Create a new emitter and start it.
                    emitter = self.create_event_emitter(path=path,
                                                        handler=event_handler,
                                                        event_queue=self.event_queue,
                                                        recursive=recursive,
                                                        interval=self.interval)
                    self._handler_for_name[name] = event_handler
                    self._emitters_for_name[name].add(emitter)
                    self._emitters.add(emitter)
                    self._emitter_for_signature[(path, recursive)] = emitter

            for emitter in self._emitters:
                if not emitter.is_alive():
                    emitter.start()


    def unschedule(self, *names):
        """Stops monitoring specified paths for file system events."""
        with self._lock:
            for name in names:
                # Each handler is given a name.
                handler = self._handler_for_name[name]

                for emitter in self._emitters_for_name[name]:
                    if handler in emitter.handlers:
                        emitter.remove_handler(handler)
                        if not emitter.handlers:
                            emitter.stop()
                            del self._emitter_for_signature[(emitter.path, emitter.is_recursive)]
                del self._emitters_for_name[name]


    def run(self):
        while not self.is_stopped:
            try:
                event = self.event_queue.get(block=True, timeout=self.interval)
                event.dispatch()
                self.event_queue.task_done()
            except queue.Empty:
                continue
        self._clean_up()


    def _clean_up(self):
        for emitter in self._emitters:
            emitter.join()
        self._emitters_for_name.clear()
        self._emitter_for_signature.clear()
        self._emitters.clear()
