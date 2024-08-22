from __future__ import annotations

import logging
import sys
import time

from watchdog import events
from watchdog.observers import Observer

logging.basicConfig(level=logging.DEBUG)


class MyEventHandler(events.FileSystemEventHandler):
    def catch_all_handler(self, event: events.FileSystemEvent) -> None:
        logging.debug(event)

    def on_moved(self, event: events.DirMovedEvent | events.FileMovedEvent) -> None:
        self.catch_all_handler(event)

    def on_created(self, event: events.DirCreatedEvent | events.FileCreatedEvent) -> None:
        self.catch_all_handler(event)

    def on_deleted(self, event: events.DirDeletedEvent | events.FileDeletedEvent) -> None:
        self.catch_all_handler(event)

    def on_modified(self, event: events.DirModifiedEvent | events.FileModifiedEvent) -> None:
        self.catch_all_handler(event)

    def on_closed(self, event: events.FileClosedEvent) -> None:
        self.catch_all_handler(event)

    def on_closed_no_write(self, event: events.FileClosedNoWriteEvent) -> None:
        self.catch_all_handler(event)

    def on_opened(self, event: events.FileOpenedEvent) -> None:
        self.catch_all_handler(event)


path = sys.argv[1]

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
