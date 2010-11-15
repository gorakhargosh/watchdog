# -*- coding: utf-8 -*-

from os.path import realpath, abspath, isdir as path_isdir
from Queue import Queue
from threading import Thread, Event

from dirsnapshot import DirectorySnapshot
from decorator_utils import synchronized
from events import DirMovedEvent, DirDeletedEvent, DirCreatedEvent, DirModifiedEvent, \
    FileMovedEvent, FileDeletedEvent, FileCreatedEvent, FileModifiedEvent


class _PollingEventEmitter(Thread):
    """Daemon thread that monitors a given path recursively and emits
    file system events.
    """
    def __init__(self, path, interval=1, out_event_queue=None, name=None):
        """Monitors a given path and appends file system modification
        events to the output queue."""
        Thread.__init__(self)
        self.interval = interval
        self.out_event_queue = out_event_queue
        self.stopped = Event()
        self.snapshot = None
        self.path = path
        if name is None:
            self.name = '%s(%s)' % (self.__class__.__name__, realpath(abspath(self.path)))
        else:
            self.name = name
        self.setDaemon(True)


    def stop(self):
        """Stops monitoring the given path by setting a flag to stop."""
        self.stopped.set()


    @synchronized()
    def _get_directory_snapshot_diff(self):
        """Obtains a diff of two directory snapshots."""
        if self.snapshot is None:
            self.snapshot = DirectorySnapshot(self.path)
            diff = None
        else:
            new_snapshot = DirectorySnapshot(self.path)
            diff = new_snapshot - self.snapshot
            self.snapshot = new_snapshot
        return diff


    def run(self):
        """
        Appends events to the output event queue
        based on the diff between two states of the same directory.

        """
        while not self.stopped.is_set():
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

                for path, new_path in diff.files_moved.items():
                    q.put((self.path, FileMovedEvent(path, new_path)))

                for path in diff.dirs_modified:
                    q.put((self.path, DirModifiedEvent(path)))

                for path in diff.dirs_deleted:
                    q.put((self.path, DirDeletedEvent(path)))

                for path in diff.dirs_created:
                    q.put((self.path, DirCreatedEvent(path)))

                for path, new_path in diff.dirs_moved.items():
                    q.put((self.path, DirMovedEvent(path, new_path)))



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



class PollingObserver(Thread):
    """Observer daemon thread that spawns threads for each path to be monitored.
    """
    def __init__(self, interval=1):
        Thread.__init__(self)
        self.interval = interval
        self.event_queue = Queue()
        self.event_emitters = set()
        self.rules = {}
        self.map_name_to_paths = {}
        self.setDaemon(True)


    @synchronized()
    def schedule(self, name, event_handler, *paths):
        """Schedules monitoring specified paths and calls methods in the
        given callback handler based on events occurring in the file system.
        """
        for path in paths:
            if not isinstance(path, str):
                raise TypeError(
                    "Path must be string, not '%s'." % type(path).__name__)

        self.map_name_to_paths[name] = set()
        for path in paths:
            self._schedule_path(name, event_handler, path)


    @synchronized()
    def _schedule_path(self, name, event_handler, path):
        """Starts monitoring the given path for file system events."""
        if path_isdir(path) and not path in self.rules:
            event_emitter = _PollingEventEmitter(path=path,
                                                 interval=self.interval,
                                                 out_event_queue=self.event_queue)
            self.event_emitters.add(event_emitter)
            self.rules[path] = _Rule(path=path,
                                    event_handler=event_handler,
                                    event_emitter=event_emitter)
            self.map_name_to_paths[name].add(path)
            event_emitter.start()


    @synchronized()
    def unschedule(self, *names):
        """Stops monitoring specified paths for file system events."""
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
        try:
            while True:
                (rule_path, event) = self.event_queue.get()
                rule = self.rules[rule_path]
                rule.event_handler.dispatch(event)
                self.event_queue.task_done()
        except KeyboardInterrupt:
            self.stop()


    def stop(self):
        """Stops all monitoring."""
        for event_emitter in self.event_emitters:
            event_emitter.stop()


if __name__ == '__main__':
    import time
    import sys
    from os.path import abspath, realpath, dirname
    from events import FileSystemEventHandler

    o = PollingObserver()
    event_handler = FileSystemEventHandler()
    o.schedule('arguments', event_handler, *sys.argv[1:])
    o.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        o.unschedule('arguments')
        o.stop()
        raise
    o.join()
