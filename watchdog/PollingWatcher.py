

from dirsnapshot import DirectorySnapshot
from threading import Thread, Event
from decorator_utils import synchronized
import logging

logging.basicConfig(level=logging.DEBUG,
                    format='(%(threadName)-10s) %(message)s',
                    )

class PollingWatcher(Thread):
    """
    """

    def __init__(self, path, interval=1, callback=None, *args, **kwargs):
        Thread.__init__(self)
        self.interval = interval
        self.callback = callback
        self.args = args
        self.kwargs = kwargs
        self.stopped = Event()
        self.snapshot = None
        self.path = path
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
            if diff:
                if diff.files_modified: logging.debug('Modified: %s', str(diff.files_modified))
                if diff.files_deleted: logging.debug('Deleted: %s', str(diff.files_deleted))
                if diff.files_moved: logging.debug('Moved: %s', str(diff.files_moved))
                if diff.files_created: logging.debug('Created: %s', str(diff.files_created))


if __name__ == '__main__':
    import time
    import sys
    path = sys.argv[1]
    t = PollingWatcher(path=path, name=path)
    t.start()
    try:
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        t.stop()
    t.join()


