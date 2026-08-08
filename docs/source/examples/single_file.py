import logging
import sys
import time

from watchdog.events import FileSystemEvent, PatternMatchingEventHandler
from watchdog.observers import Observer

logging.basicConfig(level=logging.INFO)


class SingleFileEventHandler(PatternMatchingEventHandler):
    def on_any_event(self, event: FileSystemEvent) -> None:
        logging.info(event)


watched_directory = sys.argv[1]
filename = sys.argv[2] if len(sys.argv) > 2 else "example.txt"
event_handler = SingleFileEventHandler(patterns=[filename], ignore_directories=True)
observer = Observer()
observer.schedule(event_handler, watched_directory, recursive=False)
observer.start()
try:
    while True:
        time.sleep(1)
finally:
    observer.stop()
    observer.join()
