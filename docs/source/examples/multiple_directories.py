"""Monitor several directories with one observer and a labeled handler per watch.

Usage::

    python multiple_directories.py "input one" "input two"

Directories must already exist. With no arguments, watch the current directory.
Press Ctrl+C to stop monitoring.
"""

from __future__ import annotations

import logging
import sys
import time

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logging.basicConfig(level=logging.INFO, format="%(message)s")


class LabeledEventHandler(FileSystemEventHandler):
    def __init__(self, label: str) -> None:
        self.label = label

    def on_any_event(self, event: FileSystemEvent) -> None:
        logging.info("[%s] %s", self.label, event)


paths = sys.argv[1:] or ["."]
observer = Observer()
started = False
try:
    for path in paths:
        observer.schedule(LabeledEventHandler(path), path, recursive=True)
    observer.start()
    started = True
    while True:
        time.sleep(1)
finally:
    # Also stop any emitters that started before another watch failed to start.
    observer.stop()
    if started:  # An observer thread cannot be joined before it has started.
        observer.join()
