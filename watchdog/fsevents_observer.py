# -*- coding: utf-8 -*-

import _fsevents

from threading import Thread, Event as ThreadedEvent
from os.path import realpath, abspath, sep as path_separator
from decorator_utils import synchronized
from dirsnapshot import DirectorySnapshot
from events import DirMovedEvent, DirDeletedEvent, DirCreatedEvent, DirModifiedEvent, \
    FileMovedEvent, FileDeletedEvent, FileCreatedEvent, FileModifiedEvent


class _Stream(object):
    """Stream object that acts as a conduit for the _fsevents module API."""
    def __init__(self, name, event_handler, *paths):
        for path in paths:
            if not isinstance(path, str):
                raise TypeError(
                    "Path must be string, not '%s'." % type(path).__name__)

        self.event_handler = event_handler
        self.paths = [realpath(abspath(path)) for path in set(paths)]
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


    @synchronized()
    def _get_directory_snapshot_diff(self, path):
        """Obtains a diff of two directory snapshots."""
        # Strip the path of the ending separator to ensure consistent keys
        # in the self.snapshot_for_path dictionary.
        path = path.rstrip(path_separator)
        snapshot = self.snapshot_for_path[path]
        new_snapshot = DirectorySnapshot(path)
        self.snapshot_for_path[path] = new_snapshot
        return new_snapshot - snapshot


    @synchronized()
    def _dispatch_events_for_path(self, event_handler, path):
        diff = self._get_directory_snapshot_diff(path)
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
            self.snapshot_for_path[path] = DirectorySnapshot(path)
        def callback(paths, masks):
            for path in paths:
                self._dispatch_events_for_path(stream.event_handler, path)
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
    def schedule(self, name, event_handler, *paths):
        s = _Stream(name, event_handler, *paths)
        self.map_name_to_stream[name] = s
        self._schedule_stream(s)


    @synchronized()
    def unschedule(self, *names):
        for name in names:
            if name in self.map_name_to_stream:
                s = self.map_name_to_stream[name]
                self._unschedule_stream(s)
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


if __name__ == '__main__':
    import sys
    import time
    from events import FileSystemEventHandler

    event_handler = FileSystemEventHandler()
    o = FSEventsObserver()
    o.schedule('arguments', event_handler, *sys.argv[1:])
    o.start()
    try:
    	while True:
    		time.sleep(1)
    except KeyboardInterrupt:
    	o.unschedule('arguments')
    	o.stop()
    o.join()

