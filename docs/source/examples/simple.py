from __future__ import annotations

import logging
import sys
import time

from watchdog import events
from watchdog.observers import Observer

logging.basicConfig(level=logging.DEBUG)


class MyEventHandler(events.FileSystemEventHandler):
    def on_any_event(self, event: events.FileSystemEvent) -> None:
        logging.debug(event)


path = sys.argv[1] if len(sys.argv) > 1 else "."

event_handler = MyEventHandler()
observer = Observer()
observer.schedule(event_handler, path, recursive=True)
observer.start()
try:
    while True:
        time.sleep(1)
finally:
    observer.stop()
    observer.join()
