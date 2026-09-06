"""Example: Watching multiple directories with a single observer.

Demonstrates how to use a single :class:`~watchdog.observers.Observer` to watch
multiple directories simultaneously, each with its own event handler.

Usage::

    python multi_watch.py /path/to/dir1 /path/to/dir2 [--recursive]

Args:
    dirs: One or more directories to watch.
    --recursive: Watch subdirectories recursively. Default: False.
"""

from __future__ import annotations

import argparse
import logging
import os
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")


class LoggingEventHandler(FileSystemEventHandler):
    """Log all file system events with the directory they originated from."""

    def __init__(self, watch_path: str) -> None:
        super().__init__()
        self.watch_path = watch_path

    def on_any_event(self, event) -> None:
        rel_path = event.src_path.replace(self.watch_path, "")
        action = event.event_type.replace("_", " ").capitalize()
        kind = "directory" if event.is_directory else "file"
        logging.info("[%s] %s %s: %s", action, kind, rel_path, event)


# Parse arguments and set up the observer at module level
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "dirs", nargs="+", help="One or more directories to watch"
)
parser.add_argument(
    "--recursive", action="store_true", help="Watch subdirectories recursively"
)
args = parser.parse_args()

for directory in args.dirs:
    if not os.path.isdir(directory):
        import sys
        sys.exit(f"Error: {directory!r} is not a directory")

observer = Observer()
for directory in args.dirs:
    handler = LoggingEventHandler(directory)
    observer.schedule(handler, directory, recursive=args.recursive)
    logging.info("Watching: %s (recursive=%s)", directory, args.recursive)

observer.start()

# Run the sleep loop at module level so the test can exercise it.
try:
    while True:
        time.sleep(1)
finally:
    observer.stop()
    observer.join()
