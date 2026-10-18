from __future__ import annotations

import logging
import sys
import time

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.utils.event_debouncer import EventDebouncer

logging.basicConfig(level=logging.INFO)


def rebuild(events: list[FileSystemEvent]) -> None:
    """Run an expensive action once after a burst of file changes."""
    logging.info("Rebuilding after %d filesystem events", len(events))


class DebouncedEventHandler(FileSystemEventHandler):
    def __init__(self, debouncer: EventDebouncer) -> None:
        self.debouncer = debouncer

    def on_any_event(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.debouncer.handle_event(event)


path = sys.argv[1] if len(sys.argv) > 1 else "."

debouncer = EventDebouncer(debounce_interval_seconds=1, events_callback=rebuild)
event_handler = DebouncedEventHandler(debouncer)
observer = Observer()
observer.schedule(event_handler, path, recursive=True)

debouncer.start()
observer.start()
try:
    while True:
        time.sleep(1)
finally:
    observer.stop()
    debouncer.stop()
    observer.join()
    debouncer.join()
