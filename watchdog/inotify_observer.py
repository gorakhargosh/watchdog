# -*- coding: utf-8 -*-

from threading import Thread, Event as ThreadedEvent
from os.path import realpath, abspath, join as path_join, sep as path_separator, dirname
from decorator_utils import synchronized
from events import DirMovedEvent, DirDeletedEvent, DirCreatedEvent, DirModifiedEvent, \
    FileMovedEvent, FileDeletedEvent, FileCreatedEvent, FileModifiedEvent, \
    EVENT_TYPE_MOVED, EVENT_TYPE_DELETED, EVENT_TYPE_CREATED, EVENT_TYPE_MODIFIED

from pyinotify import ALL_EVENTS, \
    ProcessEvent, WatchManager, ThreadedNotifier


class _ProcessEventDispatcher(ProcessEvent):

    def my_init(self, **kwargs):
        if not 'event_handler' in kwargs:
            raise ValueError('event_handler argument to  _ProcessEventDispatcher is not specified.')
        self.event_handler = kwargs['event_handler']

    def process_IN_CREATE(self, event):
        path = event.pathname
        if event.dir:
            self.event_handler.on_created(DirCreatedEvent(path))
        else:
            self.event_handler.on_created(FileCreatedEvent(path))


    def process_IN_DELETE(self, event):
        path = event.pathname
        if event.dir:
            self.event_handler.on_deleted(DirDeletedEvent(path))
        else:
            self.event_handler.on_deleted(FileDeletedEvent(path))


    def process_IN_CLOSE_WRITE(self, event):
        path = event.pathname
        if event.dir:
            self.event_handler.on_modified(DirModifiedEvent(path))
        else:
            self.event_handler.on_modified(FileModifiedEvent(path))


    def process_IN_ATTRIB(self, event):
        self.process_IN_CLOSE_WRITE(event)


    def process_IN_MOVED_TO(self, event):
        # TODO: Moved event on a directory does not fire moved event for
        # files inside the directory. Fix?
        path = event.pathname
        new_path = event.src_pathname
        if event.dir:
            self.event_handler.on_moved(DirMovedEvent(path, new_path=new_path))
        else:
            self.event_handler.on_moved(FileMovedEvent(path, new_path=new_path))


class _Rule(object):
    def __init__(self, name, notifier, descriptors):
        self.name = name
        self.notifier = notifier
        self.descriptors = descriptors


class InotifyObserver(Thread):
    def __init__(self, interval=1,):
        Thread.__init__(self)
        self.wm = WatchManager()
        self.stopped = ThreadedEvent()
        self.notifiers = set()
        self.name_to_rule = dict()
        self.setDaemon(True)

    def stop(self):
        self.stopped.set()
        for notifier in self.notifiers:
            notifier.stop()


    @synchronized()
    def schedule(self, name, event_handler, *paths):
        """Schedules monitoring."""
        #from pyinotify import PrintAllEvents
        #dispatcher = PrintAllEvents()
        dispatcher = _ProcessEventDispatcher(event_handler=event_handler)
        notifier = ThreadedNotifier(self.wm, dispatcher)
        self.notifiers.add(notifier)
        for path in paths:
            if not isinstance(path, str):
                raise TypeError(
                    "Path must be string, not '%s'." % type(path).__name__)
            descriptors = self.wm.add_watch(path, ALL_EVENTS, rec=True, auto_add=True)
        self.name_to_rule[name] = _Rule(name, notifier, descriptors)
        notifier.start()

    @synchronized()
    def unschedule(self, *names):
        for name in names:
            try:
                rule = self.name_to_rule[name]
                self.wm.rm_watch(rule.descriptors.values())
            except KeyError:
                raise


    def run(self):
        import time
        while not self.stopped.is_set():
            time.sleep(1)


if __name__ == '__main__':
    import sys
    import time
    from events import FileSystemEventHandler

    o = InotifyObserver()
    event_handler = FileSystemEventHandler()
    o.schedule('arguments', event_handler, *sys.argv[1:])
    o.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        o.unschedule('arguments')
        o.stop()
    o.join()

