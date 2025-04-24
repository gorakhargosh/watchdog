import logging
import sys
import time

from watchdog.events import FileSystemEvent, PatternMatchingEventHandler
from watchdog.observers import Observer

logging.basicConfig(level=logging.DEBUG)


class MyEventHandler(PatternMatchingEventHandler):
    def on_any_event(self, event: FileSystemEvent) -> None:
        logging.debug(event)


event_handler = MyEventHandler(
    patterns=["**/*.py", "**/*.pyc"], ignore_patterns=["version.py"], ignore_directories=True
)
observer = Observer()
observer.schedule(event_handler, sys.argv[1], recursive=True)
observer.start()
try:
    while True:
        time.sleep(1)
finally:
    observer.stop()
    observer.join()
