from __future__ import annotations

import logging
import sys
import time

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logging.basicConfig(level=logging.INFO)


class ChangeHandler(FileSystemEventHandler):
    def on_any_event(self, event: FileSystemEvent) -> None:
        logging.info("File system event: %s", event)


path = sys.argv[1] if len(sys.argv) > 1 else "."

event_handler = ChangeHandler()
observer = Observer()
observer.schedule(event_handler, path, recursive=True)

with observer:
    while True:
        time.sleep(1)
