

from dirsnapshot import DirectorySnapshot
from threading import Thread, Event
from decorator_utils import synchronized
from os.path import realpath, abspath
from Queue import Queue
from events import *

import logging

logging.basicConfig(level=logging.DEBUG,
                    format='(%(threadName)-10s) %(message)s',
                    )

class FileSystemEventHandler(object):

    def dispatch(self, event):
        _method_map = {
            EVENT_TYPE_MODIFIED: self.on_modified,
            EVENT_TYPE_MOVED: self.on_moved,
            EVENT_TYPE_CREATED: self.on_created,
            EVENT_TYPE_DELETED: self.on_deleted,
            }
        event_type = event.event_type
        _method_map[event_type](event)

    def on_moved(self, event):
        logging.debug(event)
        #what = "directory" if event.is_directory else "file"
        #logging.debug('Moved %s: %s to %s', what, event.path, event.new_path)
        pass

    def on_created(self, event):
        logging.debug(event)
        #what = "directory" if event.is_directory else "file"
        #logging.debug('Created %s: %s', what, event.path)
        pass

    def on_deleted(self, event):
        logging.debug(event)
        #what = "directory" if event.is_directory else "file"
        #logging.debug('Deleted %s: %s', what, event.path)
        pass

    def on_modified(self, event):
        logging.debug(event)
        #what = "directory" if event.is_directory else "file"
        #logging.debug('Modified %s: %s', what, event.path)
        pass


class _PollingEventProducer(Thread):
    """
    """

    def __init__(self, path, interval=1, out_event_queue=None, name=None, *args, **kwargs):
        Thread.__init__(self)
        self.interval = interval
        self.out_event_queue = out_event_queue
        self.args = args
        self.kwargs = kwargs
        self.stopped = Event()
        self.snapshot = None
        self.path = path
        if name is None:
            name = 'PollingObserver(%s)' % realpath(abspath(self.path))
            self.name = name + self.name
        else:
            self.name = name
        self.setDaemon(True)

    def stop(self):
        self.stopped.set()

    @synchronized()
    def get_directory_snapshot_diff(self):
        if self.snapshot is None:
            self.snapshot = DirectorySnapshot(self.path)
            diff = None
        else:
            new_snapshot = DirectorySnapshot(self.path)
            diff = new_snapshot - self.snapshot
            self.snapshot = new_snapshot
        return diff

    def run(self):
        while not self.stopped.is_set():
            self.stopped.wait(self.interval)
            diff = self.get_directory_snapshot_diff()
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



class PollingObserver(Thread):
    """
    """
    def __init__(self, interval=1, *args, **kwargs):
        Thread.__init__(self)
        self.interval = interval
        self.args = args
        self.kwargs = kwargs
        self.event_queue = Queue()
        self.event_producer_threads = set()
        self.rules = {}
        self.setDaemon(True)


    def add_rule(self, path, event_handler):
        if not path in self.rules:
            event_producer_thread = _PollingEventProducer(path=path, interval=self.interval, out_event_queue=self.event_queue)
            self.event_producer_threads.add(event_producer_thread)
            self.rules[path] = {
                'event_handler': event_handler,
                'event_producer_thread': event_producer_thread,
                }


    def remove_rule(self, path):
        if path in self.rules:
            o = self.rules.pop(path)
            o['event_producer_thread'].stop()



    def run(self):
        for t in self.event_producer_threads:
            t.start()
            try:
                while True:
                    (rule_path, event) = self.event_queue.get()
                    event_handler = self.rules[rule_path]['event_handler']
                    event_handler.dispatch(event)
            except KeyboardInterrupt:
                t.stop()

    def stop(self):
        for t in self.event_producer_threads:
            t.stop()
            #t.join()

    #def join(self):
    #    for t in self.event_producer_threads:
    #        t.join()
        #Thread.join(self)

if __name__ == '__main__':
    import time
    import sys
    path = sys.argv[1]
    o = PollingObserver()
    o.add_rule(path, FileSystemEventHandler())
    o.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        o.stop()
        raise
    o.join()
