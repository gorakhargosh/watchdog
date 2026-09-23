import logging
import sys
import time

from watchdog.events import FileSystemEvent
from watchdog.observers import Observer
from watchdog.tricks import Trick

logging.basicConfig(level=logging.INFO)


class FileCountTrick(Trick):
    """A custom Trick subclass that keeps a running tally of filesystem
    events by type (created, deleted, modified, moved) and logs the
    counters every time a new event is observed.

    Subclassing Trick (rather than FileSystemEventHandler directly) means
    this handler can also be declared in a watchmedo tricks YAML file,
    since Trick already extends PatternMatchingEventHandler and exposes
    generate_yaml() for scaffolding that config.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.counters = {
            "created": 0,
            "deleted": 0,
            "modified": 0,
            "moved": 0,
            "other": 0,
        }

    def on_any_event(self, event: FileSystemEvent) -> None:
        self.counters[event.event_type] = self.counters.get(event.event_type, 0) + 1
        logging.info("Event counters: %s", self.counters)


event_handler = FileCountTrick(ignore_directories=True)
observer = Observer()
observer.schedule(event_handler, sys.argv[1], recursive=True)
observer.start()
try:
    while True:
        time.sleep(1)
finally:
    observer.stop()
    observer.join()
