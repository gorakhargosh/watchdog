from __future__ import annotations

import logging
import time

from watchdog import events
from watchdog.observers import Observer

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class MyEventHandler(events.FileSystemEventHandler):
    def on_any_event(self, event: events.FileSystemEvent) -> None:
        logger.info("Any event: %s", event)

    def on_created(self, event: events.DirCreatedEvent | events.FileCreatedEvent) -> None:
        logger.info("Created: %s", event)

    def on_deleted(self, event: events.DirDeletedEvent | events.FileDeletedEvent) -> None:
        logger.info("Deleted: %s", event)

    def on_modified(self, event: events.DirModifiedEvent | events.FileModifiedEvent) -> None:
        logger.info("Modified: %s", event)

    def on_moved(self, event: events.DirMovedEvent | events.FileMovedEvent) -> None:
        logger.info("Moved: %s", event)

    def on_opened(self, event: events.FileOpenedEvent) -> None:
        logger.info("Opened: %s", event)

    def on_closed(self, event: events.FileClosedEvent) -> None:
        logger.info("Closed: %s", event)

    def on_closed_no_write(self, event: events.FileClosedNoWriteEvent) -> None:
        logger.info("Closed no write: %s", event)


event_handler = MyEventHandler()
observer = Observer()
observer.schedule(event_handler, ".", recursive=True)
observer.start()
try:
    while True:
        time.sleep(1)
finally:
    observer.stop()
    observer.join()
