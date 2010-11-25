# -*- coding: utf-8 -*-
# fsevents_observer.py: FSEvents-based observer implementation for Mac OS X.
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

import _watchdog_fsevents as _fsevents

from threading import Thread, Event as ThreadedEvent
from os.path import realpath, abspath, dirname, sep as path_separator

from watchdog.decorator_utils import synchronized
from watchdog.dirsnapshot import DirectorySnapshot
from watchdog.events import DirMovedEvent, DirDeletedEvent, DirCreatedEvent, DirModifiedEvent, \
    FileMovedEvent, FileDeletedEvent, FileCreatedEvent, FileModifiedEvent

#import logging
#logging.basicConfig(level=logging.DEBUG)


def get_parent_dir_path(path):
    return realpath(abspath(dirname(path))).rstrip(path_separator)

class _Stream(object):
    """Stream object that acts as a conduit for the _fsevents module API."""
    def __init__(self, name, event_handler, paths, recursive):
        for path in paths:
            if not isinstance(path, str):
                raise TypeError(
                    "Path must be string, not '%s'." % type(path).__name__)

        # Strip the path of the ending separator to ensure consistent keys
        # in the self.snapshot_for_path dictionary.
        self.is_recursive = recursive
        self.paths = [realpath(abspath(path)).rstrip(path_separator) for path in set(paths)]
        self.event_handler = event_handler
        self.name = name

    def __repr__(self):
        return self.name

    def __str__(self):
        return self.__repr__()


class FSEventsObserver(Thread):
    event = None

    def __init__(self, *args, **kwargs):
        self.streams = set()
        self.map_name_to_stream = {}
        self.snapshot_for_path = {}
        Thread.__init__(self)


    def run(self):
        self._wait_until_stream_registered()
        self._schedule_all_streams()
        _fsevents.loop(self)


    def _wait_until_stream_registered(self):
        """Blocks until a stream is registered."""
        while not self.streams:
            self.event = ThreadedEvent()
            self.event.wait()
            if self.event is None:
                return
            self.event = None


    def _get_snapshot_for_path(self, path):
        """The FSEvents API calls back with paths within the 'watched'
        directory. So get back to the root path for which we have
        snapshots and return the snapshot path and snapshot."""
        try:
            # Strip the path of the ending separator to ensure consistent keys
            # in the self.snapshot_for_path dictionary.
            path.rstrip(path_separator)
            snapshot = self.snapshot_for_path[path]
            #logging.debug(path)
            return (path, snapshot)
        except KeyError:
            path = get_parent_dir_path(path)
            if not path:
                raise
            return self._get_snapshot_for_path(path)


    @synchronized()
    def _get_directory_snapshot_diff(self, path, recursive):
        """Obtains a diff of two directory snapshots."""
        # The path will be reset to the watched directory path
        # and a snapshot will be stored for the correct key.
        (path, snapshot) = self._get_snapshot_for_path(path)
        new_snapshot = DirectorySnapshot(path, recursive=recursive)
        self.snapshot_for_path[path] = new_snapshot
        return new_snapshot - snapshot


    @synchronized()
    def _dispatch_events_for_path(self, event_handler, recursive, path):
        diff = self._get_directory_snapshot_diff(path, recursive)
        if diff:
            for path in diff.files_deleted:
                event_handler.dispatch(FileDeletedEvent(path))

            for path in diff.files_modified:
                event_handler.dispatch(FileModifiedEvent(path))

            for path in diff.files_created:
                event_handler.dispatch(FileCreatedEvent(path))

            for path, new_path in diff.files_moved.items():
                event_handler.dispatch(FileMovedEvent(path, new_path))

            for path in diff.dirs_modified:
                event_handler.dispatch(DirModifiedEvent(path))

            for path in diff.dirs_deleted:
                event_handler.dispatch(DirDeletedEvent(path))

            for path in diff.dirs_created:
                event_handler.dispatch(DirCreatedEvent(path))

            for path, new_path in diff.dirs_moved.items():
                event_handler.dispatch(DirMovedEvent(path, new_path))


    def _schedule_and_set_callback(self, stream):
        if not stream.paths:
            raise ValueError("No paths to observe.")
        for path in stream.paths:
            # Strip the path of the ending separator to ensure consistent keys
            # in the self.snapshot_for_path dictionary.
            path = path.rstrip(path_separator)
            self.snapshot_for_path[path] = DirectorySnapshot(path, recursive=stream.is_recursive)
        def callback(paths, masks):
            for path in paths:
                #logging.debug(path)
                self._dispatch_events_for_path(stream.event_handler, stream.is_recursive, path)
        _fsevents.schedule(self, stream, callback, stream.paths)


    @synchronized()
    def _schedule_all_streams(self):
        for stream in self.streams:
            self._schedule_and_set_callback(stream)
        self.streams = None


    @synchronized()
    def _schedule_stream(self, stream):
        if self.streams is None:
            self._schedule_and_set_callback(stream)
        elif stream in self.streams:
            raise ValueError("Stream already scheduled.")
        else:
            self.streams.add(stream)
            if self.event is not None:
                self.event.set()


    @synchronized()
    def _unschedule_stream(self, stream):
        if self.streams is None:
            _fsevents.unschedule(stream)
        else:
            self.streams.remove(stream)


    @synchronized()
    def schedule(self, name, event_handler, paths=None, recursive=False):
        if not paths:
            raise ValueError('Please specify a few paths.')
        if isinstance(paths, basestring):
            paths = [paths]

        s = _Stream(name, event_handler, paths, recursive)
        self.map_name_to_stream[name] = s
        self._schedule_stream(s)


    @synchronized()
    def unschedule(self, *names):
        if not names:
            for name, stream in self.map_name_to_stream.items():
                self._unschedule_stream(stream)
        else:
            for name in names:
                if name in self.map_name_to_stream:
                    s = self.map_name_to_stream[name]
                    self._unschedule_stream(s)
                    # TODO: Clean up this code.
                    #for path in s.paths:
                    #    del self.snapshot_for_path[path]
                    del self.map_name_to_stream[name]


    def stop(self):
        if self.event is None:
            _fsevents.stop(self)
        else:
            event = self.event
            self.event = None
            event.set()

