"""Example: Auto-renaming files based on a timestamp pattern.

Watches a directory and automatically renames files that match a source pattern
to a target pattern (for example, adding a timestamp prefix to new screenshots
or log files).

Usage::

    python renaming.py /path/to/watch [--pattern "*.png"] [--prefix "shot_"]

Args:
    path: The directory to watch. Defaults to the current directory.
    --pattern: Glob pattern for files to rename. Default: "*.png".
    --prefix: Prefix to add to renamed files. Default: "shot_".
"""

from __future__ import annotations

import argparse
import fnmatch
import logging
import os
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logging.basicConfig(level=logging.INFO)


class RenamingEventHandler(FileSystemEventHandler):
    """Rename files matching a pattern with a configurable prefix."""

    def __init__(self, pattern: str = "*.png", prefix: str = "shot_") -> None:
        super().__init__()
        self.pattern = pattern
        self.prefix = prefix
        # Track already-renamed files to avoid re-processing on modify events
        self._renamed: set[str] = set()

    def _matches(self, path: str) -> bool:
        return fnmatch.fnmatch(os.path.basename(path), self.pattern)

    def on_created(self, event) -> None:
        if event.is_directory:
            return
        self._maybe_rename(event.src_path)

    def _maybe_rename(self, src_path: str) -> None:
        if not self._matches(src_path) or src_path in self._renamed:
            return
        directory, basename = os.path.split(src_path)
        name, ext = os.path.splitext(basename)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        new_name = f"{self.prefix}{timestamp}{ext}"
        new_path = os.path.join(directory, new_name)
        if not os.path.exists(new_path):
            os.rename(src_path, new_path)
            logging.info("Renamed: %s -> %s", basename, new_name)
            self._renamed.add(src_path)


# Parse arguments and set up the observer at module level so the test can load it
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("path", nargs="?", default=".", help="Directory to watch")
parser.add_argument(
    "--pattern", default="*.png", help="Glob pattern for files to rename"
)
parser.add_argument(
    "--prefix", default="shot_", help="Prefix for renamed files"
)
args = parser.parse_args()

path = os.path.abspath(args.path)
if not os.path.isdir(path):
    import sys
    sys.exit(f"Error: {path!r} is not a directory")

logging.info("Watching %s for files matching %r (prefix=%r)", path, args.pattern, args.prefix)
event_handler = RenamingEventHandler(pattern=args.pattern, prefix=args.prefix)
observer = Observer()
observer.schedule(event_handler, path, recursive=False)
observer.start()

# Run the sleep loop at module level so the test can exercise it.
# The test framework patches time.sleep to raise KeyboardInterrupt.
try:
    while True:
        time.sleep(1)
finally:
    observer.stop()
    observer.join()
