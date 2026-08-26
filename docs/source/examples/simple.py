from __future__ import annotations

import logging
import sys
import time

from watchdog import events
from watchdog.observers import Observer

logging.basicConfig(level=logging.DEBUG)


class MyEventHandler(events.FileSystemEventHandler):
    def on_any_event(self, event: events.FileSystemEvent) -> None:
        logging.info("Any event: %s", event)

    def on_created(self, event: events.DirCreatedEvent | events.FileCreatedEvent) -> None:
        logging.info("Created: %s", event)

    def on_deleted(self, event: events.DirDeletedEvent | events.FileDeletedEvent) -> None:
        logging.info("Deleted: %s", event)

    def on_modified(self, event: events.DirModifiedEvent | events.FileModifiedEvent) -> None:
        logging.info("Modified: %s", event)

    def on_moved(self, event: events.DirMovedEvent | events.FileMovedEvent) -> None:
        logging.info("Moved: %s", event)

    def on_opened(self, event: events.FileOpenedEvent) -> None:
        logging.info("Opened: %s", event)

    def on_closed(self, event: events.FileClosedEvent) -> None:
        logging.info("Closed: %s", event)

    def on_closed_no_write(self, event: events.FileClosedNoWriteEvent) -> None:
        logging.info("Closed no write: %s", event)


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
